import { useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileText,
  Scale,
  ShieldCheck,
} from 'lucide-react'
import { downloadAssessment, getAssessment, reviseAssessment } from '../api/assessments'
import { getApiErrorMessage } from '../lib/apiError'
import { EVIDENCE_GRADE_CLASS, formatDateTime } from '../lib/format'
import type { AssessmentDimension } from '../types'

type DimensionFilter = 'all' | 'strong' | 'needs_verify' | 'revised'

const STATE_LABEL: Record<AssessmentDimension['evidence_state'], string> = {
  strong: '证据充分',
  partial: '部分证据',
  self_claim: '仅简历自述',
  missing: '缺乏证据',
}

const STATE_CLASS: Record<AssessmentDimension['evidence_state'], string> = {
  strong: 'ttc-badge-green',
  partial: 'ttc-badge-blue',
  self_claim: 'ttc-badge-amber',
  missing: 'ttc-badge-red',
}

const BREAKDOWN_LABELS: Record<string, string> = {
  A: 'A 级官方/权威',
  B: 'B 级公开验证',
  C: 'C 级弱佐证',
  D: 'D 级仅自述',
  strong: '证据充分',
  partial: '部分证据',
  self_claim: '仅简历自述',
  missing: '缺乏证据',
}

const REVIEW_STATUS_LABEL: Record<string, string> = {
  pending: '待人工复核',
  approved: '人工已确认',
  revised: '人工已复核修改',
}

