/**
 * dependency-cruiser configuration
 *
 * CI gate: `npm run dep-cruise` must pass with 0 violations.
 * Run locally: npx depcruise --config .dependency-cruiser.cjs src
 *
 * Enforces architectural rules that ESLint cannot catch reliably:
 *   - No cross-feature internal imports (only index.ts boundary allowed)
 *   - app/ and pages/ use only a feature's public API (index.ts)
 *   - apiClient only from the feature API layer (features/<feature>/api/)
 *   - No raw axios/fetch outside apiClient.ts
 *   - No queryClient.invalidateQueries called from pages/
 *   - No circular dependencies
 */

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    // -----------------------------------------------------------------------
    // RULE 1: No cross-feature internal imports
    // features/X/** must not import from features/Y/** (only features/Y/index.ts)
    // -----------------------------------------------------------------------
    {
      name: 'no-cross-feature-internals',
      comment:
        'Features may only consume another feature\'s public API (index.ts). ' +
        'Direct import of another feature\'s internals is forbidden.',
      severity: 'error',
      from: { path: '^src/features/([^/]+)/' },
      to: {
        path: '^src/features/(?!$1/)[^/]+/',
        // Allow importing the index.ts public API file
        pathNot: '^src/features/[^/]+/index\\.(ts|tsx|js|jsx)$',
      },
    },

    // -----------------------------------------------------------------------
    // RULE 1b: app/ a pages/ smí z feature importovat jen její index.ts
    // (modulární architektura – feature je modul s veřejným rozhraním)
    // -----------------------------------------------------------------------
    {
      name: 'app-and-pages-use-feature-public-api',
      comment:
        'app/ and pages/ may only import a feature through its public API (index.ts).',
      severity: 'error',
      from: { path: '^src/(app|pages)/' },
      to: {
        path: '^src/features/[^/]+/',
        pathNot: '^src/features/[^/]+/index\\.(ts|tsx|js|jsx)$',
      },
    },

    // -----------------------------------------------------------------------
    // RULE 1c: apiClient smí používat jen API vrstva feature (features/*/api/)
    // Stránky, providery, hooky a komponenty volají backend přes ni.
    // -----------------------------------------------------------------------
    {
      name: 'api-client-only-in-api-layer',
      comment:
        'Only features/<feature>/api/** may import shared/lib/apiClient; ' +
        'UI code calls the backend through the feature API layer.',
      severity: 'error',
      from: {
        path: '^src/',
        pathNot: '^src/(features/[^/]+/api/|shared/lib/)',
      },
      to: { path: '^src/shared/lib/apiClient\\.ts$' },
    },

    // -----------------------------------------------------------------------
    // RULE 1d: vygenerované kontrakty jsou jen ke čtení – nic z nich neimportují
    // -----------------------------------------------------------------------
    {
      name: 'generated-contracts-are-leaves',
      comment: 'Generated contract files must not depend on application code.',
      severity: 'error',
      from: { path: '^src/shared/api/generated/' },
      to: { path: '^src/', pathNot: '^src/shared/api/generated/' },
    },

    // -----------------------------------------------------------------------
    // RULE 2: No raw HTTP clients (axios / fetch) outside apiClient.ts
    // -----------------------------------------------------------------------
    {
      name: 'no-raw-axios-in-api-wrappers',
      comment:
        'API wrapper files (*Api.ts) must use shared/lib/apiClient, ' +
        'never import axios directly.',
      severity: 'error',
      from: { path: '^src/features/.*/api/' },
      to: { path: '^node_modules/axios(/|$)' },
    },
    {
      name: 'no-raw-fetch-anywhere',
      comment: 'node-fetch and cross-fetch are banned; use apiClient.',
      severity: 'error',
      from: { path: '^src/' },
      to: { path: '^node_modules/(node-fetch|cross-fetch)(/|$)' },
    },

    // -----------------------------------------------------------------------
    // RULE 3: Pages must not import queryClient (for invalidation)
    // Note: severity=warn because dep-cruiser cannot distinguish read vs write
    // usage — code review confirms the absence of invalidateQueries calls.
    // -----------------------------------------------------------------------
    {
      name: 'no-query-invalidation-in-pages',
      comment:
        'Pages importing queryClient is a smell — invalidation belongs in mutation hooks. ' +
        'Warn only; verify in code review that no invalidateQueries call is in a page.',
      severity: 'warn',
      from: { path: '^src/pages/' },
      to: { path: '^src/shared/lib/queryClient' },
    },

    // -----------------------------------------------------------------------
    // RULE 4: store/ must not import from features/
    // -----------------------------------------------------------------------
    {
      name: 'no-store-to-features',
      comment:
        'Store modules must not depend on features. ' +
        'Store is for pure UI state; data belongs in the query cache.',
      severity: 'error',
      from: { path: '^src/store/' },
      to: { path: '^src/features/' },
    },

    // -----------------------------------------------------------------------
    // RULE 5: shared/ must not import from features/, pages/, app/, or store/
    // -----------------------------------------------------------------------
    {
      name: 'no-shared-to-upper-layers',
      comment:
        'Shared utilities are the lowest layer — they must not depend on features, ' +
        'pages, app, or store.',
      severity: 'error',
      from: { path: '^src/shared/' },
      to: { path: '^src/(features|pages|app|store)/' },
    },

    // -----------------------------------------------------------------------
    // RULE 6: No circular dependencies
    // -----------------------------------------------------------------------
    {
      name: 'no-circular',
      comment: 'Circular dependencies are always an architecture error.',
      severity: 'error',
      from: {},
      to: { circular: true },
    },

    // -----------------------------------------------------------------------
    // RULE 7: features/ must not import from pages/
    // -----------------------------------------------------------------------
    {
      name: 'no-features-to-pages',
      comment: 'Features must not import from pages/ — pages compose features, not the reverse.',
      severity: 'error',
      from: { path: '^src/features/' },
      to: { path: '^src/pages/' },
    },
  ],

  options: {
    exclude: {
      path: '^src/.*\\.(js|jsx)$',
    },
    doNotFollow: {
      path: 'node_modules',
    },
    tsPreCompilationDeps: true,
    tsConfig: {
      fileName: 'tsconfig.json',
    },
    reporterOptions: {
      dot: {
        collapsePattern: 'node_modules/[^/]+',
      },
      archi: {
        collapsePattern: '^(src/(features|pages|app|shared|store))/[^/]+',
      },
      text: {
        highlightFocused: true,
      },
    },
  },
}
