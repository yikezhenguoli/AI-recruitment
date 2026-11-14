import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Database,
  FileClock,
  Gauge,
  Loader2,
  PlugZap,
  RefreshCw,
  Settings,
  ShieldCheck,
} from 'lucide-react'
import {
  enableCrossref,
  getIntegrationStatus,
  getTaskMetrics,
  listAuditLogs,
  listDataSources,
  updateDataSource,
} from '../api/admin'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useAuthStore } from '../store/authStore'

export default function AdminPage() {
  const role = useAuthStore((state) => state.user?.role)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const sourcesQuery = useQuery({
    queryKey: ['admin', 'data-sources'],
    queryFn: listDataSources,
    enabled: role === 'admin',
  })
  const metricsQuery = useQuery({
    queryKey: ['admin', 'metrics'],
    queryFn: getTaskMetrics,
    enabled: role === 'admin',
  })
  const auditQuery = useQuery({
    queryKey: ['admin', 'audit-logs'],
    queryFn: () => listAuditLogs(50),
    enabled: role === 'admin',
  })
  const integrationsQuery = useQuery({
    queryKey: ['integrations', 'status'],
    queryFn: getIntegrationStatus,
  })

  const updateMutation = useMutation({
    mutationFn: (payload: { id: string; enabled?: boolean; rate_limit?: number }) =>
      updateDataSource(payload.id, {
        enabled: payload.enabled,
        rate_limit: payload.rate_limit,
      }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['admin', 'data-sources'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '更新数据源失败。')),
  })

  const enableMutation = useMutation({
    mutationFn: enableCrossref,
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['admin', 'data-sources'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '启用 Crossref 失败。')),
  })

  if (role !== 'admin') {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>需要管理员权限</strong>
            <span>
              当前身份为 {role ?? '未知'}；`/api/v1/admin/*` 仅 admin 可访问。请使用
              admin@ttc.local 登录。
            </span>
          </div>
        </div>
      </div>
    )
  }

  const sources = sourcesQuery.data ?? []
  const metrics = metricsQuery.data
  const audit = auditQuery.data ?? []
  const integrations = integrationsQuery.data

  return (
    <div className="ttc-page">
      {error && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            GOVERNANCE
            <span className="hero-eyebrow-line" />
            <span>ADMIN / AUDIT / METRICS</span>
          </div>
          <h1>管理后台</h1>
          <p>数据源策略、审计日志、任务指标与集成状态均来自 `/api/v1` 管理员接口。</p>
        </div>
        <div className="ttc-heading-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => {
              void sourcesQuery.refetch()
              void metricsQuery.refetch()
              void auditQuery.refetch()
              void integrationsQuery.refetch()
            }}
          >
            <RefreshCw size={15} />
            刷新全部
          </button>
        </div>
      </section>

      <section className="ttc-kpi-grid">
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>数据源</span>
            <Database size={17} />
          </div>
          <strong className="ttc-kpi-value">{sources.length}</strong>
          <p className="ttc-kpi-hint">GET /admin/data-sources</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>任务总数</span>
            <Gauge size={17} />
          </div>
          <strong className="ttc-kpi-value">
            {metrics ? Object.values(metrics.tasks).reduce((sum, value) => sum + value, 0) : '—'}
          </strong>
          <p className="ttc-kpi-hint">GET /admin/metrics</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>审计记录</span>
            <FileClock size={17} />
          </div>
          <strong className="ttc-kpi-value">{audit.length}</strong>
          <p className="ttc-kpi-hint">GET /admin/audit-logs?limit=50</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>租户范围</span>
            <ShieldCheck size={17} />
          </div>
          <strong className="ttc-kpi-value">{metrics?.scope ?? 'tenant'}</strong>
          <p className="ttc-kpi-hint">所有查询按登录租户隔离</p>
        </article>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">数据源策略</h2>
              <p className="ttc-card-sub">Crossref 当前唯一受支持的公开来源</p>
            </div>
            <Settings size={18} className="ttc-accent-icon" />
          </div>
          {sourcesQuery.isLoading && <p className="ttc-muted">正在读取…</p>}
          {sources.map((source) => (
            <div className="ttc-source-row" key={source.name}>
              <div>
                <strong>{source.name}</strong>
                <span>
                  {source.id ? `ID ${source.id.slice(0, 8)}` : '尚未落库（使用默认策略）'}
                </span>
              </div>
              <label className="ttc-checkbox">
                <input
                  type="checkbox"
                  checked={source.enabled}
                  disabled={!source.id || updateMutation.isPending}
                  onChange={(event) =>
                    source.id &&
                    updateMutation.mutate({
                      id: source.id,
                      enabled: event.target.checked,
                    })
                  }
                />
                <span>启用</span>
              </label>
              <label className="ttc-rate-input">
                <span>限流 / 分钟</span>
                <input
                  type="number"
                  min={1}
                  max={300}
                  defaultValue={source.rate_limit}
                  disabled={!source.id || updateMutation.isPending}
                  onBlur={(event) =>
                    source.id &&
                    updateMutation.mutate({
                      id: source.id,
                      rate_limit: Number(event.target.value),
                    })
                  }
                />
              </label>
              {!source.id && (
                <button
                  type="button"
                  className="ttc-btn ttc-btn-primary ttc-btn-sm"
                  disabled={enableMutation.isPending}
                  onClick={() => enableMutation.mutate()}
                >
                  {enableMutation.isPending && (
                    <Loader2 size={13} className="animate-spin" />
                  )}
                  落库并启用
                </button>
              )}
            </div>
          ))}
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">任务指标</h2>
              <p className="ttc-card-sub">按 task.status 聚合</p>
            </div>
            <Gauge size={18} className="ttc-accent-icon" />
          </div>
          {metricsQuery.isLoading && <p className="ttc-muted">正在读取…</p>}
          <ul className="ttc-plain-list">
            {Object.entries(metrics?.tasks ?? {}).map(([status, count]) => (
              <li key={status}>
                <strong>{status}</strong>
                <span>{count} 个任务</span>
              </li>
            ))}
            {Object.keys(metrics?.tasks ?? {}).length === 0 && (
              <li>
                <strong>暂无任务</strong>
                <span>上传简历或提交证据检索后会出现。</span>
              </li>
            )}
          </ul>
        </article>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">集成状态</h2>
              <p className="ttc-card-sub">GET /integrations/status</p>
            </div>
            <PlugZap size={18} className="ttc-accent-icon" />
          </div>
          <ul className="ttc-plain-list">
            <li>
              <strong>OpenATS</strong>
              <span>
                {integrations?.openats.configured ? '已配置凭证' : '未配置'} ·{' '}
                {integrations?.openats.status ?? '未知'}
              </span>
            </li>
            <li>
              <strong>Vekt</strong>
              <span>
                {integrations?.vekt.configured ? '已配置凭证' : '未配置'} ·{' '}
                {integrations?.vekt.status ?? '未知'}
                {integrations?.vekt.fallback
                  ? ` · 回退 ${integrations.vekt.fallback}`
                  : ''}
              </span>
            </li>
          </ul>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">审计日志</h2>
              <p className="ttc-card-sub">最近 50 条 · 按 id 倒序</p>
            </div>
            <FileClock size={18} className="ttc-accent-icon" />
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
                {audit.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>{item.action}</td>
                    <td>
                      {item.resource_type}
                      {item.resource_id ? ` · ${item.resource_id.slice(0, 8)}` : ''}
                    </td>
                    <td>
                      <code>{item.request_id?.slice(0, 8) ?? '—'}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {auditQuery.isLoading && <p className="ttc-muted">正在读取审计日志…</p>}
          {!auditQuery.isLoading && audit.length === 0 && (
            <p className="ttc-muted">暂无审计记录。</p>
          )}
        </article>
      </section>
    </div>
  )
}
