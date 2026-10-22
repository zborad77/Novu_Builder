/**
 * Texty UI na jednom místě – příprava na CZ/EN bez nové knihovny.
 *
 * Pravidla:
 *  - každý klíč musí mít obě jazykové verze (typově vynuceno přes TextKey),
 *  - proměnné se zapisují jako `{name}` a doplní je `t(key, { name })`,
 *  - aktivní jazyk je zatím pevně `cs` (html lang="cs"); přepínání přijde
 *    s i18n vrstvou, texty se nepřesouvají znovu.
 *
 * Do modulu jsou zatím převedené obrazovky upravené v NC-007 etapě 1
 * (přihlášení, odhlášení, ověření session, fotky zakázky, prohlížeč fotky).
 */

const cs = {
  'common.retry': 'Zkusit znovu',
  'common.forbidden': 'Nemáte oprávnění k zobrazení tohoto obsahu.',
  'common.forbiddenAction': 'Nemáte oprávnění k této akci.',

  'auth.login.title': 'Přihlášení',
  'auth.login.subtitle': 'Zadejte přístupové údaje k účtu',
  'auth.login.email': 'E-mail',
  'auth.login.emailPlaceholder': 'vas@email.cz',
  'auth.login.password': 'Heslo',
  'auth.login.submit': 'Přihlásit se',
  'auth.login.submitting': 'Přihlašuji…',
  'auth.login.invalidCredentials': 'Nesprávný e-mail nebo heslo.',
  'auth.login.rateLimited': 'Příliš mnoho pokusů o přihlášení. Zkuste to za chvíli.',
  'auth.login.failed': 'Přihlášení selhalo. Zkuste to znovu.',

  'auth.logout': 'Odhlásit',
  'auth.logoutAll': 'Odhlásit všude',
  'auth.logoutAllConfirm': 'Odhlásit všechna webová přihlášení tohoto účtu na všech zařízeních?',
  'auth.loggingOut': 'Odhlašuji…',
  'auth.logoutFailed': 'Odhlášení se nezdařilo. Zkuste to znovu.',
  'auth.logoutAllPartial':
    'Byli jste odhlášeni, ale odhlášení na ostatních zařízeních se nepodařilo potvrdit. Zkuste to po přihlášení znovu.',
  'auth.sessionExpired': 'Přihlášení vypršelo. Přihlaste se znovu.',
  'auth.session.loading': 'Ověřuji přihlášení…',
  'auth.session.error': 'Nepodařilo se ověřit přihlášení. Server je možná dočasně nedostupný.',

  'shell.guest': 'Host',
  'shell.noSession': 'Bez aktivního přihlášení',

  'photos.title': 'Fotky',
  'photos.count': '{count} fotek',
  'photos.loading': 'Načítám fotky…',
  'photos.loadFailed': 'Fotky se nepodařilo načíst.',
  'photos.empty': 'Zatím nejsou nahrané žádné fotky.',
  'photos.minimumRecommended':
    'Pro analýzu doporučujeme alespoň {minimum} fotek. Chybí ještě {missing}.',
  'photos.badgePrimary': 'Hlavní',
  'photos.badgeAnalysis': 'Analýza',
  'photos.previewUnavailable': 'Náhled není k dispozici',

  'viewer.loadFailed': 'Fotku se nepodařilo načíst.',
  'viewer.notFound': 'Fotka nebyla nalezena.',
  'viewer.backToPhotos': '← Zpět na fotky',
  'viewer.allPhotos': '← Všechny fotky',
  'viewer.prev': '← Předchozí',
  'viewer.next': 'Další →',
  'viewer.refreshing': 'Obnovuji…',
  'viewer.badgePrimary': 'Hlavní',
  'viewer.badgeReference': 'Referenční pro analýzu',
  'viewer.confirmAiArea': 'Potvrdit plochu z AI',
  'viewer.saving': 'Ukládám…',
  'viewer.confirmed': 'Potvrzeno ✓',
  'viewer.saved': 'Uloženo',
  'viewer.saveError': 'Chyba uložení',
  'viewer.manualArea': 'Ruční oprava plochy',
  'viewer.resetToAi': 'Vrátit na AI',
  'viewer.analysisResult': 'Výsledek analýzy',
  'viewer.updating': 'Aktualizuji…',
  'viewer.fieldObject': 'Objekt',
  'viewer.fieldCondition': 'Stav',
  'viewer.fieldScope': 'Rozsah',
  'viewer.fieldArea': 'Odhad plochy',
  'viewer.fieldWorkType': 'Typ práce',
  'viewer.fieldConfidence': 'Jistota',
  'viewer.toastSelectionReset': 'Analýza se změnila – váš výběr byl zrušen.',
  'viewer.toastCaseFinalized': 'Zakázka je uzavřená – výběr už nelze měnit.',
  'viewer.toastAnalysisUpdated': 'Analýza byla aktualizována – zkontrolujte nový výsledek.',
  'viewer.toastSaveFailed': 'Výběr se nepodařilo uložit. Zkuste to znovu.',
  'viewer.toastSaveForbidden': 'Nemáte oprávnění měnit výběr.',
} as const

