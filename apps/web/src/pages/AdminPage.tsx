import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Database,
  HardDriveDownload,
  Plug,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Users,
} from 'lucide-react'
import {
  createBackup,
  enableCrossref,
  getIntegrations,
  getMetrics,
  listAuditLogs,
  listBackups,
  listDataSources,
  restoreBackup,
  updateDataSource,
  verifyBackup,
} from '../api/admin'
import { listCandidates } from '../api/candidates'
import { listConsents } from '../api/consents'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'

const TASK_STATUS_LABEL: Record<string, string> = {
  queued: '排队',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  canceled: '已取消',
}

export default function AdminPage() {
  const queryClient = useQueryClient()
  const [candidateId, setCandidateId] = useState('')
  const [error, setError] = useState('')

  const metricsQuery = useQuery({ queryKey: ['adminMetrics'], queryFn: getMetrics, retry: false })
  const sourcesQuery = useQuery({
    queryKey: ['adminSources'],
    queryFn: listDataSources,
    retry: false,
  })
  const auditQuery = useQuery({
    queryKey: ['adminAudit'],
    queryFn: () => listAuditLogs(50),
    retry: false,
  })
  const integrationsQuery = useQuery({
    queryKey: ['integrations'],
    queryFn: getIntegrations,
    retry: false,
  })
  const candidatesQuery = useQuery({ queryKey: ['candidates'], queryFn: () => listCandidates() })
  const effectiveCandidateId = candidateId || candidatesQuery.data?.[0]?.id || ''
  const consentsQuery = useQuery({
    queryKey: ['consents', effectiveCandidateId],
    queryFn: () => listConsents(effectiveCandidateId),
    enabled: Boolean(effectiveCandidateId),
  })
  const backupsQuery = useQuery({
    queryKey: ['backups'],
    queryFn: listBackups,
    retry: false,
  })

  const [backupNote, setBackupNote] = useState('')

  const invalidateBackups = () => {
    void queryClient.invalidateQueries({ queryKey: ['backups'] })
  }

  const createBackupMutation = useMutation({
    mutationFn: createBackup,
    onSuccess: (snapshot) => {
      setBackupNote(
        `快照已生成：${snapshot.id.slice(0, 8)}… · ` +
          `${Object.values(snapshot.table_counts).reduce((sum, value) => sum + value, 0)} 行 · ` +
          `${(snapshot.size_bytes / 1024).toFixed(1)} KB。${snapshot.note}`,
      )
      invalidateBackups()
    },
    onError: (err) => setBackupNote(getApiErrorMessage(err, '创建备份失败。')),
  })

  const verifyBackupMutation = useMutation({
    mutationFn: verifyBackup,
    onSuccess: (report) => {
      setBackupNote(
        report.ok
          ? `校验一致：${Object.keys(report.tables).length} 张表，结构无差异。`
          : `校验发现问题：${report.problems.join('；')}`,
      )
    },
    onError: (err) => setBackupNote(getApiErrorMessage(err, '校验备份失败。')),
  })

  const restoreBackupMutation = useMutation({
    mutationFn: (snapshotId: string) => restoreBackup(snapshotId, true),
    onSuccess: (report) => {
      setBackupNote(
        report.ok
          ? '恢复演练通过（dry_run，未写入数据库）。真实写入需要管理员二次确认。'
          : `演练发现问题：${report.problems.join('；')}`,
      )
    },
    onError: (err) => setBackupNote(getApiErrorMessage(err, '恢复演练失败。')),
  })

  const source = sourcesQuery.data?.[0]

  const toggleSource = useMutation({
    mutationFn: async () => {
      if (!source) return null
      if (!source.id) return enableCrossref()
      return updateDataSource(source.id, { enabled: !source.enabled })
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['adminSources'] }),
    onError: (err) => setError(getApiErrorMessage(err, '更新数据源失败。')),
  })

  const rateLimit = useMutation({
    mutationFn: (value: number) => updateDataSource(source!.id!, { rate_limit: value }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['adminSources'] }),
    onError: (err) => setError(getApiErrorMessage(err, '更新限流失败。')),
  })

  const anyError =
    metricsQuery.error ?? sourcesQuery.error ?? auditQuery.error ?? integrationsQuery.error

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            GOVERNANCE
            <span className="hero-eyebrow-line" />
            <span>ADMIN</span>
          </div>
          <h1>管理后台</h1>
          <p>租户级指标、审计留痕、数据源开关与外部集成状态；仅管理员可访问核心接口。</p>
        </div>
        <div className="ttc-heading-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => {
              void metricsQuery.refetch()
              void sourcesQuery.refetch()
              void auditQuery.refetch()
              void integrationsQuery.refetch()
            }}
          >
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </section>

      {anyError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>部分治理接口不可用</strong>
            <span>{getApiErrorMessage(anyError, '当前账号可能没有管理员权限。')}</span>
          </div>
        </div>
      )}

      <div className="ttc-kpi-grid">
        {Object.entries(metricsQuery.data?.tasks ?? {}).map(([status, count]) => (
          <article key={status} className="ttc-card ttc-kpi-card">
            <div className="ttc-kpi-top">
              <span className="ttc-kpi-icon ttc-kpi-icon-blue">
                <Database size={16} />
              </span>
              <span>{TASK_STATUS_LABEL[status] ?? status}任务</span>
            </div>
            <strong className="ttc-kpi-value">{count}</strong>
          </article>
        ))}
        {!metricsQuery.data && metricsQuery.isLoading && (
          <div className="ttc-card ttc-skeleton-card" />
        )}
      </div>

      <div className="ttc-detail-grid">
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">数据源</h2>
              <p className="ttc-card-sub">当前只接 Crossref，限流按租户计算。</p>
            </div>
            <Database size={18} className="ttc-accent-icon" />
          </div>
          {source ? (
            <div className="ttc-source-row">
              <div>
                <strong>{source.name}</strong>
                <span className="ttc-muted">
                  {source.enabled ? '已启用' : '已停用'} · 每分钟上限 {source.rate_limit}
                </span>
              </div>
              <div className="ttc-card-actions">
                <button
                  type="button"
                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                  disabled={toggleSource.isPending}
                  onClick={() => toggleSource.mutate()}
                >
                  {source.enabled ? '停用' : '启用'}
                </button>
                {source.id && (
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={rateLimit.isPending}
                    onClick={() => rateLimit.mutate(source.rate_limit >= 60 ? 30 : 60)}
                  >
                    切换限流
                  </button>
                )}
              </div>
            </div>
          ) : (
            <p className="ttc-muted">读取中或没有权限。</p>
          )}
        </article>

        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">外部集成</h2>
              <p className="ttc-card-sub">未实现的集成会明确显示 not_implemented。</p>
            </div>
            <Plug size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-integration-list">
            {Object.entries(integrationsQuery.data ?? {}).map(([name, value]) => (
              <div key={name} className="ttc-integration-row">
                <strong>{name}</strong>
                <span className="ttc-muted">{value.status}</span>
                <span className={`ttc-badge ${value.configured ? 'ttc-badge-blue' : 'ttc-badge-amber'}`}>
                  {value.configured ? '已配置' : '未配置'}
                </span>
              </div>
            ))}
            {!integrationsQuery.data && <p className="ttc-muted">读取中…</p>}
          </div>
        </article>
      </div>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">授权记录</h2>
            <p className="ttc-card-sub">按候选人查看授权与撤回历史。</p>
          </div>
          <Users size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-launch-form ttc-launch-form--compact">
          <label className="ttc-login-field">
            <span>候选人</span>
            <select value={effectiveCandidateId} onChange={(event) => setCandidateId(event.target.value)}>
              <option value="">请选择候选人</option>
              {(candidatesQuery.data ?? []).map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="ttc-consent-list">
          {(consentsQuery.data ?? []).map((consent) => (
            <div key={consent.id} className="ttc-consent-row">
              <div>
                <strong>{consent.purpose}</strong>
                <span className="ttc-muted">{formatDateTime(consent.accepted_at)}</span>
              </div>
              <span
                className={`ttc-badge ${
                  consent.status === 'granted' ? 'ttc-badge-green' : 'ttc-badge-red'
                }`}
              >
                {consent.status === 'granted' ? '已授权' : '已撤回'}
              </span>
            </div>
          ))}
          {effectiveCandidateId && (consentsQuery.data ?? []).length === 0 && (
            <p className="ttc-muted">该候选人没有授权记录。</p>
          )}
        </div>
      </article>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">备份快照</h2>
            <p className="ttc-card-sub">
              租户级数据库逻辑快照；不含简历原件与录音，且只做 UPSERT 恢复。
            </p>
          </div>
          <div className="ttc-card-actions">
            <button type="button" className="ttc-btn ttc-btn-primary ttc-btn-sm"
              disabled={createBackupMutation.isPending}
              onClick={() => createBackupMutation.mutate()}>
              <ShieldCheck size={14} />
              {createBackupMutation.isPending ? '生成中…' : '立即备份'}
            </button>
            <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => void backupsQuery.refetch()}>
              <RefreshCw size={14} />
              刷新
            </button>
            <HardDriveDownload size={18} className="ttc-accent-icon" aria-hidden="true" />
          </div>
        </div>
        {backupNote && (
          <p className="ttc-muted" style={{ fontSize: 12, marginBottom: 10 }}>
            {backupNote}
          </p>
        )}
        <div className="ttc-table-scroll">
          <table className="ttc-result-table">
            <thead>
              <tr>
                <th>快照</th>
                <th>行数</th>
                <th>体积</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {(backupsQuery.data ?? []).map((snapshot) => (
                <tr key={snapshot.id}>
                  <td>
                    <span className="ttc-muted">{snapshot.id.slice(0, 8)}…</span>
                  </td>
                  <td className="ttc-muted">
                    {Object.values(snapshot.table_counts).reduce((sum, value) => sum + value, 0)}
                  </td>
                  <td className="ttc-muted">{(snapshot.size_bytes / 1024).toFixed(1)} KB</td>
                  <td className="ttc-muted">{formatDateTime(snapshot.created_at)}</td>
                  <td>
                    <div className="ttc-card-actions">
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={verifyBackupMutation.isPending}
                        onClick={() => verifyBackupMutation.mutate(snapshot.id)}>
                        校验
                      </button>
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={restoreBackupMutation.isPending}
                        onClick={() => restoreBackupMutation.mutate(snapshot.id)}>
                        恢复演练
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!backupsQuery.isLoading && (backupsQuery.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="ttc-muted">
                    {backupsQuery.isError ? '没有备份管理权限或接口不可用。' : '还没有备份快照。'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </article>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">审计日志</h2>
            <p className="ttc-card-sub">最近 50 条租户操作留痕。</p>
          </div>
          <ScrollText size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-table-scroll">
          <table className="ttc-result-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>动作</th>
                <th>资源</th>
                <th>请求 ID</th>
              </tr>
            </thead>
            <tbody>
              {(auditQuery.data ?? []).map((log) => (
                <tr key={log.id}>
                  <td className="ttc-muted">{formatDateTime(log.created_at)}</td>
                  <td>{log.action}</td>
                  <td className="ttc-muted">
                    {log.resource_type}
                    {log.resource_id ? ` · ${log.resource_id.slice(0, 8)}` : ''}
                  </td>
                  <td className="ttc-muted">{log.request_id?.slice(0, 8) ?? '—'}</td>
                </tr>
              ))}
              {(auditQuery.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="ttc-muted">
                    没有审计记录。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  )
}
