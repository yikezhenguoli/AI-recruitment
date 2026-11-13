import type { Me } from '../api/types'

const ACCESS_KEY = 'ttc.careers.access'
const REFRESH_KEY = 'ttc.careers.refresh'
const USER_KEY = 'ttc.careers.user'

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY)
}

export function setTokens(accessToken: string, refreshToken: string): void {
  sessionStorage.setItem(ACCESS_KEY, accessToken)
  sessionStorage.setItem(REFRESH_KEY, refreshToken)
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(USER_KEY)
}

export function getStoredUser(): Me | null {
  const raw = sessionStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Me
  } catch {
    return null
  }
}

export function setStoredUser(user: Me): void {
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}
