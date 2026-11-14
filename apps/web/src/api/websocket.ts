import { accessToken } from '../store/authStore'

/**
 * WebSocket 工厂。
 *
 * 后端所有 WS 都要求连接后先发送 `{"token": "<access_token>"}`（10 秒内），
 * 不在 URL 里放令牌。默认走同源 Vite 代理；部署时可用 VITE_WS_URL 指定
 * 独立的 WS origin（例如 wss://api.example.com）。
 */

export function websocketBase(): string {
  const configured = import.meta.env.VITE_WS_URL
  if (configured) return configured.replace(/\/$/, '')
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const { hostname, port } = window.location
  // 本机 Vite 在部分 Windows 环境下只对 localhost(::1) 完成 WS upgrade；
  // 页面若以 127.0.0.1 打开，WS 也统一走 localhost，避免代理握手超时。
  const host =
    hostname === '127.0.0.1' || hostname === '[::1]'
      ? `localhost${port ? `:${port}` : ''}`
      : window.location.host
  return `${protocol}//${host}`
}

export function websocketUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${websocketBase()}${normalized}`
}

/**
 * 建立需要鉴权的 WebSocket，并在 onopen 后立即发送令牌。
 * 调用方负责 close() 与消息处理。
 */
export function openAuthenticatedSocket(path: string): WebSocket {
  const socket = new WebSocket(websocketUrl(path))
  socket.addEventListener(
    'open',
    () => {
      const token = accessToken()
      if (token) {
        socket.send(JSON.stringify({ token }))
      } else {
        socket.close(4401, 'missing access token')
      }
    },
    { once: true },
  )
  return socket
}

export function openProgressSocket(taskId: string): WebSocket {
  return openAuthenticatedSocket(`/api/v1/ws/progress/${taskId}`)
}

export function openVoiceStatusSocket(sessionId: string): WebSocket {
  return openAuthenticatedSocket(`/api/v1/ws/voice/${sessionId}`)
}

export function openVoiceRealtimeSocket(sessionId: string): WebSocket {
  return openAuthenticatedSocket(`/api/v1/voice-sessions/${sessionId}/realtime`)
}
