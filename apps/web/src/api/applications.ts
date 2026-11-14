import { API_PREFIX, api } from './client'
import type { ApplicationItem } from '../types'

export async function listApplications(params: {
  job_id?: string
  status?: string
  limit?: number
} = {}): Promise<ApplicationItem[]> {
  const response = await api.get(`${API_PREFIX}/applications`, { params })
  return response.data.items as ApplicationItem[]
}
