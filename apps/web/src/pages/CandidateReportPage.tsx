import { FormEvent, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileSearch,
  Loader2,
  ShieldCheck,
} from 'lucide-react'
import { getCandidate } from '../api/candidates'
import { getJob } from '../api/jobs'
import {
  createAssessment,
  downloadAssessment,
  getAssessment,
  reviseAssessment,
} from '../api/assessments'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { EVIDENCE_STATE_LABEL } from '../types'

export default function CandidateReportPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const candidateId = id ?? ''
  const jobId = searchParams.get('job') || ''
  const assessmentId = searchParams.get('assessment') || ''
  const [note, setNote] = useState('')
  const [revisions, setRevisions] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const candidateQuery = useQuery({
    queryKey: ['candidate', candidateId],
    queryFn: () => getCandidate(candidateId),
    enabled: Boolean(candidateId),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
  })
  const assessmentQuery = useQuery({
    queryKey: ['assessment', assessmentId],
    queryFn: () => getAssessment(assessmentId),
    enabled: Boolean(assessmentId),
  })
  const createMutation = useMutation({
    mutationFn: () => createAssessment(candidateId, jobId),
    onSuccess: (result) => {
      window.location.href = `/candidates/${candidateId}/report?job=${jobId}&assessment=${result.id}`
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建评估失败。')),
  })
  const reviseMutation = useMutation({
    mutationFn: () =>
      reviseAssessment(assessmentId, { note: note.trim(), dimensions: revisions }),
    onSuccess: () => {
      setMessage('人工复核结论已保存。')
      setError(null)
      void assessmentQuery.refetch()
    },
    onError: (err) => setError(getApiErrorMessage(err, '保存人工复核失败。')),
  })

  const assessment = assessmentQuery.data
  const report = assessment?.report
  const dimensions = report?.match_ledger?.dimensions ?? []
  const explanation = report?.explanation
  const evidence = report?.evidence_ledger

  if (!assessmentId) {
    return (
      <div className="ttc-page">
        <section className="ttc-page-head">
          <div>
            <h1>评估报告</h1>
            <p>尚未指定评估记录。</p>
          </div>
          <Link
            to={jobId ? `/candidates?job=${jobId}` : '/candidates'}
            className="ttc-btn ttc-btn-secondary"
          >
            <ArrowLeft size={15} />
            返回
          </Link>
        </section>
        <div className="ttc-card ttc-card-pad">
          <p className="ttc-muted">
            可从候选人详情点击「完整报告」，或在已有解析简历的情况下提交确定性评估。
          </p>
          {jobId && (
            <button
              type="button"
              className="ttc-btn ttc-btn-primary"
              disabled={createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              生成确定性评估
            </button>
          )}
        </div>
      </div>
    )
  }

  if (assessmentQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      </div>
    )
  }

  if (assessmentQuery.isError || !assessment) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>报告读取失败</strong>
            <span>{getApiErrorMessage(assessmentQuery.error, '评估不存在。')}</span>
          </div>
        </div>
      </div>
    )
  }

  const candidateName = candidateQuery.data?.display_name ?? '候选人'
  const jobTitle = jobQuery.data?.title ?? '岗位'

  const onRevise = (event: FormEvent) => {
    event.preventDefault()
    if (!note.trim()) {
      setError('请填写复核说明。')
      return
    }
    if (Object.keys(revisions).length === 0) {
      setError('至少填写一个维度的复核结论。')
      return
    }
    reviseMutation.mutate()
  }

  return (
    <div className="ttc-page">
      {message && (
        <div className="ttc-notice">
          <CheckCircle2 size={15} />
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
            ASSESSMENT REPORT
            <span className="hero-eyebrow-line" />
            <span>{assessment.status}</span>
          </div>
          <h1>{candidateName} · 评估报告</h1>
          <p>
            {jobTitle} · {report?.meta?.model_version || '评估模型'} ·{' '}
            {formatDateTime(report?.meta?.assessed_at)}
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
          <Link
            to={`/candidates/${candidateId}/evidence${jobId ? `?job=${jobId}` : ''}`}
            className="ttc-btn ttc-btn-secondary"
          >
            <FileSearch size={15} />
            证据中心
          </Link>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            onClick={() => void downloadAssessment(assessmentId)}
          >
            <Download size={15} />
            导出 JSON
          </button>
        </div>
      </section>

      <section className="ttc-report-page">
        <div className="ttc-report-header">
          <div className="ttc-score-hero">
            <span>匹配参考分</span>
            <strong>
              {report?.match_ledger?.score != null
                ? report.match_ledger.score.toFixed(1)
                : '—'}
            </strong>
            <small>
              类别 {report?.match_ledger?.category ?? '—'}
              {report?.match_ledger?.confidence != null
                ? ` · 置信度 ${Math.round(report.match_ledger.confidence * 100)}%`
                : ''}
            </small>
          </div>
          <div className="ttc-report-facts">
            <div>
              <span>证据分</span>
              <strong>{evidence?.score != null ? evidence.score.toFixed(1) : '—'}</strong>
            </div>
            <div>
              <span>证据等级</span>
              <strong>{evidence?.grade ?? '—'}</strong>
            </div>
            <div>
              <span>可核验覆盖</span>
              <strong>
                {evidence?.coverage
                  ? `${evidence.coverage.supported ?? 0}/${evidence.coverage.verifiable ?? 0}`
                  : '—'}
              </strong>
            </div>
          </div>
        </div>

        {explanation?.summary && (
          <article className="ttc-card ttc-card-pad">
            <h2 className="ttc-card-title">LLM 匹配解释</h2>
            <p>{explanation.summary}</p>
            {explanation.reason && <p className="ttc-muted">{explanation.reason}</p>}
            <div className="ttc-explanation-grid">
              {[
                ['优势', explanation.strengths],
                ['差距', explanation.gaps],
                ['建议', explanation.suggestions],
                ['风险与待核实', explanation.risk_notes],
              ].map(([label, items]) =>
                Array.isArray(items) && items.length > 0 ? (
                  <div key={String(label)}>
                    <strong>{String(label)}</strong>
                    <ul className="ttc-explanation-list">
                      {items.map((item, index) => (
                        <li key={index}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null,
              )}
            </div>
          </article>
        )}

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">逐维度评估</h2>
              <p className="ttc-card-sub">
                维度、权重、证据状态与理由来自 assessment.report.match_ledger
              </p>
            </div>
          </div>
          {dimensions.length === 0 && (
            <p className="ttc-muted">该评估没有维度明细。</p>
          )}
          <div className="ttc-dimension-list">
            {dimensions.map((dimension) => (
              <div className="ttc-dimension-row" key={dimension.key}>
                <div className="ttc-dimension-head">
                  <strong>
                    {dimension.label}
                    {dimension.status === 'revised' && (
                      <span className="ttc-badge ttc-badge-amber">已复核</span>
                    )}
                  </strong>
                  <span>
                    {dimension.score != null ? dimension.score.toFixed(1) : '未评分'} / 权重{' '}
                    {dimension.weight_pct}%
                  </span>
                </div>
                <p>
                  {EVIDENCE_STATE_LABEL[dimension.evidence_state]} · {dimension.reasoning}
                </p>
              </div>
            ))}
          </div>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">人工复核</h2>
              <p className="ttc-card-sub">
                PATCH /api/v1/assessments/{'{id}'} · 只修改理由，不伪造分数
              </p>
            </div>
            <ShieldCheck size={18} className="ttc-accent-icon" />
          </div>
          <form className="ttc-revision-form" onSubmit={onRevise}>
            {dimensions.map((dimension) => (
              <label className="ttc-field" key={dimension.key}>
                <span>{dimension.label}</span>
                <textarea
                  rows={2}
                  value={revisions[dimension.key] ?? ''}
                  onChange={(event) =>
                    setRevisions((prev) => ({
                      ...prev,
                      [dimension.key]: event.target.value,
                    }))
                  }
                  placeholder="可选：填写人工复核结论"
                />
              </label>
            ))}
            <label className="ttc-field">
              <span>复核说明 *</span>
              <textarea
                rows={3}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="说明复核依据；该说明会写入 assessment_revision。"
              />
            </label>
            <button
              type="submit"
              className="ttc-btn ttc-btn-primary"
              disabled={reviseMutation.isPending}
            >
              {reviseMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              保存人工复核
            </button>
          </form>
        </article>

        {(report?.limitations ?? []).length > 0 && (
          <article className="ttc-report-disclaimer">
            <AlertCircle size={16} />
            <div>
              <strong>限制与声明</strong>
              <ul>
                {report?.limitations?.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          </article>
        )}
      </section>
    </div>
  )
}
