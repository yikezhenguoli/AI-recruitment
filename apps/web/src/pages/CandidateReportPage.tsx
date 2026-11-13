import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Download, FileText, Scale, ShieldCheck } from 'lucide-react'
import { downloadAssessment, getAssessment, reviseAssessment } from '../api/assessments'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { AssessmentDimension, EvidenceGrade } from '../types'

const GRADE_CLASS: Record<EvidenceGrade, string> = {
  A: 'ttc-badge-green',
  B: 'ttc-badge-blue',
  C: 'ttc-badge-amber',
  D: 'ttc-badge-red',
}

const STATE_LABEL: Record<AssessmentDimension['evidence_state'], string> = {
  strong: '证据充分',
  partial: '部分证据',
  self_claim: '仅简历自述',
  missing: '无可用证据',
}

export default function CandidateReportPage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const assessmentId = params.get('assessment') ?? ''
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const [dimensionKey, setDimensionKey] = useState('')
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
    onError: (err) => setError(getApiErrorMessage(err, '提交复核失败。')),
  })

  const assessment = assessmentQuery.data
  const report = assessment?.report
  const dimensions = report?.match_ledger?.dimensions ?? []
  const ledger = report?.evidence_ledger

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

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            ASSESSMENT
            <span className="hero-eyebrow-line" />
            <span>{assessment?.status?.toUpperCase() ?? 'LOADING'}</span>
          </div>
          <h1>评估报告</h1>
          <p>
            证据分级与维度得分都由确定性规则生成；报告只给出可复核的线索，不做录用建议。
          </p>
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

      {(message || error) && (
        <div className={error ? 'ttc-inline-error' : 'ttc-inline-ok'}>
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

      {assessment && (
        <>
          <div className="ttc-kpi-grid">
            <article className="ttc-card ttc-kpi-card">
              <div className="ttc-kpi-top">
                <span className="ttc-kpi-icon ttc-kpi-icon-blue">
                  <ShieldCheck size={16} />
                </span>
                <span>证据分</span>
              </div>
              <strong className="ttc-kpi-value">{ledger?.score ?? '—'}</strong>
              {ledger && (
                <span className={`ttc-badge ${GRADE_CLASS[ledger.grade]}`}>{ledger.grade} 级</span>
              )}
            </article>
            <article className="ttc-card ttc-kpi-card">
              <div className="ttc-kpi-top">
                <span className="ttc-kpi-icon ttc-kpi-icon-green">
                  <Scale size={16} />
                </span>
                <span>岗位适配分</span>
              </div>
              <strong className="ttc-kpi-value">{report?.match_ledger?.score ?? '不足以计算'}</strong>
              <span className="ttc-muted">有效权重不足 30% 时不出分</span>
            </article>
            <article className="ttc-card ttc-kpi-card">
              <div className="ttc-kpi-top">
                <span className="ttc-kpi-icon ttc-kpi-icon-violet">
                  <FileText size={16} />
                </span>
                <span>可核实声明</span>
              </div>
              <strong className="ttc-kpi-value">
                {ledger ? `${ledger.coverage.supported}/${ledger.coverage.verifiable}` : '—'}
              </strong>
              <span className="ttc-muted">有 A/B 级证据支持</span>
            </article>
          </div>

          <div className="ttc-detail-grid">
            <article className="ttc-card">
              <div className="ttc-card-header">
                <div>
                  <h2 className="ttc-card-title">维度明细</h2>
                  <p className="ttc-card-sub">
                    评估于 {formatDateTime(report?.meta?.assessed_at)} · 模型{' '}
                    {report?.meta?.model_version}
                  </p>
                </div>
              </div>
              <div className="ttc-dimension-list">
                {dimensions.map((dimension) => (
                  <div key={dimension.key} className="ttc-dimension-row">
                    <div className="ttc-dimension-head">
                      <strong>{dimension.label}</strong>
                      <span className="ttc-muted">权重 {dimension.weight_pct}%</span>
                      <span className="ttc-dimension-count">
                        {dimension.score === null ? '不评分' : dimension.score}
                      </span>
                    </div>
                    <div className="ttc-dimension-mini">
                      <span
                        className={`ttc-badge ${
                          dimension.evidence_state === 'strong'
                            ? 'ttc-badge-green'
                            : dimension.evidence_state === 'missing'
                              ? 'ttc-badge-red'
                              : 'ttc-badge-amber'
                        }`}
                      >
                        {STATE_LABEL[dimension.evidence_state]}
                      </span>
                      {dimension.status === 'revised' && (
                        <span className="ttc-badge ttc-badge-blue">已复核修改</span>
                      )}
                    </div>
                    <p className="ttc-muted">{dimension.reasoning}</p>
                  </div>
                ))}
                {dimensions.length === 0 && <p className="ttc-muted">报告没有维度明细。</p>}
              </div>
            </article>

            <article className="ttc-card">
              <div className="ttc-card-header">
                <div>
                  <h2 className="ttc-card-title">人工复核</h2>
                  <p className="ttc-card-sub">复核只改说明文字，不改自动分数。</p>
                </div>
              </div>
              <label className="ttc-login-field ttc-field-block">
                <span>维度</span>
                <select
                  value={dimensionKey}
                  onChange={(event) => setDimensionKey(event.target.value)}
                >
                  <option value="">请选择维度</option>
                  {dimensions.map((dimension) => (
                    <option key={dimension.key} value={dimension.key}>
                      {dimension.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ttc-login-field ttc-field-block">
                <span>复核结论</span>
                <textarea
                  rows={4}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="写明你核对到的内容与依据…"
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

              {report?.limitations && report.limitations.length > 0 && (
                <>
                  <h3 className="ttc-report-subhead">报告边界</h3>
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
