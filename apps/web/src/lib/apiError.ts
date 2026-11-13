import axios from 'axios'

/** Convert backend/network failures into a readable message for the UI. */
export function getApiErrorMessage(
  error: unknown,
  fallback = '请求失败，请稍后重试。',
): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail

    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg)
          }
          return ''
        })
        .filter(Boolean)
      if (messages.length > 0) return messages.join('；')
    }

    if (error.code === 'ECONNABORTED') {
      return '请求超时，请检查后端服务或模型供应商状态。'
    }

    if (!error.response) {
      return '无法连接后端服务，请确认 apps/api 已在 http://localhost:8000 启动。'
    }

    return `请求失败（HTTP ${error.response.status}）。`
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return fallback
}
