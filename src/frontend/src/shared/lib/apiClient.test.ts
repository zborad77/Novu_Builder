import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  apiClient,
  bffAuth,
  CSRF_HEADER,
  DEFAULT_TIMEOUT_MS,
  resetApiClientState,
  UNAUTHORIZED_EVENT,
  UPLOAD_TIMEOUT_MS,
} from './apiClient'
import { resolveApiUrl, toBffApiPath } from './apiUrl'
import { ApiError, isForbiddenError } from '../types/api.types'

// ---------------------------------------------------------------------------
// Pomocníci
// ---------------------------------------------------------------------------

type FetchCall = { url: string; init: RequestInit }

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function empty(status: number): Response {
  return new Response(null, { status })
}

const USER = {
  id: 'u1',
  email: 'a@b.cz',
  fullName: 'A B',
  role: 'manager' as const,
  organizationId: 'o1',
  isActive: true,
  isSuperAdmin: false,
}

function session(csrfToken: string): Response {
  return json(200, {
    authenticated: true,
    user: USER,
    csrfToken,
    expiresAt: '2026-10-22T20:00:00Z',
    idleExpiresAt: '2026-10-22T12:30:00Z',
  })
}

let queue: Response[]
let calls: FetchCall[]
let fetchMock: ReturnType<typeof vi.fn>

function respondWith(...responses: Response[]): void {
  queue.push(...responses)
}

function headersOf(call: FetchCall | undefined): Record<string, string> {
  return { ...(call?.init.headers as Record<string, string> | undefined) }
}

let storageSpies: ReturnType<typeof vi.spyOn>[]

beforeEach(() => {
  resetApiClientState()
  queue = []
  calls = []
  // apiClient volá fetch vždy s řetězcovou same-origin cestou.
  fetchMock = vi.fn((input: string, init?: RequestInit) => {
    calls.push({ url: input, init: init ?? {} })
    const next = queue.shift()
    if (!next) return Promise.reject(new Error(`unexpected fetch ${input}`))
    return Promise.resolve(next)
  })
  vi.stubGlobal('fetch', fetchMock)
  storageSpies = [
    vi.spyOn(Storage.prototype, 'setItem'),
    vi.spyOn(Storage.prototype, 'getItem'),
    vi.spyOn(Storage.prototype, 'removeItem'),
    vi.spyOn(Storage.prototype, 'clear'),
  ]
})

afterEach(() => {
  // Žádný test nesmí sáhnout do localStorage/sessionStorage.
  for (const spy of storageSpies) expect(spy).not.toHaveBeenCalled()
  // Žádný požadavek nesmí nést Authorization.
  for (const call of calls) {
    const names = Object.keys(headersOf(call)).map((n) => n.toLowerCase())
    expect(names).not.toContain('authorization')
  }
})

async function primeCsrf(token = 'csrf-1'): Promise<void> {
  respondWith(session(token))
  await bffAuth.getSession()
  calls.length = 0
}

// ---------------------------------------------------------------------------
// Mapování cest
// ---------------------------------------------------------------------------

