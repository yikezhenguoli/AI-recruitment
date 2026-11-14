import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import type { HealthStatus } from '../types'
import {
  accessToken,
  clearAuth,
  refreshToken,
  useAuthStore,
} from '../store/authStore'

/**
 * 单一 Axios 实例，指向 TTC `/api/v1`。
 *
 * 本地开发时 VITE_API_BASE_URL 为空，Vite 将 `/api`、`/health` 代理到 8001；
 * 部署时设置 VITE_API_BASE_URL 为后端 origin。
 */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = configuredBaseUrl.replace(/\/$/, '')
export const API_PREFIX = '/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
})

api.interceptors.request.use((config) => {
  const token = accessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const token = refreshToken()
  if (!token) return null
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(
        `${API_BASE}${API_PREFIX}/auth/refresh`,
        { refresh_token: token },
        { timeout: 15_000 },
      )
      .then((response) => {
        const tokens = response.data
        useAuthStore.getState().setTokens(tokens)
        return tokens.access_token as string
      })
      .catch(() => {
        clearAuth()
        return null
      })
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & {
      _ttcRetried?: boolean
    }) | undefined
    const status = error.response?.status
    const url = original?.url ?? ''

    if (
      status === 401 &&
      original &&
      !original._ttcRetried &&
      !url.includes('/auth/login') &&
      !url.includes('/auth/refresh') &&
      refreshToken()
    ) {
      original._ttcRetried = true
      const next = await refreshAccessToken()
      if (next) {
        original.headers = original.headers ?? {}
        original.headers.Authorization = `Bearer ${next}`
        return api(original)
      }
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export async function getHealth(): Promise<HealthStatus> {
  const response = await api.get(`${API_PREFIX}/health/live`, { timeout: 5_000 })
  return response.data as HealthStatus
}

export async function getReadiness(): Promise<HealthStatus> {
  const response = await api.get(`${API_PREFIX}/health/ready`, { timeout: 5_000 })
  return response.data as HealthStatus
}
