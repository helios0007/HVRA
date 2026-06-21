import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    esbuildOptions: {
      target: 'esnext'
    },
    // @thatopen/components + web-ifc use dynamic WASM imports — don't pre-bundle.
    exclude: ['@thatopen/components', 'web-ifc'],
  },
  // web-ifc.wasm is fetched at runtime by ifcLoader.setup() (the 3D IFC viewer).
  assetsInclude: ['**/*.wasm'],
  server: {
    headers: {
      'Cross-Origin-Embedder-Policy': 'unsafe-none',
      'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    },
    // Building-level tool (teammate's FastAPI) runs as a second backend on
    // :8001. Proxying it through our dev server means the browser talks to one
    // origin (:5173) — no CORS change needed in her repo. Long pipeline runs
    // (2–5 min) so the proxy timeout is generous.
    proxy: {
      '/bapi': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        timeout: 600000,
        proxyTimeout: 600000,
        rewrite: (path) => path.replace(/^\/bapi/, ''),
      },
    },
  },
  build: {
    target: 'esnext'
  }
})
