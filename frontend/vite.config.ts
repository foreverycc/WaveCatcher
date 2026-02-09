import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0", // Listen on all network interfaces
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000', // Proxy to backend
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
