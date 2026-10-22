/**
 * Structured error thrown by apiClient for all failed HTTP requests.
 * Extends Error so it works with Promise.reject and instanceof checks.
 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly detail?: unknown

  constructor(opts: { code: string; message: string; status: number; detail?: unknown }) {
    super(opts.message)
    this.name = 'ApiError'
    this.code = opts.code
    this.status = opts.status
    this.detail = opts.detail
  }
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

/**
 * 403 = core odmítl oprávnění. UI jen zobrazí stav „bez oprávnění“,
 * o oprávněních nerozhoduje (NC-007 kap. 7).
 */
export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}
