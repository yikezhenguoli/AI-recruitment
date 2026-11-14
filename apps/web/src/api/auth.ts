import { API_PREFIX, api } from './client'
import type { AuthTokens, CurrentUser } from '../types'

export async function login(payload: {
  tenant_slug: string
  email: string
  password: string
}): Promise<AuthTokens> {
  const response = await api.post(`${API_PREFIX}/auth/login`, payload)
  return response.data as AuthTokens
}

export async function me(): Promise<CurrentUser> {
  const response = await api.get(`${API_PREFIX}/me`)
  return response.data as CurrentUser
}

export async function logout(refreshToken: string | null): Promise<void> {
  if (!refreshToken) return
  try {
    await api.post(`${API_PREFIX}/auth/logout`, { refresh_token: refreshToken })
  } catch {
    // 退出登录是本地行为；服务端令牌失效不应阻塞清理。
  }
}
