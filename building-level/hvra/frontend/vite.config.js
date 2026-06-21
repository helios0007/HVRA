import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
  },
  optimizeDeps: {
    // Prevent Vite from pre-bundling these — they use dynamic WASM imports
    exclude: ['@thatopen/components', 'web-ifc'],
  },
  assetsInclude: ['**/*.wasm'],
})
