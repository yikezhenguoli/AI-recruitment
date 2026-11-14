import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '../lib/tokenStorage'
import type { Tokens } from './types'

const configuredOrigin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const API_BASE = `${configuredOrigin}/api/v1`

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

let refreshInFlight: Promise<string | null> | null = null

async function requestNewAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null
  try {
    // Bare axios: the refresh call must not re-enter the 401 interceptor.
    const response = await axios.post<Tokens>(
      `${API_BASE}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 15_000 },
    )
    setTokens(response.data.access_token, response.data.refresh_token)
    return response.data.access_token
  } catch {
    return null
  }
}

function expireSession(): void {
  clearTokens()
  window.dispatchEvent(new Event('ttc-careers:unauthorized'))
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetryableConfig | undefined
    const status = error.response?.status
    const url = config?.url ?? ''
    const isAuthCall = url.includes('/auth/login') || url.includes('/auth/refresh')

    if (status === 401 && config && !config._retry && !isAuthCall) {
      config._retry = true
      if (!refreshInFlight) {
        refreshInFlight = requestNewAccessToken().finally(() => {
          refreshInFlight = null
        })
      }
      const token = await refreshInFlight
      if (token) {
        config.headers = config.headers ?? {}
        config.headers.Authorization = `Bearer ${token}`
        return api.request(config)
      }
      expireSession()
    }

    return Promise.reject(error)
  },
)
