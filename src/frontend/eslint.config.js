import js from '@eslint/js'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import reactHooks from 'eslint-plugin-react-hooks'
import boundaries from 'eslint-plugin-boundaries'
import globals from 'globals'

/**
 * ESLint flat config.
 *
 * Enforces:
 *  1. TypeScript strict rules
 *  2. React Hooks rules
 *  3. Feature boundary rules
 *  4. No raw fetch/axios outside apiClient.ts
 *  5. NC-007 (SECURITY_ARCHITECTURE 4.1, 4.7): žádné dangerouslySetInnerHTML /
 *     innerHTML, žádný localStorage/sessionStorage, document.cookie ani ruční
 *     hlavička Authorization – session nese HttpOnly cookie gateway.
 */

// Web nemá žádný UI stav, který by potřeboval Web Storage (uiStore/viewerStore jsou
// jen v paměti), proto zákaz bez výjimek. Kdyby jednou byl potřeba nesouvisející
// UI stav (např. sbalený panel), přidá se výjimka jen pro konkrétní soubor.
const STORAGE_GLOBALS = [
  {
    name: 'localStorage',
    message: 'NC-007: Web Storage je zakázaný (žádné tokeny ani session v JS).',
  },
  {
    name: 'sessionStorage',
    message: 'NC-007: Web Storage je zakázaný (žádné tokeny ani session v JS).',
  },
]

const STORAGE_PROPERTIES = ['window', 'globalThis', 'self'].flatMap((object) => [
  { object, property: 'localStorage', message: 'NC-007: Web Storage je zakázaný.' },
  { object, property: 'sessionStorage', message: 'NC-007: Web Storage je zakázaný.' },
])

const ELEMENTS = [
  { type: 'app', pattern: 'src/app/**/*' },
  { type: 'pages', pattern: 'src/pages/**/*' },
  { type: 'features', pattern: 'src/features/**/*' },
  { type: 'shared', pattern: 'src/shared/**/*' },
  { type: 'store', pattern: 'src/store/**/*' },
]

export default [
  js.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.json',
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...tsPlugin.configs['recommended-requiring-type-checking'].rules,
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { boundaries },
    settings: {
      'boundaries/elements': ELEMENTS,
      'boundaries/include': ['src/**/*'],
    },
    rules: {
      'boundaries/no-unknown': 'error',
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          rules: [
            { from: 'pages', allow: ['features', 'shared', 'app', 'store'] },
            { from: 'features', allow: ['shared'] },
            { from: 'app', allow: ['pages', 'features', 'shared', 'store'] },
            { from: 'store', allow: ['shared'] },
            { from: 'shared', allow: ['shared'] },
          ],
        },
      ],
    },
  },
  {
    // NC-007: bezpečnostní pravidla pro celý web včetně apiClient.ts
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'JSXAttribute[name.name="dangerouslySetInnerHTML"]',
          message: 'NC-007: dangerouslySetInnerHTML je zakázaný (XSS). Renderujte přes React.',
        },
        {
          selector: 'Property[key.name="dangerouslySetInnerHTML"]',
          message: 'NC-007: dangerouslySetInnerHTML je zakázaný (XSS).',
        },
        {
          selector:
            'AssignmentExpression > MemberExpression.left[property.name=/^(innerHTML|outerHTML)$/]',
          message: 'NC-007: přiřazení do innerHTML/outerHTML je zakázané (XSS).',
        },
        {
          selector: 'Property[key.name="Authorization"], Property[key.value="Authorization"]',
          message: 'NC-007: web neposílá Authorization – session nese HttpOnly cookie gateway.',
        },
      ],
      'no-restricted-globals': ['error', ...STORAGE_GLOBALS],
      'no-restricted-properties': [
        'error',
        ...STORAGE_PROPERTIES,
        {
          object: 'document',
          property: 'cookie',
          message: 'NC-007: session cookie je HttpOnly; s cookies JS nepracuje.',
        },
      ],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/shared/lib/apiClient.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'axios',
              message:
                'Use shared/lib/apiClient instead of importing axios directly. ' +
                'Only src/shared/lib/apiClient.ts may import axios.',
            },
            {
              name: 'node-fetch',
              message: 'Use shared/lib/apiClient. Raw fetch is forbidden.',
            },
            {
              name: 'cross-fetch',
              message: 'Use shared/lib/apiClient. Raw fetch is forbidden.',
            },
          ],
          patterns: [
            {
              group: ['axios/*'],
              message:
                'Use shared/lib/apiClient. Direct axios subpath imports are forbidden.',
            },
          ],
        },
      ],
      // Přepisuje stejné pravidlo z bloku výše, proto znovu obsahuje i Web Storage.
      'no-restricted-globals': [
        'error',
        ...STORAGE_GLOBALS,
        {
          name: 'fetch',
          message:
            'Do not call fetch() directly. Use apiClient from shared/lib/apiClient.',
        },
      ],
    },
  },
  {
    // src/shared/api/generated: vygenerováno z src/contracts (npm run gen:contracts)
    ignores: ['dist/**', 'node_modules/**', 'src/**/*.js', '*.config.{js,ts}', 'src/shared/api/generated/**', 'scripts/**'],
  },
]
