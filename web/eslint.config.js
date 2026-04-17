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
 */

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
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message:
            'Do not call fetch() directly. Use apiClient from shared/lib/apiClient.',
        },
      ],
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', 'src/**/*.js', '*.config.{js,ts}'],
  },
]