export default function CandidateReportPage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const assessmentId = params.get('assessment') ?? ''
  const queryClient = useQueryClient()
  const reviewInputRef = useRef<HTMLTextAreaElement | null>(null)

  const [note, setNote] = useState('')
  const [dimensionKey, setDimensionKey] = useState('')
  const [filter, setFilter] = useState<DimensionFilter>('all')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const assessmentQuery = useQuery({
    queryKey: ['assessment', assessmentId],
    queryFn: () => getAssessment(assessmentId),
    enabled: Boolean(assessmentId),
  })

  const revise = useMutation({
    mutationFn: () =>
      reviseAssessment(assessmentId, {
        note: note.trim(),
        dimensions: { [dimensionKey]: note.trim() },
      }),
    onSuccess: () => {
      setMessage('复核意见已记录。')
      setError('')
      setNote('')
      void queryClient.invalidateQueries({ queryKey: ['assessment', assessmentId] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '记录复核失败。')),
  })

  const assessment = assessmentQuery.data
  const report = assessment?.report
  const dimensions = report?.match_ledger?.dimensions ?? []
  const ledger = report?.evidence_ledger
  const matchScore = report?.match_ledger?.score ?? null

  const counts = useMemo(() => {
    const strong = dimensions.filter((d) => d.evidence_state === 'strong').length
    const needsVerify = dimensions.filter(
      (d) => d.evidence_state === 'partial' || d.evidence_state === 'self_claim' || d.evidence_state === 'missing',
    ).length
    const revised = dimensions.filter((d) => d.status === 'revised').length
    return { total: dimensions.length, strong, needsVerify, revised }
  }, [dimensions])

  const filteredDimensions = useMemo(() => {
    switch (filter) {
      case 'strong':
        return dimensions.filter((d) => d.evidence_state === 'strong')
      case 'needs_verify':
        return dimensions.filter((d) => d.evidence_state !== 'strong')
      case 'revised':
        return dimensions.filter((d) => d.status === 'revised')
      default:
        return dimensions
    }
  }, [dimensions, filter])

  async function exportReport() {
    try {
      const blob = await downloadAssessment(assessmentId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `assessment-${assessmentId}.json`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(getApiErrorMessage(err, '导出失败。'))
    }
  }

  function focusReviewForDimension(dimension: AssessmentDimension) {
    setDimensionKey(dimension.key)
    window.requestAnimationFrame(() => {
      reviewInputRef.current?.focus()
      reviewInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  if (!assessmentId) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>缺少评估 ID</strong>
            <span>请从候选人详情页点击「生成评估」进入。</span>
          </div>
          <Link to={`/candidates/${id}`} className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回候选人
          </Link>
        </div>
      </div>
    )
  }

  const evidenceScorePct = ledger ? Math.min(100, Math.max(0, Math.round(ledger.score))) : 0
  const verifiableCount = ledger?.coverage.verifiable ?? 0
  const supportedCount = ledger?.coverage.supported ?? 0
  const coveragePct =
    verifiableCount > 0 ? Math.min(100, Math.round((supportedCount / verifiableCount) * 100)) : 0
  const matchScorePct = matchScore !== null ? Math.min(100, Math.max(0, Math.round(matchScore))) : 0
  const reviewStatus = report?.human_review?.status ?? 'pending'
  const selectedDimension = dimensions.find((item) => item.key === dimensionKey)

  return (
    <div className="ttc-page ttc-report-page">
      <section className="ttc-page-head">
        <div>
          <div className="ttc-mini-heading">
            <Scale size={14} />
            <span>DUAL-LEDGER ASSESSMENT REPORT</span>
          </div>
          <h1>双账本评估报告</h1>
          <p>证据可信度与岗位匹配度独立计算与呈现，拒绝以单分掩盖信息缺口，最终结论由人工复核给出。</p>
        </div>
        <div className="ttc-heading-actions">
          <Link to={`/candidates/${id}`} className="ttc-btn ttc-btn-secondary">
            返回候选人
          </Link>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            disabled={!report}
            onClick={() => void exportReport()}
          >
            <Download size={16} />
            导出 JSON
          </button>
        </div>
      </section>

      {(error || message) && (
        <div className={error ? 'ttc-inline-error' : 'ttc-inline-ok'} role={error ? 'alert' : 'status'}>
          {error ? <AlertCircle size={16} /> : <ShieldCheck size={16} />}
          <span>{error || message}</span>
        </div>
      )}

      {assessmentQuery.isLoading && <div className="ttc-card ttc-skeleton-card" />}

      {assessmentQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取评估</strong>
            <span>{getApiErrorMessage(assessmentQuery.error)}</span>
          </div>
        </div>
      )}

      {report && (
        <>
          <section className="ttc-ledger-grid" aria-label="双账本总览">
            <article className="ttc-card ttc-ledger-card ttc-ledger-evidence">
              <div className="ttc-ledger-head">
                <div>
                  <span className="ttc-ledger-kicker">LEDGER 01 · EVIDENCE CONFIDENCE</span>
                  <h2>证据可信度账本</h2>
                </div>
                {ledger && (
                  <span className={`ttc-badge ${EVIDENCE_GRADE_CLASS[ledger.grade]}`}>
                    等级 {ledger.grade}
                  </span>
                )}
              </div>

              <div className="ttc-ledger-body">
                <div
                  className="ttc-radial-gauge"
                  style={{ ['--gauge-pct' as string]: `${evidenceScorePct}%` }}
                  aria-label={`证据可信度 ${evidenceScorePct} 分`}
                >
                  <div className="ttc-radial-inner">
                    <strong>{ledger ? Math.round(ledger.score) : '—'}</strong>
                    <span>/ 100</span>
                  </div>
                </div>

                <div className="ttc-ledger-stats">
                  <div className="ttc-coverage-block">
                    <div className="ttc-coverage-top">
                      <span>可核验声明覆盖率</span>
                      <strong>
                        {supportedCount} / {verifiableCount} ({coveragePct}%)
                      </strong>
                    </div>
                    <div className="ttc-coverage-track">
                      <div className="ttc-coverage-fill" style={{ width: `${coveragePct}%` }} />
                    </div>
                  </div>

                  {ledger?.breakdown && Object.keys(ledger.breakdown).length > 0 && (
                    <div className="ttc-breakdown-pills">
                      {Object.entries(ledger.breakdown).map(([key, count]) => (
                        <span key={key} className="ttc-mini-pill">
                          {BREAKDOWN_LABELS[key] ?? key}: <strong>{count}</strong>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </article>

            <article className="ttc-card ttc-ledger-card ttc-ledger-match">
              <div className="ttc-ledger-head">
                <div>
                  <span className="ttc-ledger-kicker">LEDGER 02 · JOB MATCH REFERENCE</span>
                  <h2>岗位匹配参考账本</h2>
                </div>
                <span className={`ttc-badge ${reviewStatus === 'revised' ? 'ttc-badge-blue' : 'ttc-badge-amber'}`}>
                  {REVIEW_STATUS_LABEL[reviewStatus] ?? reviewStatus}
                </span>
              </div>

              <div className="ttc-ledger-body">
                <div
                  className={`ttc-radial-gauge ${matchScore === null ? 'is-muted' : 'is-jade'}`}
                  style={{ ['--gauge-pct' as string]: `${matchScorePct}%` }}
                  aria-label={matchScore !== null ? `岗位匹配参考 ${matchScorePct} 分` : '当前不可比'}
                >
                  <div className="ttc-radial-inner">
                    <strong>{matchScore !== null ? Math.round(matchScore) : '不可比'}</strong>
                    <span>{matchScore !== null ? '加权参考' : '需补足证据'}</span>
                  </div>
                </div>

                <div className="ttc-ledger-stats">
                  {matchScore === null ? (
                    <div className="ttc-comparability-banner" role="note">
                      <AlertTriangle size={16} />
                      <div>
                        <strong>低证据覆盖度 · 暂不出具可比总分</strong>
                        <p>关键维度缺少可核验依据，系统已拦截单一匹配分。请在右侧人工复核或补全证据后重新评估。</p>
                      </div>
                    </div>
                  ) : (
                    <p className="ttc-card-sub">
                      岗位匹配参考基于岗位版本权重与已提取依据计算，必须结合右侧证据状态逐项判断，不可替代人工面试结论。
                    </p>
                  )}

                  <div className="ttc-breakdown-pills">
                    <span className="ttc-mini-pill">
                      评估时间：<strong>{formatDateTime(report.meta?.assessed_at)}</strong>
                    </span>
                    <span className="ttc-mini-pill">
                      模型版本：<strong>{report.meta?.model_version ?? '—'}</strong>
                    </span>
                  </div>
                </div>
              </div>
            </article>
          </section>

          <div className="ttc-two-col">
            <article className="ttc-card">
              <div className="ttc-card-head">
                <div>
                  <h2>维度证据分解</h2>
                  <p className="ttc-card-sub">每个维度并列展示得分与权重占比，可一键带入右侧复核</p>
                </div>
                <FileText size={18} className="ttc-accent-icon" />
              </div>

              <div className="ttc-chip-row ttc-chip-row-spaced" role="group" aria-label="按证据状态筛选维度">
                <button
                  type="button"
                  className={`ttc-chip ${filter === 'all' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setFilter('all')}
                >
                  全部 ({counts.total})
                </button>
                <button
                  type="button"
                  className={`ttc-chip ${filter === 'strong' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setFilter('strong')}
                >
                  证据充分 ({counts.strong})
                </button>
                <button
                  type="button"
                  className={`ttc-chip ${filter === 'needs_verify' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setFilter('needs_verify')}
                >
                  待补充核验 ({counts.needsVerify})
                </button>
                <button
                  type="button"
                  className={`ttc-chip ${filter === 'revised' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setFilter('revised')}
                >
                  已人工修改 ({counts.revised})
                </button>
              </div>

              <div className="ttc-dim-cards">
                {filteredDimensions.map((dimension) => {
                  const scorePct =
                    dimension.score !== null ? Math.min(100, Math.max(0, Math.round(dimension.score))) : 0
                  const weightPct = Math.min(100, Math.max(0, Math.round(dimension.weight_pct)))

                  return (
                    <section key={dimension.key} className="ttc-dim-card">
                      <div className="ttc-dim-card-head">
                        <div className="ttc-dim-title-group">
                          <strong>{dimension.label}</strong>
                          <span className={`ttc-badge ${STATE_CLASS[dimension.evidence_state]}`}>
                            {STATE_LABEL[dimension.evidence_state]}
                          </span>
                          {dimension.status === 'revised' && (
                            <span className="ttc-badge ttc-badge-blue">
                              <CheckCircle2 size={12} />
                              已复核修改
                            </span>
                          )}
                        </div>
                        <button
                          type="button"
                          className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => focusReviewForDimension(dimension)}
                        >
                          <ClipboardCheck size={14} />
                          填入复核
                        </button>
                      </div>

                      <div className="ttc-dim-meters">
                        <div className="ttc-meter-row">
                          <span className="ttc-meter-label">维度参考分</span>
                          <div className="ttc-meter-track">
                            <div
                              className={`ttc-meter-fill ${dimension.score === null ? 'is-empty' : 'is-score'}`}
                              style={{ width: `${scorePct}%` }}
                            />
                          </div>
                          <strong className="ttc-meter-val">
                            {dimension.score !== null ? `${dimension.score} 分` : '待核验'}
                          </strong>
                        </div>

                        <div className="ttc-meter-row">
                          <span className="ttc-meter-label">岗位权重占比</span>
                          <div className="ttc-meter-track">
                            <div className="ttc-meter-fill is-weight" style={{ width: `${weightPct}%` }} />
                          </div>
                          <strong className="ttc-meter-val">{dimension.weight_pct}%</strong>
                        </div>
                      </div>

                      <p className="ttc-dim-reason">{dimension.reasoning}</p>

                      <div className="ttc-dim-refs">
                        <span className="ttc-mini-pill">
                          引用证据：<strong>{dimension.evidence_ids.length}</strong> 条
                        </span>
                        <span className="ttc-mini-pill">
                          关联声明：<strong>{dimension.source_claim_ids.length}</strong> 条
                        </span>
                      </div>
                    </section>
                  )
                })}

                {filteredDimensions.length === 0 && (
                  <p className="ttc-muted">当前筛选条件下没有匹配维度。</p>
                )}
              </div>
            </article>

            <article className="ttc-card">
              <div className="ttc-card-head">
                <div>
                  <h2>人工复核记录</h2>
                  <p className="ttc-card-sub">
                    记录审计结论、补充访谈验证发现并修订维度说明（只增补可追溯，不静默抹除历史）
                  </p>
                </div>
                <ShieldCheck size={18} className="ttc-accent-icon" />
              </div>

              <label className="ttc-login-field ttc-field-block">
                <span>复核维度</span>
                <select
                  value={dimensionKey}
                  onChange={(event) => setDimensionKey(event.target.value)}
                >
                  <option value="">请选择维度</option>
                  {dimensions.map((dimension) => (
                    <option key={dimension.key} value={dimension.key}>
                      {dimension.label}（权重 {dimension.weight_pct}%）
                    </option>
                  ))}
                </select>
              </label>

              {selectedDimension && (
                <p className="ttc-inline-hint">
                  当前状态：{STATE_LABEL[selectedDimension.evidence_state]} · 权重 {selectedDimension.weight_pct}%
                </p>
              )}

              <label className="ttc-login-field ttc-field-block">
                <span>复核意见与依据</span>
                <textarea
                  ref={reviewInputRef}
                  rows={5}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="写明你核对到的证据链接、面试追问结论或修正理由…"
                />
              </label>

              <div className="ttc-form-actions">
                <button
                  type="button"
                  className="ttc-btn ttc-btn-primary ttc-btn-sm"
                  disabled={!dimensionKey || !note.trim() || revise.isPending}
                  onClick={() => revise.mutate()}
                >
                  {revise.isPending ? '提交中…' : '记录复核'}
                </button>
              </div>

              {report.limitations && report.limitations.length > 0 && (
                <>
                  <h3 className="ttc-report-subhead">系统识别的报告边界</h3>
                  <ul className="ttc-plain-list">
                    {report.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              )}
            </article>
          </div>
        </>
      )}
    </div>
  )
}