describe('mapování /api/v1 → /bff/api', () => {
  it('cesty relativní k /api/v1 i s prefixem /api/v1 jdou na /bff/api', async () => {
    respondWith(json(200, { ok: 1 }), json(200, { ok: 2 }), json(200, { ok: 3 }))

    await apiClient.get('/cases/1')
    await apiClient.get('/api/v1/cases/2')
    await apiClient.get('/bff/api/cases/3')

    expect(calls.map((c) => c.url)).toEqual([
      '/bff/api/cases/1',
      '/bff/api/cases/2',
      '/bff/api/cases/3',
    ])
  })

  it('všechna volání mají credentials same-origin a query parametry', async () => {
    respondWith(json(200, []))
    await apiClient.get('/cases', { page: 2, q: 'a b', skip: undefined, ids: ['x', 'y'] })

    expect(calls[0]?.url).toBe('/bff/api/cases?page=2&q=a+b&ids=x&ids=y')
    expect(calls[0]?.init.credentials).toBe('same-origin')
  })

  it('odmítne absolutní URL (jen stejný origin)', () => {
    expect(() => toBffApiPath('https://evil.example/api/v1/cases')).toThrow()
    expect(() => toBffApiPath('//evil.example/x')).toThrow()
  })

  it('resolveApiUrl převádí URL souborů a zahazuje URL mimo origin', () => {
    expect(resolveApiUrl('/api/v1/files/images/i1/preview')).toBe('/bff/api/files/images/i1/preview')
    expect(resolveApiUrl('/api/v1/files/exports/e1')).toBe('/bff/api/files/exports/e1')
    expect(resolveApiUrl('/bff/api/files/images/i1/original')).toBe('/bff/api/files/images/i1/original')
    expect(resolveApiUrl('blob:http://localhost/abc')).toBe('blob:http://localhost/abc')
    expect(resolveApiUrl(null)).toBeNull()
    expect(resolveApiUrl('')).toBeNull()
    expect(resolveApiUrl('http://minio:9000/bucket/x?X-Amz-Signature=1')).toBeNull()
    expect(resolveApiUrl('/storage/images/x.jpg')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// CSRF
// ---------------------------------------------------------------------------

describe('CSRF hlavička', () => {
  it('posílá X-CSRF-Token jen u POST/PUT/PATCH/DELETE', async () => {
    await primeCsrf('tok')
    respondWith(
      json(200, {}),
      json(200, {}),
      json(200, {}),
      json(200, {}),
      empty(204),
    )

    await apiClient.get('/cases/1')
    await apiClient.post('/cases', { a: 1 })
    await apiClient.put('/cases/1', { a: 1 })
    await apiClient.patch('/cases/1', { a: 1 })
    await apiClient.delete('/cases/1')

    const tokens = calls.map((c) => headersOf(c)[CSRF_HEADER])
    expect(tokens).toEqual([undefined, 'tok', 'tok', 'tok', 'tok'])
    expect(calls.map((c) => c.init.method)).toEqual(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
  })

  it('token z odpovědi loginu se použije u další mutace; login sám CSRF neposílá', async () => {
    respondWith(json(200, { user: USER, csrfToken: 'from-login' }), json(200, {}))

    await bffAuth.login('a@b.cz', 'secret')
    await apiClient.post('/cases', {})

    expect(calls[0]?.url).toBe('/bff/auth/login')
    expect(calls[0]?.init.method).toBe('POST')
    expect(headersOf(calls[0])[CSRF_HEADER]).toBeUndefined()
    expect(headersOf(calls[1])[CSRF_HEADER]).toBe('from-login')
  })

  it('multipart: CSRF ano, Content-Type nastaví prohlížeč (boundary)', async () => {
    await primeCsrf('tok')
    respondWith(json(201, { id: 'i1' }))
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.jpg')

    await apiClient.postForm('/cases/1/images', form)

    const headers = headersOf(calls[0])
    expect(headers[CSRF_HEADER]).toBe('tok')
    expect(headers['Content-Type']).toBeUndefined()
    expect(calls[0]?.init.body).toBe(form)
  })

  it('403 s CSRF chybou: jednou obnoví /bff/session a zopakuje s novým tokenem', async () => {
    await primeCsrf('old')
    respondWith(
      json(403, { detail: 'Forbidden.', code: 'CSRF_FAILED', requestId: 'r1' }),
      session('new'),
      json(200, { done: true }),
    )

    const result = await apiClient.post<{ done: boolean }>('/cases', { a: 1 })

    expect(result).toEqual({ done: true })
    expect(calls.map((c) => c.url)).toEqual(['/bff/api/cases', '/bff/session', '/bff/api/cases'])
    expect(headersOf(calls[0])[CSRF_HEADER]).toBe('old')
    expect(headersOf(calls[2])[CSRF_HEADER]).toBe('new')
    expect(calls[2]?.init.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('opakuje jen jednou – druhý 403 se vrátí volajícímu', async () => {
    await primeCsrf('old')
    respondWith(
      json(403, { detail: 'Forbidden.', code: 'CSRF_FAILED' }),
      session('new'),
      json(403, { detail: 'Forbidden.', code: 'CSRF_FAILED' }),
    )

    const error = await apiClient.post('/cases', {}).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(403)
    expect(calls).toHaveLength(3)
  })

  it('403 z core (oprávnění) se neopakuje a nevolá /bff/session', async () => {
    await primeCsrf('tok')
    respondWith(json(403, { detail: 'Insufficient permissions.' }))

    const error = await apiClient.post('/cases', {}).catch((e: unknown) => e)

    expect(isForbiddenError(error)).toBe(true)
    expect((error as ApiError).code).toBe('FORBIDDEN')
    expect(calls.map((c) => c.url)).toEqual(['/bff/api/cases'])
  })

  it('403 bez code CSRF_FAILED se neopakuje, ani když detail zmiňuje CSRF', async () => {
    await primeCsrf('tok')
    respondWith(json(403, { detail: 'CSRF token invalid.' }))

    const error = await apiClient.post('/cases', {}).catch((e: unknown) => e)

    expect((error as ApiError).status).toBe(403)
    expect(calls).toHaveLength(1)
  })

  it('403 ORIGIN (jiný code) se neopakuje', async () => {
    await primeCsrf('tok')
    respondWith(json(403, { detail: 'Forbidden.', code: 'ORIGIN_FAILED' }))

    const error = await apiClient.delete('/cases/1').catch((e: unknown) => e)

    expect((error as ApiError).code).toBe('ORIGIN_FAILED')
    expect(calls).toHaveLength(1)
  })

  it('403 u GET session neobnovuje', async () => {
    respondWith(json(403, { detail: 'Forbidden.' }))

    const error = await apiClient.get('/cases/1').catch((e: unknown) => e)

    expect(isForbiddenError(error)).toBe(true)
    expect(calls).toHaveLength(1)
  })

  it('403 a session mezitím skončila → stav odhlášeno', async () => {
    await primeCsrf('tok')
    const listener = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, listener)
    respondWith(json(403, { detail: 'Forbidden.', code: 'CSRF_FAILED' }), json(200, { authenticated: false }))

    const error = await apiClient.post('/cases', {}).catch((e: unknown) => e)

    window.removeEventListener(UNAUTHORIZED_EVENT, listener)
    expect((error as ApiError).status).toBe(401)
    expect(listener).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// 401
// ---------------------------------------------------------------------------

describe('401 z /bff/api', () => {
  it('vyšle UNAUTHORIZED_EVENT jednou, vyhodí ApiError 401 a zahodí CSRF token', async () => {
    await primeCsrf('tok')
    const listener = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, listener)
    respondWith(json(401, { detail: 'Not authenticated.' }), json(401, { detail: 'x' }))

    const results = await Promise.allSettled([apiClient.get('/cases/1'), apiClient.get('/cases/2')])

    window.removeEventListener(UNAUTHORIZED_EVENT, listener)
    expect(results.every((r) => r.status === 'rejected')).toBe(true)
    const reason = (results[0] as PromiseRejectedResult).reason as ApiError
    expect(reason).toBeInstanceOf(ApiError)
    expect(reason.status).toBe(401)
    expect(listener).toHaveBeenCalledTimes(1)

    // CSRF token je pryč – další mutace ho nepošle.
    calls.length = 0
    respondWith(json(401, {}))
    await apiClient.post('/cases', {}).catch(() => undefined)
    expect(headersOf(calls[0])[CSRF_HEADER]).toBeUndefined()
  })

  it('401 z loginu je chyba údajů, ne ztráta session', async () => {
    const listener = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, listener)
    respondWith(json(401, { detail: 'Invalid credentials.' }))

    const error = await bffAuth.login('a@b.cz', 'bad').catch((e: unknown) => e)

    window.removeEventListener(UNAUTHORIZED_EVENT, listener)
    expect((error as ApiError).status).toBe(401)
    expect(listener).not.toHaveBeenCalled()
  })

  it('stream (SSE) jde přes /bff/api s cookie a 401 přepne do stavu odhlášeno', async () => {
    const listener = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, listener)
    respondWith(empty(401))

    const response = await apiClient.stream('/cases/1/activity/stream', {
      headers: { Accept: 'text/event-stream', 'Last-Event-ID': '7' },
    })

    window.removeEventListener(UNAUTHORIZED_EVENT, listener)
    expect(response.status).toBe(401)
    expect(calls[0]?.url).toBe('/bff/api/cases/1/activity/stream')
    expect(calls[0]?.init.credentials).toBe('same-origin')
    expect(headersOf(calls[0])['Last-Event-ID']).toBe('7')
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// Session, odhlášení
// ---------------------------------------------------------------------------

describe('session a odhlášení', () => {
  it('GET /bff/session vrací stav a neposílá CSRF', async () => {
    respondWith(json(200, { authenticated: false }))

    const result = await bffAuth.getSession()

    expect(result).toEqual({ authenticated: false })
    expect(calls[0]?.url).toBe('/bff/session')
    expect(calls[0]?.init.method).toBe('GET')
    expect(calls[0]?.init.credentials).toBe('same-origin')
    expect(headersOf(calls[0])[CSRF_HEADER]).toBeUndefined()
  })

  it('logout a logout-all posílají CSRF a pak token zahodí', async () => {
    await primeCsrf('tok')
    respondWith(empty(204))
    await bffAuth.logout()

    respondWith(json(200, {}))
    await apiClient.post('/cases', {}).catch(() => undefined)

    expect(calls[0]?.url).toBe('/bff/auth/logout')
    expect(headersOf(calls[0])[CSRF_HEADER]).toBe('tok')
    expect(headersOf(calls[1])[CSRF_HEADER]).toBeUndefined()

    await primeCsrf('tok2')
    respondWith(empty(204))
    await bffAuth.logoutAll()
    expect(calls[0]?.url).toBe('/bff/auth/logout-all')
    expect(headersOf(calls[0])[CSRF_HEADER]).toBe('tok2')
  })

  it('logout-all 502 LOGOUT_ALL_PARTIAL = odhlášeno s upozorněním (partial)', async () => {
    await primeCsrf('tok')
    respondWith(json(502, { detail: 'Upstream error.', code: 'LOGOUT_ALL_PARTIAL' }))

    const result = await bffAuth.logoutAll()
    expect(result).toEqual({ partial: true })

    // CSRF token je zahozený jako po úspěšném odhlášení.
    respondWith(json(200, {}))
    await apiClient.post('/cases', {}).catch(() => undefined)
    expect(headersOf(calls[1])[CSRF_HEADER]).toBeUndefined()
  })

  it('logout-all úspěch vrací partial: false', async () => {
    await primeCsrf('tok')
    respondWith(empty(204))

    await expect(bffAuth.logoutAll()).resolves.toEqual({ partial: false })
  })

  it('logout-all jiné 502 / síťová chyba se propagují beze změny', async () => {
    await primeCsrf('tok')
    respondWith(json(502, { detail: 'Upstream error.' }))
    const upstream = await bffAuth.logoutAll().catch((e: unknown) => e)
    expect((upstream as ApiError).status).toBe(502)

    fetchMock.mockImplementationOnce((input: string, init?: RequestInit) => {
      calls.push({ url: input, init: init ?? {} })
      return Promise.reject(new TypeError('Failed to fetch'))
    })
    const network = await bffAuth.logoutAll().catch((e: unknown) => e)
    expect((network as ApiError).code).toBe('NETWORK_ERROR')

    // Token zůstal – uživatel je pořád přihlášený.
    respondWith(json(200, {}))
    calls.length = 0
    await apiClient.post('/cases', {})
    expect(headersOf(calls[0])[CSRF_HEADER]).toBe('tok')
  })

  it('logout s 401 (session už neplatí) je úspěch', async () => {
    await primeCsrf('tok')
    respondWith(json(401, { detail: 'Not authenticated.' }))

    await expect(bffAuth.logout()).resolves.toBeUndefined()
  })

  it('logout s 5xx chybu propaguje (UI zůstane přihlášené a ohlásí chybu)', async () => {
    await primeCsrf('tok')
    respondWith(json(502, { detail: 'Upstream error.' }))

    const error = await bffAuth.logout().catch((e: unknown) => e)
    expect((error as ApiError).status).toBe(502)
  })

  it('síťová chyba → ApiError NETWORK_ERROR', async () => {
    fetchMock.mockImplementationOnce((input: string, init?: RequestInit) => {
      calls.push({ url: input, init: init ?? {} })
      return Promise.reject(new TypeError('Failed to fetch'))
    })

    const error = await apiClient.get('/cases').catch((e: unknown) => e)
    expect((error as ApiError).code).toBe('NETWORK_ERROR')
  })
})

// ---------------------------------------------------------------------------
// Časové limity
// ---------------------------------------------------------------------------

describe('časové limity', () => {
  /** fetch, který nikdy neodpoví, jen reaguje na abort. */
  function hangingFetch(): void {
    fetchMock.mockImplementation((input: string, init?: RequestInit) => {
      calls.push({ url: input, init: init ?? {} })
      return new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    })
  }

  afterEach(() => {
    vi.useRealTimers()
  })

  it('běžný požadavek skončí REQUEST_TIMEOUT po 30 s', async () => {
    vi.useFakeTimers()
    hangingFetch()
    const pending = apiClient.post('/cases', {}).catch((e: unknown) => e)

    await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS)
    const error = await pending

    expect(DEFAULT_TIMEOUT_MS).toBe(30_000)
    expect((error as ApiError).code).toBe('REQUEST_TIMEOUT')
  })

  it('postForm (upload) má delší limit 120 s', async () => {
    vi.useFakeTimers()
    hangingFetch()
    let settled = false
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.jpg')
    const pending = apiClient.postForm('/cases/1/images', form).catch((e: unknown) => {
      settled = true
      return e
    })

    await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS + 1_000)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS - DEFAULT_TIMEOUT_MS)
    const error = await pending

    expect(UPLOAD_TIMEOUT_MS).toBe(120_000)
    expect(settled).toBe(true)
    expect((error as ApiError).code).toBe('REQUEST_TIMEOUT')
  })
})
