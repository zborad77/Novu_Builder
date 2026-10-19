/**
 * Maps backend error codes / HTTP status codes to user-facing messages.
 * Keep entries here, not scattered in components.
 */
const ERROR_MESSAGES: Record<string, string> = {
  // Auth
  INVALID_CREDENTIALS: 'Nespravne prihlasovaci udaje.',
  UNAUTHENTICATED: 'Prihlaseni vyprselo. Prihlaste se znovu.',
  SESSION_EXPIRED: 'Relace vyprsela. Prihlaste se znovu.',
  SESSION_REVOKED: 'Relace byla odvolana.',
  TOKEN_EXPIRED: 'Platnost prihlaseni vyprsela. Prihlaste se znovu.',
  TOKEN_REFRESH_FAILED: 'Nepodarilo se obnovit prihlaseni. Prihlaste se znovu.',
  REFRESH_FAILED: 'Nepodarilo se obnovit prihlaseni. Prihlaste se znovu.',

  // Authorization
  FORBIDDEN: 'Nemate opravneni k teto akci.',
  NOT_FOUND: 'Pozadovany zdroj nebyl nalezen.',

  // Validation
  VALIDATION_ERROR: 'Zkontrolujte zadane hodnoty.',

  // Rate limiting
  RATE_LIMITED: 'Prilis mnoho pozadavku. Zkuste to za chvili.',

  // Transport
  NETWORK_ERROR: 'Sitova chyba. Zkontrolujte pripojeni.',
  REQUEST_ABORTED: 'Pozadavek byl zrusen.',

  // Generic
  SERVER_ERROR: 'Chyba serveru. Zkuste to znovu.',
  UNKNOWN: 'Nastala necekavana chyba.',
}

export function mapErrorCode(code: string | undefined, status?: number): string {
  if (code && code in ERROR_MESSAGES) {
    return ERROR_MESSAGES[code] as string
  }

  if (status === 401) return ERROR_MESSAGES['UNAUTHENTICATED'] as string
  if (status === 403) return ERROR_MESSAGES['FORBIDDEN'] as string
  if (status === 404) return ERROR_MESSAGES['NOT_FOUND'] as string
  if (status === 429) return ERROR_MESSAGES['RATE_LIMITED'] as string
  if (status != null && status >= 500) return ERROR_MESSAGES['SERVER_ERROR'] as string

  return ERROR_MESSAGES['UNKNOWN'] as string
}
