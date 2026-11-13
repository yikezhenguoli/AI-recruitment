import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Database, Plug, RefreshCw, ScrollText, Users } from 'lucide-react'
import {
  enableCrossref,
  getIntegrations,
  getMetrics,
  listAuditLogs,
  listDataSources,
  updateDataSource,
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
  const consentsQuery = useQuery({
    queryKey: ['consents', candidateId],
    queryFn: () => listConsents(candidateId),
    enabled: Boolean(candidateId),
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
        <div className="ttc-launch-form">
          <label className="ttc-login-field">
            <span>候选人</span>
            <select value={candidateId} onChange={(event) => setCandidateId(event.target.value)}>
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
          {candidateId && (consentsQuery.data ?? []).length === 0 && (
            <p className="ttc-muted">该候选人没有授权记录。</p>
          )}
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
