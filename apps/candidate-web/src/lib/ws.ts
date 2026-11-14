import { API_BASE } from '../api/client'
import { getAccessToken } from './tokenStorage'

/** 开发环境走 Vite 的 /api 代理，生产环境走同源。 */
export function buildWsUrl(path: string): string {
  if (/^https?:/.test(API_BASE)) {
    return `${API_BASE.replace(/^http/, 'ws')}${path}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_BASE}${path}`
}

/** 后端 WebSocket 统一用「连上后第一帧发 {"token": ...}」鉴权。 */
export function openAuthedSocket(path: string): WebSocket {
  const socket = new WebSocket(buildWsUrl(path))
  socket.addEventListener('open', () => {
    const token = getAccessToken()
    if (token) socket.send(JSON.stringify({ token }))
  })
  return socket
}

export function describeSocketClose(code: number): string {
  switch (code) {
    case 4401:
      return '登录状态已失效，请重新登录。'
    case 4403:
      return '当前账号无权访问该连接。'
    case 4404:
      return '会话或任务不存在。'
    case 4409:
      return '会话已被占用、授权已撤回或已结束。'
    default:
      return `连接已断开（${code}）。`
  }
}
