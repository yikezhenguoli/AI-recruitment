import { API_BASE, API_PREFIX } from './client'
import { getTokens } from '../lib/tokenStorage'

/** WebSocket 地址：开发走 Vite 代理，生产走同源。 */
export function buildWsUrl(path: string): string {
  if (API_BASE) {
    return `${API_BASE.replace(/^http/, 'ws')}${API_PREFIX}${path}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_PREFIX}${path}`
}

/**
 * 后端所有 WebSocket 都用「连上后第一帧发 {"token": ...}」鉴权，
 * 这里统一处理，调用方只需监听业务消息。
 */
export function openAuthedSocket(path: string): WebSocket {
  const socket = new WebSocket(buildWsUrl(path))
  socket.addEventListener('open', () => {
    const tokens = getTokens()
    if (tokens) {
      socket.send(JSON.stringify({ token: tokens.access_token }))
    }
  })
  return socket
}

/** Close codes the backend uses instead of an HTTP status. */
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
