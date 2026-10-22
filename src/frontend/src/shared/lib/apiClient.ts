/**
 * JEDINÝ HTTP TRANSPORT webu – všechny *Api.ts obaly volají backend jen přes něj.
 *
 * NC-007 etapa 1 (kontrakt docs/security/NC-007_STAGE1_CONTRACT.md kap. 2–4 a 7):
 *  - prohlížeč mluví jen s gateway na stejném originu: `/bff/api/*`, `/bff/session`,
 *    `/bff/auth/*`; `credentials: 'same-origin'`, session nese HttpOnly cookie,
 *  - v JS není žádný token: žádné `Authorization`, žádný localStorage/sessionStorage,
 *    žádná obnova tokenů (tu dělá gateway),
 *  - CSRF token se drží jen v paměti modulu (z `GET /bff/session` nebo z loginu)
 *    a posílá se jako `X-CSRF-Token` výhradně u POST/PUT/PATCH/DELETE,
 *  - 403 u mutace → jednou obnovit `/bff/session` a požadavek zopakovat,
 *  - 401 z `/bff/api` → stav „odhlášeno“ (událost UNAUTHORIZED_EVENT),
 *  - jednotná normalizace chyb do ApiError, předávání AbortSignal (TanStack Query).
 */

import { mapErrorCode } from './errorMap'
import { toBffApiPath } from './apiUrl'
import { ApiError } from '../types/api.types'
import type { BffLoginResponse, BffSessionResponse } from '../types/session.types'

export const UNAUTHORIZED_EVENT = 'nb:unauthorized' as const

export const CSRF_HEADER = 'X-CSRF-Token'

const BFF_SESSION_PATH = '/bff/session'
const BFF_LOGIN_PATH = '/bff/auth/login'
const BFF_LOGOUT_PATH = '/bff/auth/logout'
const BFF_LOGOUT_ALL_PATH = '/bff/auth/logout-all'

const REQUEST_TIMEOUT_MS = 30_000
/** Multipart upload (fotky až 25 MiB) potřebuje delší limit. */
export const UPLOAD_TIMEOUT_MS = 120_000
export const DEFAULT_TIMEOUT_MS = REQUEST_TIMEOUT_MS

/** Kód 403 od gateway při neplatném CSRF tokenu (kontrakt kap. 4 bod 5). */
export const CSRF_FAILED_CODE = 'CSRF_FAILED'

/** 502 z logout-all: gateway zrušila své sessions i cookie, revokace v core nepotvrzena. */
export const LOGOUT_ALL_PARTIAL_CODE = 'LOGOUT_ALL_PARTIAL'

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

const MUTATING_METHODS: ReadonlySet<HttpMethod> = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export type ApiRequestOptions = {
  signal?: AbortSignal
}

export type ApiStreamOptions = ApiRequestOptions & {
  /** Hlavičky konkrétního požadavku, např. `Accept: text/event-stream`, `Last-Event-ID`. */
  headers?: Record<string, string>
}

type QueryParams = Record<string, unknown>

interface RequestSpec {
  method: HttpMethod
  /** Plná same-origin cesta (`/bff/...`). */
  url: string
  params?: QueryParams | undefined
  json?: unknown
  form?: FormData | undefined
  signal?: AbortSignal | undefined
  /** Poslat X-CSRF-Token (jen mutace; login ho nepotřebuje). */
  withCsrf: boolean
  /** Při 403 jednou obnovit session a zopakovat. */
  csrfRetry: boolean
  /** 401 znamená ztrátu session → UNAUTHORIZED_EVENT. */
  signalUnauthorized: boolean
  /** Časový limit požadavku v ms (výchozí REQUEST_TIMEOUT_MS). */
  timeoutMs?: number
}

type ErrorPayload = {
  code?: unknown
  error?: unknown
  detail?: unknown
  requestId?: unknown
}

// ---------------------------------------------------------------------------
// Stav v paměti (nikdy ne ve Storage)
// ---------------------------------------------------------------------------

let csrfToken: string | null = null
let sessionRefreshPromise: Promise<BffSessionResponse> | null = null
let unauthorizedDispatched = false

/** Zahodí stav klienta v paměti (CSRF token). Volá se po odhlášení a v testech. */
export function resetApiClientState(): void {
  csrfToken = null
  sessionRefreshPromise = null
  unauthorizedDispatched = false
}

/**
 * Session skončila. Událost se vyšle jen jednou (souběžné 401 ji neopakují);
 * znovu se „nabije“ až s novou platnou session (login nebo /bff/session).
 */
function signalUnauthorized(): void {
  csrfToken = null
  if (unauthorizedDispatched) return
  unauthorizedDispatched = true
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
}

// ---------------------------------------------------------------------------
// Pomocné funkce
// ---------------------------------------------------------------------------

/** Query parametry jen z primitivních hodnot; null/undefined se vynechají. */
function paramValue(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value)
  }
  return null
}

function buildUrl(url: string, params?: QueryParams): string {
  if (!params) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    const items: unknown[] = Array.isArray(value) ? (value as unknown[]) : [value]
    for (const item of items) {
      const text = paramValue(item)
      if (text !== null) search.append(key, text)
    }
  }
  const query = search.toString()
  return query ? `${url}?${query}` : url
}

