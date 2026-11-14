import { accessToken } from '../store/authStore'
import type { TaskProgressEvent } from '../types'

export function taskSocketUrl(taskId: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}/api/v1/ws/progress/${taskId}`
}

/**
 * 订阅后端任务进度。连接后第一帧发送短期 access token（后端不允许把令牌
 * 放在 URL 里）。返回取消函数，组件卸载时务必调用。
 */
export function watchTask(
  taskId: string,
  handlers: {
    onEvent?: (event: TaskProgressEvent) => void
    onClose?: () => void
    onError?: (message: string) => void
  },
): () => void {
  const ws = new WebSocket(taskSocketUrl(taskId))
  let closed = false

  ws.onopen = () => {
    const token = accessToken()
    if (!token) {
      handlers.onError?.('登录已失效，无法订阅任务进度。')
      ws.close()
      return
    }
    ws.send(JSON.stringify({ token }))
  }

  ws.onmessage = (event) => {
    try {
      handlers.onEvent?.(JSON.parse(event.data) as TaskProgressEvent)
    } catch {
      handlers.onError?.('收到无法解析的任务进度消息。')
    }
  }

  ws.onerror = () => {
    if (!closed) handlers.onError?.('任务进度连接中断。')
  }

  ws.onclose = (event) => {
    if (closed) return
    if (event.code === 4401) {
      handlers.onError?.('任务进度鉴权失败，请重新登录。')
    } else if (event.code === 4403) {
      handlers.onError?.('无权查看该任务进度。')
    } else if (event.code === 4404) {
      handlers.onError?.('任务不存在。')
    }
    handlers.onClose?.()
  }

  return () => {
    closed = true
    try {
      ws.close()
    } catch {
      // ignore
    }
  }
}
