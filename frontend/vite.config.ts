import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend requests go to FastAPI in both `npm run dev` and `npm run serve`
const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8000', // Proxy to backend
    changeOrigin: true,
    secure: false,
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0", // Listen on all network interfaces
    port: 5173,
    proxy,
  },
  // `npm run serve`: the production build on the same address as dev, several times faster than dev mode
  preview: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    proxy,
  },
})
