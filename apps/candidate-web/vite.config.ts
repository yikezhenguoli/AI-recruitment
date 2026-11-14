import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const certDir = fileURLToPath(new URL('./.certs/', import.meta.url))
const certFile = `${certDir}dev-cert.pem`
const keyFile = `${certDir}dev-key.pem`
// 手机走局域网 IP 访问时，http:// 不是安全上下文，浏览器不给麦克风。
// 用 scripts/make-dev-cert.sh 生成证书后，这里自动切到 https。
const https =
  existsSync(certFile) && existsSync(keyFile)
    ? { cert: readFileSync(certFile), key: readFileSync(keyFile) }
    : undefined

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    https,
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
