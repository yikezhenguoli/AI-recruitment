import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { HealthResponse } from '../types'
import { clearTokens, getTokens, setTokens, type Tokens } from '../lib/tokenStorage'

/**
 * Single Axios instance for the HR workbench.
 *
 * In local development VITE_API_BASE_URL is empty and Vite proxies /api and /ws
 * to http://localhost:8000. In deployment, set VITE_API_BASE_URL to the backend
 * origin.
 */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = configuredBaseUrl.replace(/\/$/, '')

export const API_PREFIX = '/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const tokens = getTokens()
  if (tokens && !config.url?.startsWith('/auth/')) {
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  return config
})

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

let refreshing: Promise<Tokens> | null = null

async function refreshTokens(): Promise<Tokens> {
  const tokens = getTokens()
  if (!tokens) throw new Error('no refresh token')
  const response = await axios.post<Tokens>(
    `${API_BASE}${API_PREFIX}/auth/refresh`,
    { refresh_token: tokens.refresh_token },
    { timeout: 15_000 },
  )
  const next = response.data
  setTokens(next)
  return next
}

function redirectToLogin(): void {
  clearTokens()
  if (window.location.pathname !== '/login') {
    const next = `${window.location.pathname}${window.location.search}`
    window.location.assign(`/login?next=${encodeURIComponent(next)}`)
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status
    const url = config?.url ?? ''
    const isAuthCall = url.startsWith('/auth/') || url.includes(`${API_PREFIX}/auth/`)

    if (status === 401 && config && !config._retried && !isAuthCall && getTokens()) {
      config._retried = true
      try {
        refreshing ??= refreshTokens().finally(() => {
          refreshing = null
        })
        const tokens = await refreshing
        config.headers.Authorization = `Bearer ${tokens.access_token}`
        return api(config)
      } catch {
        redirectToLogin()
        return Promise.reject(error)
      }
    }

    if (status === 401 && !isAuthCall) {
      redirectToLogin()
    }

    return Promise.reject(error)
  },
)

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get(`${API_PREFIX}/health/ready`, { timeout: 5_000 })
  return response.data as HealthResponse
}