function asErrorPayload(data: unknown): ErrorPayload | undefined {
  return typeof data === 'object' && data !== null ? (data as ErrorPayload) : undefined
}

function codeForStatus(status: number): string {
  if (status === 401) return 'UNAUTHENTICATED'
  if (status === 403) return 'FORBIDDEN'
  if (status === 404) return 'NOT_FOUND'
  if (status === 429) return 'RATE_LIMITED'
  if (status >= 500) return 'SERVER_ERROR'
  return 'UNKNOWN'
}

function apiErrorFromResponse(status: number, data: unknown): ApiError {
  const payload = asErrorPayload(data)
  const code =
    (typeof payload?.code === 'string' ? payload.code : undefined) ??
    (typeof payload?.error === 'string' ? payload.error : undefined) ??
    codeForStatus(status)

  return new ApiError({
    code,
    message: mapErrorCode(code, status),
    status,
    detail: payload?.detail ?? data,
  })
}

function transportError(code: 'REQUEST_ABORTED' | 'REQUEST_TIMEOUT' | 'NETWORK_ERROR', detail: unknown): ApiError {
  return new ApiError({ code, message: mapErrorCode(code), status: 0, detail })
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) return undefined
  const contentType = response.headers.get('Content-Type') ?? ''
  try {
    if (contentType.includes('application/json')) {
      const text = await response.text()
      return text ? (JSON.parse(text) as unknown) : undefined
    }
    const text = await response.text()
    return text === '' ? undefined : text
  } catch {
    return undefined
  }
}

/** 403 od gateway kvůli CSRF: jen `code === 'CSRF_FAILED'` (kontrakt kap. 4 bod 5). */
function isCsrfFailure(data: unknown): boolean {
  return asErrorPayload(data)?.code === CSRF_FAILED_CODE
}

/**
 * Spojí volitelný signál volajícího s časovým limitem. Vrací signál a úklid.
 * (AbortSignal.any zatím není všude, proto ručně.)
 */
function withTimeout(timeoutMs: number, external?: AbortSignal): {
  signal: AbortSignal
  timedOut: () => boolean
  cleanup: () => void
} {
  const controller = new AbortController()
  let didTimeout = false
  const timer = setTimeout(() => {
    didTimeout = true
    controller.abort()
  }, timeoutMs)

  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener('abort', onExternalAbort, { once: true })
  }

  return {
    signal: controller.signal,
    timedOut: () => didTimeout,
    cleanup: () => {
      clearTimeout(timer)
      external?.removeEventListener('abort', onExternalAbort)
    },
  }
}

async function send(spec: RequestSpec): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined

  if (spec.form !== undefined) {
    // Content-Type s boundary doplní prohlížeč sám.
    body = spec.form
  } else if (spec.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(spec.json)
  }

  if (spec.withCsrf && MUTATING_METHODS.has(spec.method) && csrfToken) {
    headers[CSRF_HEADER] = csrfToken
  }

  const timeout = withTimeout(spec.timeoutMs ?? REQUEST_TIMEOUT_MS, spec.signal)
  try {
    return await fetch(buildUrl(spec.url, spec.params), {
      method: spec.method,
      headers,
      credentials: 'same-origin',
      signal: timeout.signal,
      ...(body !== undefined ? { body } : {}),
      ...(spec.url === BFF_SESSION_PATH ? { cache: 'no-store' as const } : {}),
    })
  } catch (error) {
    if (spec.signal?.aborted) throw transportError('REQUEST_ABORTED', error)
    if (timeout.timedOut()) throw transportError('REQUEST_TIMEOUT', error)
    throw transportError('NETWORK_ERROR', error)
  } finally {
    timeout.cleanup()
  }
}

// ---------------------------------------------------------------------------
// Session (/bff/session)
// ---------------------------------------------------------------------------

function refreshSession(signal?: AbortSignal): Promise<BffSessionResponse> {
  sessionRefreshPromise ??= (async () => {
    const response = await send({
      method: 'GET',
      url: BFF_SESSION_PATH,
      signal,
      withCsrf: false,
      csrfRetry: false,
      signalUnauthorized: false,
    })
    const data = await readBody(response)
    if (!response.ok) throw apiErrorFromResponse(response.status, data)

    const session = data as BffSessionResponse
    csrfToken = session.authenticated ? session.csrfToken : null
    if (session.authenticated) unauthorizedDispatched = false
    return session
  })().finally(() => {
    sessionRefreshPromise = null
  })
  return sessionRefreshPromise
}

// ---------------------------------------------------------------------------
// Jádro požadavku
// ---------------------------------------------------------------------------

