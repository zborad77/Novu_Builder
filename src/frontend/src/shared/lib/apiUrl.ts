/**
 * Mapování cest API na Gateway/BFF (NC-007 etapa 1, kontrakt kap. 6.3 a 7).
 *
 * Prohlížeč nikdy nevolá `/api/v1/*` přímo – vše jde přes stejný origin na
 * `/bff/api/*`, gateway přidá session (HttpOnly cookie) a předá dál do core.
 */

export const BFF_API_PREFIX = '/bff/api'

const CORE_API_PREFIX = '/api/v1'

/**
 * Převede cestu API na cestu přes BFF.
 *
 *  - `/cases/1`            → `/bff/api/cases/1`  (cesty relativní k `/api/v1`)
 *  - `/api/v1/cases/1`     → `/bff/api/cases/1`
 *  - `/bff/api/cases/1`    → beze změny
 *
 * Absolutní URL a cesty bez úvodního lomítka odmítne – klient smí mluvit jen
 * se stejným originem.
 */
export function toBffApiPath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error(`API path must be a same-origin absolute path, got: ${path}`)
  }
  if (path === BFF_API_PREFIX || path.startsWith(`${BFF_API_PREFIX}/`)) {
    return path
  }
  if (path === CORE_API_PREFIX || path.startsWith(`${CORE_API_PREFIX}/`)) {
    return `${BFF_API_PREFIX}${path.slice(CORE_API_PREFIX.length)}`
  }
  return `${BFF_API_PREFIX}${path}`
}

/**
 * Převede URL souboru z odpovědi API (`ProjectPhotoRead.url`, `variants.*.url`,
 * `ExportRead.downloadUrl`) na URL použitelnou v `<img src>` / odkazu ke stažení.
 *
 * `/api/v1/files/...` → `/bff/api/files/...`; session cookie pošle prohlížeč sám.
 * Lokální `blob:` a `data:` URL projdou beze změny. Cokoli jiného (absolutní
 * URL úložiště, `/storage/...`) vrátí `null` – web nesmí načítat soubory mimo
 * vlastní origin (CSP `img-src 'self' blob: data:`).
 */
export function resolveApiUrl(url: string | null | undefined): string | null {
  if (!url) return null
  if (url.startsWith('blob:') || url.startsWith('data:')) return url
  if (url.startsWith(`${CORE_API_PREFIX}/`) || url.startsWith(`${BFF_API_PREFIX}/`)) {
    return toBffApiPath(url)
  }
  return null
}
