/**
 * SINGLE HTTP TRANSPORT - all *Api.ts wrappers must use this client exclusively.
 *
 * Guarantees implemented here:
 *  - JWT Authorization header injection
 *  - 401 -> refresh flow -> one-shot retry
 *  - retry loop protection via _isRefreshRetry
 *  - centralized ApiError normalization
 *  - logout when refresh fails
 *  - AbortSignal forwarding for TanStack Query cancellation
 */

import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosHeaderValue,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type RawAxiosRequestHeaders,
} from 'axios'
import { mapErrorCode } from './errorMap'
import { ApiError } from '../types/api.types'

const ACCESS_TOKEN_KEY = 'nb_access_token'
const REFRESH_TOKEN_KEY = 'nb_refresh_token'

type TokenPair = {
  accessToken: string
  refreshToken: string
}

type RefreshResponseShape = {
  accessToken?: string
  refreshToken?: string
  access_token?: string
  refresh_token?: string
}

type ErrorPayload = {
  code?: unknown
  error?: unknown
  message?: unknown
  detail?: unknown
}

export const tokenStorage = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  },

  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  },

  setAccess(token: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, token)
  },

  setRefresh(token: string): void {
    localStorage.setItem(REFRESH_TOKEN_KEY, token)
  },

  setTokens(tokens: TokenPair): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken)
  },

  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}

export const LOGOUT_EVENT = 'nb:logout' as const

function dispatchLogout(): void {
  window.dispatchEvent(new CustomEvent(LOGOUT_EVENT))
}

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'
const REFRESH_PATH = '/auth/refresh'

interface RetryConfig extends AxiosRequestConfig {
  _isRefreshRetry?: boolean
}

const axiosInstance: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

let refreshPromise: Promise<string> | null = null
let logoutDispatched = false

function isRefreshRequest(url: string | undefined): boolean {
  if (!url) return false

  return url === REFRESH_PATH || url.endsWith(REFRESH_PATH)
}

type NormalizableHeaders =
  | AxiosHeaders
  | RawAxiosRequestHeaders
  | string
  | undefined

function ensureHeaders(headers?: NormalizableHeaders): AxiosHeaders {
  if (headers instanceof AxiosHeaders) {
    return headers
  }

  const normalized = new AxiosHeaders()

  if (typeof headers === 'string') {
    normalized.set(headers)
    return normalized
  }

  if (headers && typeof headers === 'object') {
    for (const [name, value] of Object.entries(headers)) {
      if (value !== undefined) {
        normalized.set(name, value as AxiosHeaderValue)
      }
    }
  }

  return normalized
}

function readRefreshPayload(data: unknown): RefreshResponseShape {
  if (typeof data !== 'object' || data === null) {
    return {}
  }

  return data as RefreshResponseShape
}

function readAccessToken(payload: RefreshResponseShape): string | null {
  return payload.accessToken ?? payload.access_token ?? null
}

function readRefreshToken(payload: RefreshResponseShape): string | null {
  return payload.refreshToken ?? payload.refresh_token ?? null
}

function extractPayload(data: unknown): ErrorPayload | undefined {
  if (typeof data !== 'object' || data === null) {
    return undefined
  }

  return data as ErrorPayload
}

function normalizeError(
  error: unknown,
  fallback?: { code?: string; status?: number; detail?: unknown },
): ApiError {
  if (error instanceof ApiError) {
    return error
  }

  if (axios.isAxiosError(error)) {
    if (error.code === 'ERR_CANCELED') {
      return new ApiError({
        code: 'REQUEST_ABORTED',
        message: mapErrorCode('REQUEST_ABORTED'),
        status: 0,
        detail: fallback?.detail ?? error.message,
      })
    }

    const payload = extractPayload(error.response?.data)
    const code =
      (typeof payload?.code === 'string' ? payload.code : undefined) ??
      (typeof payload?.error === 'string' ? payload.error : undefined) ??
      fallback?.code ??
      (error.response == null ? 'NETWORK_ERROR' : 'UNKNOWN')

    const status = error.response?.status ?? fallback?.status ?? 0

    return new ApiError({
      code,
      message: mapErrorCode(code, status),
      status,
      detail: fallback?.detail ?? payload?.detail ?? error.response?.data,
    })
  }

  if (error instanceof Error) {
    const code = fallback?.code ?? 'UNKNOWN'
    const status = fallback?.status ?? 0

    return new ApiError({
      code,
      message: mapErrorCode(code, status),
      status,
      detail: fallback?.detail ?? error.message,
    })
  }

  return new ApiError({
    code: fallback?.code ?? 'UNKNOWN',
    message: mapErrorCode(fallback?.code, fallback?.status),
    status: fallback?.status ?? 0,
    detail: fallback?.detail ?? error,
  })
}