async function request<T>(spec: RequestSpec): Promise<T> {
  const isMutation = MUTATING_METHODS.has(spec.method)
  let response = await send(spec)

  if (response.status === 403 && isMutation && spec.csrfRetry) {
    const firstBody = await readBody(response)

    // Jiný 403 (oprávnění z core, Origin) se vrací volajícímu bez dalšího volání.
    if (!isCsrfFailure(firstBody)) {
      throw apiErrorFromResponse(403, firstBody)
    }

    // CSRF_FAILED: jednou obnovit /bff/session a požadavek zopakovat.
    const session = await refreshSession()
    if (!session.authenticated) {
      if (spec.signalUnauthorized) signalUnauthorized()
      throw apiErrorFromResponse(401, { detail: 'Session expired.' })
    }
    response = await send(spec)
  }

  const data = await readBody(response)

  if (response.status === 401 && spec.signalUnauthorized) {
    signalUnauthorized()
  }

  if (!response.ok) {
    throw apiErrorFromResponse(response.status, data)
  }

  return data as T
}

function apiSpec(
  method: HttpMethod,
  path: string,
  opts: ApiRequestOptions | undefined,
  extra: Partial<RequestSpec> = {},
): RequestSpec {
  return {
    method,
    url: toBffApiPath(path),
    signal: opts?.signal,
    withCsrf: true,
    csrfRetry: true,
    signalUnauthorized: true,
    ...extra,
  }
}

// ---------------------------------------------------------------------------
// Veřejné API
// ---------------------------------------------------------------------------

/**
 * Volání průchozího API core přes `/bff/api`. Cesty se zadávají relativně
 * k `/api/v1` (`/cases/1`) nebo s prefixem `/api/v1/` – obojí se mapuje na `/bff/api/`.
 */
export const apiClient = {
  get<T>(url: string, params?: QueryParams, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('GET', url, opts, { params }))
  },

  post<T>(url: string, data?: unknown, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('POST', url, opts, { json: data }))
  },

  put<T>(url: string, data?: unknown, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('PUT', url, opts, { json: data }))
  },

  patch<T>(url: string, data?: unknown, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('PATCH', url, opts, { json: data }))
  },

  delete<T>(url: string, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('DELETE', url, opts))
  },

  postForm<T>(url: string, formData: FormData, opts?: ApiRequestOptions): Promise<T> {
    return request<T>(apiSpec('POST', url, opts, { form: formData, timeoutMs: UPLOAD_TIMEOUT_MS }))
  },

  /**
   * Otevře streamovaný GET (SSE) a vrátí syrovou Response.
   *
   * Prohlížeč pošle session cookie sám (same-origin). Stav odpovědi se tu
   * nekontroluje – volající si větví 401 vs. ostatní chyby sám; 401 navíc
   * přepne aplikaci do stavu „odhlášeno“.
   */
  async stream(url: string, opts?: ApiStreamOptions): Promise<Response> {
    const response = await fetch(toBffApiPath(url), {
      method: 'GET',
      headers: { ...opts?.headers },
      credentials: 'same-origin',
      cache: 'no-store',
      ...(opts?.signal !== undefined ? { signal: opts.signal } : {}),
    })
    if (response.status === 401) signalUnauthorized()
    return response
  },
}

/** Veřejné endpointy gateway pro přihlášení a session (kontrakt kap. 2). */
export const bffAuth = {
  /** `GET /bff/session` – zároveň obnoví CSRF token v paměti. */
  getSession(opts?: ApiRequestOptions): Promise<BffSessionResponse> {
    return refreshSession(opts?.signal)
  },

  /** `POST /bff/auth/login` – 401 znamená neplatné údaje, ne ztrátu session. */
  async login(email: string, password: string): Promise<BffLoginResponse> {
    const result = await request<BffLoginResponse>({
      method: 'POST',
      url: BFF_LOGIN_PATH,
      json: { email, password },
      withCsrf: false,
      csrfRetry: false,
      signalUnauthorized: false,
    })
    csrfToken = result.csrfToken
    unauthorizedDispatched = false
    return result
  },

  /** `POST /bff/auth/logout`. 401 = session už neplatí, bere se jako úspěch. */
  logout(): Promise<void> {
    return endSession(BFF_LOGOUT_PATH)
  },

  /**
   * `POST /bff/auth/logout-all` – odhlásí všechny webové sessions uživatele.
   *
   * 502 `{"code":"LOGOUT_ALL_PARTIAL"}`: gateway už zrušila všechny své sessions
   * i cookie, jen core revokaci nepotvrdil. Klient je odhlášený stejně jako po
   * úspěchu; výsledek `{ partial: true }` umožní UI zobrazit upozornění.
   */
  async logoutAll(): Promise<LogoutAllResult> {
    try {
      await endSession(BFF_LOGOUT_ALL_PATH)
      return { partial: false }
    } catch (error) {
      if (error instanceof ApiError && error.status === 502 && error.code === LOGOUT_ALL_PARTIAL_CODE) {
        csrfToken = null
        return { partial: true }
      }
      throw error
    }
  },
}

export interface LogoutAllResult {
  /** Odhlášení na ostatních zařízeních nebylo potvrzeno (core revokace selhala). */
  partial: boolean
}

async function endSession(url: string): Promise<void> {
  try {
    await request<void>({
      method: 'POST',
      url,
      withCsrf: true,
      csrfRetry: true,
      signalUnauthorized: false,
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error
  }
  csrfToken = null
}
