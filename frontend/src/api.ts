import axios from 'axios'

export interface SessionUser { id: string; tenant_id: string; role: string; display_name: string }
export interface Job { id: string; title: string; department: string | null; headcount: number | null; status: string; current_version_id: string | null; created_at: string; updated_at: string; current_version?: { jd_text: string } | null }
export interface Candidate { id: string; display_name: string; job_id: string | null; source: string; is_synthetic: boolean; created_at: string }
interface Tokens { access_token: string; refresh_token: string }

const key = 'ttc.session'
export const session = {
  get(): Tokens | null {
    try { return JSON.parse(sessionStorage.getItem(key) || 'null') as Tokens | null }
    catch { return null }
  },
  set(value: Tokens) { sessionStorage.setItem(key, JSON.stringify(value)) },
  clear() { sessionStorage.removeItem(key) },
}

export const api = axios.create({ baseURL: '/api/v1', timeout: 60000 })
api.interceptors.request.use(config => {
  const token = session.get()?.access_token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<Tokens> | null = null
api.interceptors.response.use(response => response, async error => {
  const request = error.config
  if (error.response?.status === 401 && request && !request._retry &&
      !String(request.url).includes('/auth/') && session.get()?.refresh_token) {
    request._retry = true
    try {
      refreshing ??= axios.post<Tokens>('/api/v1/auth/refresh', {
        refresh_token: session.get()!.refresh_token,
      }).then(response => response.data).finally(() => { refreshing = null })
      const tokens = await refreshing
      session.set(tokens)
      request.headers.Authorization = `Bearer ${tokens.access_token}`
      return api(request)
    } catch { session.clear() }
  }
  if (error.response?.status === 401 && !session.get()) {
    if (location.pathname !== '/login') location.assign('/login')
  }
  return Promise.reject(error)
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) return error.response?.data?.message || error.message || '请求失败'
  return '请求失败，请稍后重试'
}

export async function logout() {
  const token = session.get()?.refresh_token
  if (token) {
    try { await api.post('/auth/logout', { refresh_token: token }) }
    finally { session.clear() }
  }
}
