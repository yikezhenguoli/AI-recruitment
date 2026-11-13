import { api, API_PREFIX } from './client'
import { clearTokens, getTokens, setTokens, type Tokens } from '../lib/tokenStorage'

export interface SessionUser {
  id: string
  tenant_id: string
  role: string
  display_name: string
}

export async function login(tenantSlug: string, email: string, password: string): Promise<Tokens> {
  const response = await api.post<Tokens>(`${API_PREFIX}/auth/login`, {
    tenant_slug: tenantSlug,
    email,
    password,
  })
  setTokens(response.data)
  return response.data
}

export async function fetchMe(): Promise<SessionUser> {
  const response = await api.get<SessionUser>(`${API_PREFIX}/me`)
  return response.data
}

export async function logout(): Promise<void> {
  const tokens = getTokens()
  try {
    if (tokens) {
      await api.post(`${API_PREFIX}/auth/logout`, { refresh_token: tokens.refresh_token })
    }
  } catch {
    // 退出失败不阻塞本地清理
  } finally {
    clearTokens()
  }
}

export const roleLabels: Record<string, string> = {
  hr: '招聘专员',
  admin: '管理员',
  candidate: '候选人',
}

export function roleLabel(role: string): string {
  return roleLabels[role] ?? '未知角色'
}
