import { API_BASE } from './client'

export function getExportUrl(sessionId: string): string {
  return `${API_BASE}/api/export/${sessionId}`
}
