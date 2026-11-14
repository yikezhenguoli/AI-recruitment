import { API_PREFIX, api } from './client'
import type {
  AdminMetrics,
  AuditLogItem,
  BackupCreateResult,
  BackupItem,
  BackupRestoreResult,
  BackupVerifyResult,
  DataSource,
  IntegrationsStatus,
} from '../types'

export async function listDataSources(): Promise<DataSource[]> {
  const response = await api.get(`${API_PREFIX}/admin/data-sources`)
  return response.data.items as DataSource[]
}

export async function enableCrossref(): Promise<DataSource> {
  const response = await api.post(`${API_PREFIX}/admin/data-sources/crossref`)
  return response.data as DataSource
}

export async function updateDataSource(
  sourceId: string,
  body: { enabled?: boolean; rate_limit?: number },
): Promise<DataSource> {
  const response = await api.patch(`${API_PREFIX}/admin/data-sources/${sourceId}`, body)
  return response.data as DataSource
}

export async function listAuditLogs(limit = 50): Promise<AuditLogItem[]> {
  const response = await api.get(`${API_PREFIX}/admin/audit-logs`, { params: { limit } })
  return response.data.items as AuditLogItem[]
}

export async function getMetrics(): Promise<AdminMetrics> {
  const response = await api.get(`${API_PREFIX}/admin/metrics`)
  return response.data as AdminMetrics
}

export async function getIntegrations(): Promise<IntegrationsStatus> {
  const response = await api.get(`${API_PREFIX}/integrations/status`)
  return response.data as IntegrationsStatus
}

export async function listBackups(): Promise<BackupItem[]> {
  const response = await api.get(`${API_PREFIX}/admin/backups`)
  return response.data.items as BackupItem[]
}

export async function createBackup(): Promise<BackupCreateResult> {
  const response = await api.post(`${API_PREFIX}/admin/backups`)
  return response.data as BackupCreateResult
}

export async function verifyBackup(snapshotId: string): Promise<BackupVerifyResult> {
  const response = await api.post(`${API_PREFIX}/admin/backups/${snapshotId}/verify`)
  return response.data as BackupVerifyResult
}

export async function restoreBackup(
  snapshotId: string,
  dryRun: boolean,
): Promise<BackupRestoreResult> {
  const response = await api.post(`${API_PREFIX}/admin/backups/${snapshotId}/restore`, {
    dry_run: dryRun,
    confirm: dryRun ? undefined : snapshotId,
  })
  return response.data as BackupRestoreResult
}
