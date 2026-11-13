import axios from 'axios'

interface ApiErrorBody {
  code?: string
  message?: string
  request_id?: string
  details?: unknown
}

/** Pull the backend's `{code,message}` envelope out of any thrown value. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const body = error.response?.data as ApiErrorBody | undefined
    if (body?.message) {
      return body.code ? `${body.message}（${body.code}）` : body.message
    }
    if (status === 401) return '登录已失效，请重新登录。'
    if (status === 403) return '没有访问该资源的权限。'
    if (status === 404) return '资源不存在。'
    if (status === 413) return '文件超过 20 MB 限制。'
    if (status === 415) return '文件格式不受支持，请上传 PDF、DOCX 或 TXT。'
    if (status === 422) return '提交的内容未通过校验，请检查后重试。'
    if (status && status >= 500) return '服务暂时不可用，请稍后重试。'
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试。'
    return error.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}
