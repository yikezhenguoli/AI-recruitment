import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 本地新后端默认跑在 8001（8000 可能被旧 AI AFS 进程占用）。
// 可通过 VITE_DEV_API_TARGET 覆盖，例如 http://127.0.0.1:8000。
const target = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
        ws: true,
      },
      // 兼容旧标签页/旧缓存模块对 `/health` 的请求。
      // 新前端统一使用 `/api/v1/health/live` 与 `/api/v1/health/ready`。
      '/health': {
        target,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/health/, '/api/v1/health/live'),
      },
    },
  },
})
