import axios from 'axios'

interface TtcErrorBody {
  code?: string
  message?: string
  request_id?: string
  details?: unknown
  detail?: unknown
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const record = item as { msg?: unknown; loc?: unknown }
          const loc = Array.isArray(record.loc)
            ? record.loc.filter((part) => part !== 'body').join('.')
            : ''
          return loc ? `${loc}：${String(record.msg ?? '')}` : String(record.msg ?? '')
        }
        return ''
      })
      .filter(Boolean)
    if (parts.length > 0) return parts.join('；')
  }
  return null
}

/**
 * 将 `/api/v1` 统一错误信封 `{code,message,request_id,details}`、FastAPI
 * 校验错误 `detail` 和网络错误转换为可读中文提示。
 */
export function getApiErrorMessage(
  error: unknown,
  fallback = '请求失败，请稍后重试。',
): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as TtcErrorBody | string | undefined
    if (body && typeof body === 'object') {
      if (typeof body.message === 'string' && body.message.trim()) {
        const code = body.code ? `${body.code} · ` : ''
        return `${code}${body.message}`
      }
      const fromDetail = detailMessage(body.detail)
      if (fromDetail) return fromDetail
    }
    if (typeof body === 'string' && body.trim()) return body

    if (error.code === 'ECONNABORTED') {
      return '请求超时，请检查后端服务或模型供应商状态。'
    }
    if (!error.response) {
      return '无法连接后端服务，请确认 TTC API 已在 http://127.0.0.1:8001 启动。'
    }
    return `请求失败（HTTP ${error.response.status}）。`
  }

  if (error instanceof Error && error.message) return error.message
  return fallback
}
