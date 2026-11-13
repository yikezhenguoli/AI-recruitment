import { api } from './client'
import type { Me, RegisterResponse, Tokens } from './types'

export async function login(payload: {
  tenant_slug: string
  email: string
  password: string
}): Promise<Tokens> {
  const response = await api.post<Tokens>('/auth/login', payload)
  return response.data
}

export async function register(payload: {
  tenant_slug: string
  email: string
  password: string
  display_name: string
}): Promise<RegisterResponse> {
  const response = await api.post<RegisterResponse>('/portal/register', payload)
  return response.data
}

export async function fetchMe(): Promise<Me> {
  const response = await api.get<Me>('/me')
  return response.data
}

export async function logout(refreshToken: string): Promise<void> {
  await api.post('/auth/logout', { refresh_token: refreshToken })
}
