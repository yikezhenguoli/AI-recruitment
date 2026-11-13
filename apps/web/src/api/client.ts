import axios from 'axios'
import type { HealthResponse } from '../types'

/**
 * Single Axios instance for the HR workbench.
 *
 * In local development VITE_API_BASE_URL is empty and Vite proxies /api,
 * /health and /ws to http://localhost:8000. In deployment, set
 * VITE_API_BASE_URL to the backend origin.
 */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = configuredBaseUrl.replace(/\/$/, '')

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
})

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get('/health', { timeout: 5_000 })
  return response.data as HealthResponse
}
