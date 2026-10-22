import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Dev server: prohlížeč mluví jen s `/bff/*` na stejném originu (NC-007 kap. 7).
 * `/bff` se proxuje na gateway (`VITE_BFF_PROXY_TARGET`, výchozí http://127.0.0.1:8090 = výchozí port gateway).
 * Proxy na `/api` záměrně neexistuje – core není z prohlížeče dosažitelné.
 *
 * Gateway v dev režimu potřebuje `NC_BFF_PUBLIC_ORIGIN` = origin dev serveru
 * (např. http://localhost:5173; hlavička Origin se proxy nepřepisuje) a
 * `NC_BFF_DEV_INSECURE_COOKIE=1` (cookie bez Secure přes http).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const bffTarget = env.VITE_BFF_PROXY_TARGET || 'http://127.0.0.1:8090'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        app: resolve(__dirname, 'src/app'),
        features: resolve(__dirname, 'src/features'),
        pages: resolve(__dirname, 'src/pages'),
        shared: resolve(__dirname, 'src/shared'),
        store: resolve(__dirname, 'src/store'),
      },
    },
    server: {
      proxy: {
        '/bff': {
          target: bffTarget,
          changeOrigin: false,
          ws: false,
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  }
})
