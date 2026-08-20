import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Experimental UI — separate from JM FX desk (/fx/)
// Production: https://jmtechsolution.cloud/lab/
export default defineConfig({
  base: process.env.JM_LAB_BASE || '/lab/',
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/fx/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
