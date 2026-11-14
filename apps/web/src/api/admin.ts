import { API_PREFIX, api } from './client'
import type {
  AuditLogItem,
  DataSource,
  IntegrationStatus,
  TaskMetrics,
} from '../types'

export async function listDataSources(): Promise<DataSource[]> {
  const response = await api.get(`${API_PREFIX}/admin/data-sources`)
  return response.data.items as DataSource[]
}

export async function updateDataSource(
  sourceId: string,
  payload: { enabled?: boolean; rate_limit?: number },
): Promise<DataSource> {
  const response = await api.patch(
    `${API_PREFIX}/admin/data-sources/${sourceId}`,
    payload,
  )
  return response.data as DataSource
}

export async function enableCrossref(): Promise<DataSource> {
  const response = await api.post(`${API_PREFIX}/admin/data-sources/crossref`)
  return response.data as DataSource
}

export async function listAuditLogs(limit = 50): Promise<AuditLogItem[]> {
  const response = await api.get(`${API_PREFIX}/admin/audit-logs`, {
    params: { limit },
  })
  return response.data.items as AuditLogItem[]
}

export async function getTaskMetrics(): Promise<TaskMetrics> {
  const response = await api.get(`${API_PREFIX}/admin/metrics`)
  return response.data as TaskMetrics
}

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  const response = await api.get(`${API_PREFIX}/integrations/status`)
  return response.data as IntegrationStatus
}
