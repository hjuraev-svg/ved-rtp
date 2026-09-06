import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker the nginx container proxies /api and /ws to the api service.
// These proxies only apply to `npm run dev` on the host.
// VITE_BASE lets the same source serve from the site root (local: "/") or from
// a sub-path behind a shared reverse proxy (server: "/ved/"). Every request the
// app makes is prefixed with it — see BASE in src/api.ts.
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
