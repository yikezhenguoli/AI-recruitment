import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, FileText, Plus, RefreshCw, Send, XCircle } from 'lucide-react'
import { listApplications } from '../api/applications'
import {
  createOffer,
  getOffer,
  listOffers,
  recordDecision,
  sendOffer,
  withdrawOffer,
} from '../api/offers'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { OfferStatus } from '../types'

const STATUS_LABEL: Record<OfferStatus, string> = {
  draft: '草稿',
  sent: '已发送',
  accepted: '已接受',
  declined: '已拒绝',
  withdrawn: '已撤回',
  expired: '已过期',
}

const STATUS_CLASS: Record<OfferStatus, string> = {
  draft: 'ttc-badge-amber',
  sent: 'ttc-badge-blue',
  accepted: 'ttc-badge-green',
  declined: 'ttc-badge-red',
  withdrawn: 'ttc-badge-red',
  expired: 'ttc-badge-red',
}

function formatSalary(value: string | number | null, months: number | null): string {
  if (value === null || value === '') return '薪资待定'
  const monthly = Number(value)
  if (!Number.isFinite(monthly)) return '薪资待定'
  const text = `¥${monthly.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}/月`
  return months ? `${text} × ${months} 个月` : text
}

export default function OffersPage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<'all' | OfferStatus>('all')
  const [formOpen, setFormOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [salary, setSalary] = useState('')
  const [months, setMonths] = useState('12')
  const [startDate, setStartDate] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [note, setNote] = useState('')

  const offersQuery = useQuery({
    queryKey: ['offers', status],
    queryFn: () => listOffers(status === 'all' ? {} : { status }),
  })
  const applicationsQuery = useQuery({
    queryKey: ['applications', 'for-offer'],
    queryFn: () => listApplications({ limit: 200 }),
  })
  const detailQuery = useQuery({
    queryKey: ['offer', selected],
    queryFn: () => getOffer(selected as string),
    enabled: Boolean(selected),
  })

  const availableApplications = (applicationsQuery.data ?? []).filter(
    (item) => !item.offer_id || item.offer_id === selected,
  )

  const refresh = () => {
    void offersQuery.refetch()
    void applicationsQuery.refetch()
    if (selected) void detailQuery.refetch()
  }

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['offers'] })
    void queryClient.invalidateQueries({ queryKey: ['applications'] })
    void queryClient.invalidateQueries({ queryKey: ['offer'] })
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createOffer({
        application_id: applicationId,
        salary_monthly: salary === '' ? undefined : salary,
        salary_months: months === '' ? undefined : Number(months),
        start_date: startDate || undefined,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
        note: note || undefined,
      }),
    onSuccess: (offer) => {
      setError('')
      setFormOpen(false)
      setApplicationId('')
      setSalary('')
      setNote('')
      setSelected(offer.id)
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建 Offer 失败。')),
  })

  const actionMutation = useMutation({
    mutationFn: async (action: { type: 'send' | 'withdraw' | 'accept' | 'decline'; id: string }) => {
      if (action.type === 'send') return sendOffer(action.id)
      if (action.type === 'withdraw') return withdrawOffer(action.id)
      return recordDecision(action.id, action.type === 'accept' ? 'accepted' : 'declined',
        '招聘方代录')
    },
    onSuccess: () => {
      setError('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '操作失败。')),
  })

  const offers = offersQuery.data ?? []
  const detail = detailQuery.data

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            OFFER CENTER
            <span className="hero-eyebrow-line" />
            <span>DECISION</span>
          </div>
          <h1>Offer 管理</h1>
          <p>草稿 → 发送 → 候选人接受/拒绝；每一步留痕，终态不可再改。</p>
        </div>
        <div className="ttc-heading-actions">
          <button type="button" className="ttc-btn ttc-btn-secondary" onClick={refresh}>
            <RefreshCw size={15} className={offersQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            onClick={() => setFormOpen((value) => !value)}
          >
            <Plus size={16} />
            新建 Offer
          </button>
        </div>
      </section>

      {error && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>操作未完成</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {formOpen && (
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">新建 Offer 草稿</h2>
              <p className="ttc-card-sub">选择一条投递；同一投递只能有一份 Offer。</p>
            </div>
            <FileText size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-launch-form">
            <label className="ttc-login-field">
              <span>投递</span>
              <select value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>
                <option value="">请选择投递</option>
                {availableApplications.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.candidate_name} · {item.job_title}
                  </option>
                ))}
              </select>
            </label>
            <label className="ttc-login-field">
              <span>月薪（元）</span>
              <input value={salary} onChange={(event) => setSalary(event.target.value)}
                inputMode="decimal" placeholder="18000" />
            </label>
            <label className="ttc-login-field">
              <span>发薪月数</span>
              <input value={months} onChange={(event) => setMonths(event.target.value)}
                inputMode="numeric" placeholder="12" />
            </label>
            <label className="ttc-login-field">
              <span>入职日期</span>
              <input type="date" value={startDate}
                onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <label className="ttc-login-field">
              <span>有效期至</span>
              <input type="datetime-local" value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)} />
            </label>
            <label className="ttc-login-field">
              <span>备注</span>
              <input value={note} onChange={(event) => setNote(event.target.value)}
                placeholder="给候选人看的补充说明" />
            </label>
          </div>
          <div className="ttc-card-actions">
            <button
              type="button"
              className="ttc-btn ttc-btn-primary"
              disabled={!applicationId || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? '创建中…' : '创建草稿'}
            </button>
          </div>
        </article>
      )}

      <div className="ttc-filter-chips">
        {(
          [
            ['all', '全部'],
            ['draft', '草稿'],
            ['sent', '已发送'],
            ['accepted', '已接受'],
            ['declined', '已拒绝'],
            ['withdrawn', '已撤回'],
            ['expired', '已过期'],
          ] as const
        ).map(([value, label]) => (
          <button key={value} type="button"
            className={`ttc-chip ${status === value ? 'ttc-chip-blue' : ''}`}
            onClick={() => setStatus(value)}>
            {label}
          </button>
        ))}
      </div>

      {offersQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取 Offer 列表</strong>
            <span>{getApiErrorMessage(offersQuery.error, '请确认后端服务已启动。')}</span>
          </div>
        </div>
      )}

      <div className="ttc-table-scroll">
        <table className="ttc-result-table">
          <thead>
            <tr>
              <th>候选人</th>
              <th>岗位</th>
              <th>薪资</th>
              <th>状态</th>
              <th>有效期</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {offers.map((offer) => (
              <tr key={offer.id}>
                <td>
                  <button type="button" className="ttc-link-btn" onClick={() => setSelected(offer.id)}>
                    {offer.candidate_name}
                  </button>
                </td>
                <td>{offer.position_title}</td>
                <td className="ttc-muted">{formatSalary(offer.salary_monthly, offer.salary_months)}</td>
                <td>
                  <span className={`ttc-badge ${STATUS_CLASS[offer.status]}`}>
                    {STATUS_LABEL[offer.status]}
                  </span>
                </td>
                <td className="ttc-muted">
                  {offer.expires_at ? formatDateTime(offer.expires_at) : '未设置'}
                </td>
                <td>
                  <div className="ttc-card-actions">
                    {offer.status === 'draft' && (
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ type: 'send', id: offer.id })}>
                        <Send size={14} /> 发送
                      </button>
                    )}
                    {(offer.status === 'draft' || offer.status === 'sent') && (
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ type: 'withdraw', id: offer.id })}>
                        <XCircle size={14} /> 撤回
                      </button>
                    )}
                    {offer.status === 'sent' && (
                      <>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => actionMutation.mutate({ type: 'accept', id: offer.id })}>
                          代录接受
                        </button>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => actionMutation.mutate({ type: 'decline', id: offer.id })}>
                          代录拒绝
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!offersQuery.isLoading && offers.length === 0 && (
              <tr>
                <td colSpan={6} className="ttc-muted">
                  还没有 Offer。点右上角「新建 Offer」从一条投递开始。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">Offer 事件流</h2>
              <p className="ttc-card-sub">
                {detail ? `${detail.candidate_name} · ${detail.position_title}` : '读取中…'}
              </p>
            </div>
            <FileText size={18} className="ttc-accent-icon" />
          </div>
          {detailQuery.isError && (
            <p className="ttc-muted">{getApiErrorMessage(detailQuery.error, '无法读取事件流。')}</p>
          )}
          <div className="ttc-consent-list">
            {(detail?.events ?? []).map((event) => (
              <div key={event.id} className="ttc-consent-row">
                <div>
                  <strong>
                    {event.from_status ? `${event.from_status} → ` : ''}
                    {event.to_status}
                  </strong>
                  <span className="ttc-muted">{event.note ?? '—'}</span>
                </div>
                <span className="ttc-muted">{formatDateTime(event.created_at)}</span>
              </div>
            ))}
            {detail && detail.events.length === 0 && <p className="ttc-muted">暂无事件。</p>}
          </div>
          <div className="ttc-card-actions">
            <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => setSelected(null)}>
              关闭
            </button>
          </div>
        </article>
      )}
    </div>
  )
}
