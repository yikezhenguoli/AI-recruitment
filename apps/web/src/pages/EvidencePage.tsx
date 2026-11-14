import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  BadgeCheck,
  ExternalLink,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
} from 'lucide-react'
import { getCandidate } from '../api/candidates'
import { listEvidence, searchEvidence, confirmEvidence } from '../api/evidence'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'

export default function EvidencePage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const candidateId = id ?? ''
  const jobId = searchParams.get('job') || ''
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const candidateQuery = useQuery({
    queryKey: ['candidate', candidateId],
    queryFn: () => getCandidate(candidateId),
    enabled: Boolean(candidateId),
  })
  const evidenceQuery = useQuery({
    queryKey: ['candidate', candidateId, 'evidence'],
    queryFn: () => listEvidence(candidateId),
    enabled: Boolean(candidateId),
  })

  const searchMutation = useMutation({
    mutationFn: () => searchEvidence(candidateId, { sources: ['crossref'] }),
    onSuccess: (result) => {
      setError(null)
      setMessage(
        `已提交 Crossref 检索任务：${result.entities} 条论文陈述，task=${result.task_id.slice(
          0,
          8,
        )}。任务完成后刷新列表查看证据。`,
      )
    },
    onError: (err) => setError(getApiErrorMessage(err, '证据检索失败。')),
  })

  const confirmMutation = useMutation({
    mutationFn: (evidenceId: string) => confirmEvidence(evidenceId),
    onSuccess: async () => {
      setMessage('已人工确认匹配；该确认不代表证明候选人个人贡献。')
      await queryClient.invalidateQueries({
        queryKey: ['candidate', candidateId, 'evidence'],
      })
    },
    onError: (err) => setError(getApiErrorMessage(err, '确认证据失败。')),
  })

  const items = evidenceQuery.data ?? []

  return (
    <div className="ttc-page">
      {message && (
        <div className="ttc-notice">
          <BadgeCheck size={15} />
          <span>{message}</span>
        </div>
      )}
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
            EVIDENCE CENTER
            <span className="hero-eyebrow-line" />
            <span>Crossref DOI</span>
          </div>
          <h1>证据中心</h1>
          <p>
            {candidateQuery.data?.display_name ?? '候选人'} 的公开来源核验。当前后端只按 DOI
            精确检索 Crossref；匹配到的作品元数据不证明候选人作者身份。
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link
            to={`/candidates/${candidateId}${jobId ? `?job=${jobId}` : ''}`}
            className="ttc-btn ttc-btn-secondary"
          >
            <ArrowLeft size={15} />
            候选人详情
          </Link>
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => void evidenceQuery.refetch()}
          >
            <RefreshCw size={15} />
            刷新
          </button>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            disabled={searchMutation.isPending}
            onClick={() => searchMutation.mutate()}
          >
            {searchMutation.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Search size={15} />
            )}
            检索 Crossref
          </button>
        </div>
      </section>

      {evidenceQuery.isLoading && (
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      )}

      {evidenceQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>证据读取失败</strong>
            <span>{getApiErrorMessage(evidenceQuery.error, '请稍后重试。')}</span>
          </div>
        </div>
      )}

      {!evidenceQuery.isLoading && !evidenceQuery.isError && items.length === 0 && (
        <div className="ttc-card ttc-empty-large">
          <FileSearch size={28} />
          <h2>暂无证据</h2>
          <p>
            只有简历中存在可逐字定位、且包含 DOI 的论文陈述才能提交检索；系统不会凭标题推断匹配。
          </p>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            disabled={searchMutation.isPending}
            onClick={() => searchMutation.mutate()}
          >
            <Search size={15} />
            提交 Crossref 检索
          </button>
        </div>
      )}

      <div className="ttc-evidence-grid">
        {items.map((item) => (
          <article className="ttc-card ttc-card-pad ttc-evidence-card" key={item.id}>
            <div className="ttc-card-header">
              <div>
                <h2 className="ttc-card-title">{item.title}</h2>
                <p className="ttc-card-sub">
                  {item.source_name} · {formatDateTime(item.accessed_at)}
                </p>
              </div>
              <span className="ttc-badge ttc-badge-green">证据 {item.grade}</span>
            </div>
            <p>{item.snippet}</p>
            <div className="ttc-evidence-meta">
              <span>匹配方式：{item.match_method ?? '—'}</span>
              <span>
                置信度：
                {item.match_confidence != null
                  ? `${Math.round(item.match_confidence * 100)}%`
                  : '—'}
              </span>
            </div>
            <div className="ttc-card-actions">
              <a
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                href={item.source_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                <ExternalLink size={13} />
                打开来源
              </a>
              <button
                type="button"
                className="ttc-btn ttc-btn-primary ttc-btn-sm"
                disabled={Boolean(item.verified_by) || confirmMutation.isPending}
                onClick={() => confirmMutation.mutate(item.id)}
              >
                <BadgeCheck size={13} />
                {item.verified_by ? '已确认' : '人工确认匹配'}
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
