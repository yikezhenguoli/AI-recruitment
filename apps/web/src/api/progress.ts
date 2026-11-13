import { openAuthedSocket, describeSocketClose } from './ws'
import type { TaskProgressMessage } from '../types'

/**
 * 订阅后台任务进度。返回取消订阅函数。
 * 任务终态（succeeded/failed/canceled）时后端会主动关闭连接。
 */
export function watchTask(
  taskId: string,
  handlers: {
    onProgress: (message: TaskProgressMessage) => void
    onClose?: (reason: string) => void
  },
): () => void {
  const socket = openAuthedSocket(`/ws/progress/${taskId}`)
  let settled = false

  socket.addEventListener('message', (event) => {
    let data: TaskProgressMessage
    try {
      data = JSON.parse(String(event.data)) as TaskProgressMessage
    } catch {
      return
    }
    if (data.type === 'done' || data.type === 'error') settled = true
    handlers.onProgress(data)
  })

  socket.addEventListener('close', (event) => {
    if (!settled) handlers.onClose?.(describeSocketClose(event.code))
  })

  return () => {
    settled = true
    socket.close()
  }
}
