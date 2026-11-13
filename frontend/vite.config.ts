import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': { target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
})