export type TextKey = keyof typeof cs

const en: Record<TextKey, string> = {
  'common.retry': 'Try again',
  'common.forbidden': 'You do not have permission to view this content.',
  'common.forbiddenAction': 'You do not have permission for this action.',

  'auth.login.title': 'Sign in',
  'auth.login.subtitle': 'Enter your account credentials',
  'auth.login.email': 'E-mail',
  'auth.login.emailPlaceholder': 'you@example.com',
  'auth.login.password': 'Password',
  'auth.login.submit': 'Sign in',
  'auth.login.submitting': 'Signing in…',
  'auth.login.invalidCredentials': 'Incorrect e-mail or password.',
  'auth.login.rateLimited': 'Too many sign-in attempts. Please try again later.',
  'auth.login.failed': 'Sign-in failed. Please try again.',

  'auth.logout': 'Sign out',
  'auth.logoutAll': 'Sign out everywhere',
  'auth.logoutAllConfirm': 'Sign out all web sessions of this account on every device?',
  'auth.loggingOut': 'Signing out…',
  'auth.logoutFailed': 'Sign-out failed. Please try again.',
  'auth.logoutAllPartial':
    'You have been signed out, but signing out on other devices could not be confirmed. Please try again after signing in.',
  'auth.sessionExpired': 'Your session has expired. Please sign in again.',
  'auth.session.loading': 'Checking your session…',
  'auth.session.error': 'Could not verify your session. The server may be temporarily unavailable.',

  'shell.guest': 'Guest',
  'shell.noSession': 'No active session',

  'photos.title': 'Photos',
  'photos.count': '{count} photos',
  'photos.loading': 'Loading photos…',
  'photos.loadFailed': 'Failed to load photos.',
  'photos.empty': 'No photos uploaded yet.',
  'photos.minimumRecommended':
    'At least {minimum} photos recommended for analysis. {missing} more needed.',
  'photos.badgePrimary': 'Primary',
  'photos.badgeAnalysis': 'Analysis',
  'photos.previewUnavailable': 'Preview not available',

  'viewer.loadFailed': 'Failed to load photo.',
  'viewer.notFound': 'Photo not found.',
  'viewer.backToPhotos': '← Back to photos',
  'viewer.allPhotos': '← All photos',
  'viewer.prev': '← Prev',
  'viewer.next': 'Next →',
  'viewer.refreshing': 'Refreshing…',
  'viewer.badgePrimary': 'Primary',
  'viewer.badgeReference': 'Analysis reference',
  'viewer.confirmAiArea': 'Confirm AI area',
  'viewer.saving': 'Saving…',
  'viewer.confirmed': 'Confirmed ✓',
  'viewer.saved': 'Saved',
  'viewer.saveError': 'Save error',
  'viewer.manualArea': 'Manual repair area',
  'viewer.resetToAi': 'Reset to AI',
  'viewer.analysisResult': 'Analysis result',
  'viewer.updating': 'Updating…',
  'viewer.fieldObject': 'Object',
  'viewer.fieldCondition': 'Condition',
  'viewer.fieldScope': 'Scope',
  'viewer.fieldArea': 'Est. area',
  'viewer.fieldWorkType': 'Work type',
  'viewer.fieldConfidence': 'Confidence',
  'viewer.toastSelectionReset': 'Analysis updated — your selection was reset.',
  'viewer.toastCaseFinalized': 'Case is finalized — selection can no longer be changed.',
  'viewer.toastAnalysisUpdated': 'Analysis was updated — please review the new result.',
  'viewer.toastSaveFailed': 'Failed to save selection. Please try again.',
  'viewer.toastSaveForbidden': 'You do not have permission to change the selection.',
}

export type Locale = 'cs' | 'en'

const DICTIONARIES: Record<Locale, Record<TextKey, string>> = { cs, en }

const ACTIVE_LOCALE: Locale = 'cs'

export function t(
  key: TextKey,
  vars?: Record<string, string | number>,
  locale: Locale = ACTIVE_LOCALE,
): string {
  const template = DICTIONARIES[locale][key]
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  )
}