function handleRefreshFailure(error: unknown): ApiError {
  tokenStorage.clear()

  if (!logoutDispatched) {
    logoutDispatched = true
    dispatchLogout()
    queueMicrotask(() => {
      logoutDispatched = false
    })
  }

  return normalizeError(error, {
    code: 'TOKEN_REFRESH_FAILED',
    status: 401,
  })
}

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefresh()

  if (!refreshToken) {
    throw new ApiError({
      code: 'TOKEN_REFRESH_FAILED',
      message: mapErrorCode('TOKEN_REFRESH_FAILED', 401),
      status: 401,
      detail: { reason: 'missing_refresh_token' },
    })
  }

  const response = await axios.post<RefreshResponseShape>(
    `${BASE_URL}${REFRESH_PATH}`,
    { refresh_token: refreshToken },
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: 30_000,
    },
  )

  const payload = readRefreshPayload(response.data)
  const nextAccessToken = readAccessToken(payload)

  if (!nextAccessToken) {
    throw new ApiError({
      code: 'TOKEN_REFRESH_FAILED',
      message: mapErrorCode('TOKEN_REFRESH_FAILED', 401),
      status: 401,
      detail: payload,
    })
  }

  tokenStorage.setAccess(nextAccessToken)

  const nextRefreshToken = readRefreshToken(payload)
  if (nextRefreshToken) {
    tokenStorage.setRefresh(nextRefreshToken)
  }

  return nextAccessToken
}

axiosInstance.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess()
  if (!token) return config

  const headers = ensureHeaders(
    config.headers as AxiosHeaders | RawAxiosRequestHeaders | undefined,
  )
  headers.set('Authorization', `Bearer ${token}`)
  config.headers = headers

  return config
})

axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryConfig | undefined

    if (!originalRequest) {
      return Promise.reject(normalizeError(error))
    }

    const isUnauthorized = error.response?.status === 401
    const alreadyRetried = originalRequest._isRefreshRetry === true
    const requestIsRefresh = isRefreshRequest(originalRequest.url)

    if (!isUnauthorized || alreadyRetried || requestIsRefresh) {
      return Promise.reject(normalizeError(error))
    }

    originalRequest._isRefreshRetry = true

    try {
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null
      })

      const nextAccessToken = await refreshPromise
      const headers = ensureHeaders(
        originalRequest.headers as AxiosHeaders | RawAxiosRequestHeaders | undefined,
      )
      headers.set('Authorization', `Bearer ${nextAccessToken}`)
      originalRequest.headers = headers

      return await axiosInstance(originalRequest)
    } catch (refreshError) {
      return Promise.reject(handleRefreshFailure(refreshError))
    }
  },
)

export type ApiRequestOptions = {
  signal?: AbortSignal
}

function cfg(opts?: ApiRequestOptions): AxiosRequestConfig {
  return opts?.signal !== undefined ? { signal: opts.signal } : {}
}

export const apiClient = {
  get<T>(url: string, params?: Record<string, unknown>, opts?: ApiRequestOptions) {
    return axiosInstance.get<T>(url, { params, ...cfg(opts) }).then((response) => response.data)
  },

  post<T>(url: string, data?: unknown, opts?: ApiRequestOptions) {
    return axiosInstance.post<T>(url, data, cfg(opts)).then((response) => response.data)
  },

  put<T>(url: string, data?: unknown, opts?: ApiRequestOptions) {
    return axiosInstance.put<T>(url, data, cfg(opts)).then((response) => response.data)
  },

  patch<T>(url: string, data?: unknown, opts?: ApiRequestOptions) {
    return axiosInstance.patch<T>(url, data, cfg(opts)).then((response) => response.data)
  },

  delete<T>(url: string, opts?: ApiRequestOptions) {
    return axiosInstance.delete<T>(url, cfg(opts)).then((response) => response.data)
  },

  postForm<T>(url: string, formData: FormData, opts?: ApiRequestOptions) {
    return axiosInstance
      .post<T>(url, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ...cfg(opts),
      })
      .then((response) => response.data)
  },
}
