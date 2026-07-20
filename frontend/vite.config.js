import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Production on JM TECH portal: https://jmtechsolution.cloud/fx/
// Local dev stays at /
export default defineConfig({
  base: process.env.JM_BASE || '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})