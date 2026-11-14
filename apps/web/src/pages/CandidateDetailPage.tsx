import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileSearch,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { getCandidate, listCandidateResumes } from '../api/candidates'
import {
  deleteResume,
  getResumeClaims,
  getResumeTimeline,
  reparseResume,
} from '../api/resumes'
import {
  createAssessment,
  getAssessment,
  matchResume,
} from '../api/assessments'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import {
  CLAIM_TYPE_LABEL,
  EVIDENCE_STATE_LABEL,
  PARSE_STATUS_LABEL,
} from '../types'
import type { AssessmentDimension, ResumeClaim } from '../types'

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="ttc-json-preview">{JSON.stringify(value, null, 2)}</pre>
}

export default function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const candidateId = id ?? ''
  const jobId = searchParams.get('job') || ''
  const assessmentId = searchParams.get('assessment') || ''
  const [selectedResume, setSelectedResume] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const candidateQuery = useQuery({
    queryKey: ['candidate', candidateId],
    queryFn: () => getCandidate(candidateId),
    enabled: Boolean(candidateId),
  })
  const resumesQuery = useQuery({
    queryKey: ['candidate', candidateId, 'resumes'],
    queryFn: () => listCandidateResumes(candidateId),
    enabled: Boolean(candidateId),
  })
  const activeResumeId = selectedResume || resumesQuery.data?.[0]?.id || ''
  const claimsQuery = useQuery({
    queryKey: ['resume', activeResumeId, 'claims'],
    queryFn: () => getResumeClaims(activeResumeId),
    enabled: Boolean(activeResumeId),
  })
  const timelineQuery = useQuery({
    queryKey: ['resume', activeResumeId, 'timeline'],
    queryFn: () => getResumeTimeline(activeResumeId),
    enabled: Boolean(activeResumeId),
  })
  const assessmentQuery = useQuery({
    queryKey: ['assessment', assessmentId],
    queryFn: () => getAssessment(assessmentId),
    enabled: Boolean(assessmentId),
  })

  const candidate = candidateQuery.data
  const resumes = resumesQuery.data ?? []
  const assessment = assessmentQuery.data

  const runAssessment = useMutation({
    mutationFn: () => createAssessment(candidateId, jobId),
    onSuccess: (result) => {
      setError(null)
      setMessage('确定性评估已完成。')
      setSearchParams({ job: jobId, assessment: result.id })
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建评估失败。')),
  })

  const runMatch = useMutation({
    mutationFn: async () => {
      const resume = resumes[0]
      if (!resume) throw new Error('该候选人没有简历。')
      return matchResume(resume.id, { job_id: jobId, explain: true, top_k: 5 })
    },
    onSuccess: async (result) => {
      setError(null)
      setMessage(
        result.fallback_reason
          ? `匹配完成（${result.fallback_reason}）。`
          : '小模型匹配与 DeepSeek 解释已完成。',
      )
      setSearchParams({ job: jobId, assessment: result.assessment_id })
      await queryClient.invalidateQueries({ queryKey: ['assessment'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '匹配评估失败。')),
  })

  const reparse = useMutation({
    mutationFn: (resumeId: string) => reparseResume(resumeId),
    onSuccess: async () => {
      setMessage('已重新提交解析任务，请在候选人列表查看进度。')
      await queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'resumes'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '重新解析失败。')),
  })

  const removeResume = useMutation({
    mutationFn: (resumeId: string) => deleteResume(resumeId),
    onSuccess: async () => {
      setMessage('简历已删除。')
      await queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'resumes'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '删除简历失败。')),
  })

  if (candidateQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      </div>
    )
  }

  if (candidateQuery.isError || !candidate) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>候选人读取失败</strong>
            <span>{getApiErrorMessage(candidateQuery.error, '候选人不存在。')}</span>
          </div>
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回候选人
          </Link>
        </div>
      </div>
    )
  }

  const dimensions = assessment?.report.match_ledger?.dimensions ?? []
  const explanation = assessment?.report.explanation

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
            CANDIDATE PROFILE
            <span className="hero-eyebrow-line" />
            <span>{candidate.id.slice(0, 8)}</span>
          </div>
          <h1>{candidate.display_name}</h1>
          <p>
            {candidate.source} · {candidate.is_synthetic ? '合成样本' : '真实候选人'} · 创建于{' '}
            {formatDateTime(candidate.created_at)}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link
            to={jobId ? `/candidates?job=${jobId}` : '/candidates'}
            className="ttc-btn ttc-btn-secondary"
          >
            <ArrowLeft size={15} />
            返回候选人
          </Link>
          <Link
            to={`/candidates/${candidate.id}/evidence${jobId ? `?job=${jobId}` : ''}`}
            className="ttc-btn ttc-btn-secondary"
          >
            <FileSearch size={15} />
            证据中心
          </Link>
          {jobId && (
            <>
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                disabled={runAssessment.isPending}
                onClick={() => runAssessment.mutate()}
              >
                {runAssessment.isPending && <Loader2 size={14} className="animate-spin" />}
                确定性评估
              </button>
              <button
                type="button"
                className="ttc-btn ttc-btn-primary"
                disabled={runMatch.isPending || resumes.length === 0}
                onClick={() => runMatch.mutate()}
              >
                {runMatch.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                小模型 + DeepSeek 匹配
              </button>
            </>
          )}
        </div>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">候选人信息</h2>
              <p className="ttc-card-sub">GET /api/v1/candidates/{'{id}'}</p>
            </div>
            <span className="ttc-avatar">{candidate.display_name.slice(0, 2)}</span>
          </div>
          <div className="ttc-detail-rows">
            <div className="ttc-detail-row">
              <span>姓名</span>
              <strong>{candidate.display_name}</strong>
            </div>
            <div className="ttc-detail-row">
              <span>来源</span>
              <strong>{candidate.source}</strong>
            </div>
            <div className="ttc-detail-row">
              <span>归属岗位</span>
              <strong>{candidate.job_id?.slice(0, 8) ?? '未绑定'}</strong>
            </div>
            <div className="ttc-detail-row">
              <span>联系方式</span>
              <strong>{candidate.contact_masked || '未提供（默认脱敏）'}</strong>
            </div>
          </div>
          <div className="ttc-privacy-note">
            <ShieldCheck size={15} />
            <span>后端仅返回脱敏联系方式；原始联系方式不进入前端。</span>
          </div>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">简历</h2>
              <p className="ttc-card-sub">GET /candidates/{'{id}'}/resumes</p>
            </div>
          </div>
          {resumes.length === 0 && (
            <p className="ttc-muted">该候选人还没有简历。</p>
          )}
          <div className="ttc-resume-list">
            {resumes.map((resume) => (
              <article
                key={resume.id}
                className={`ttc-resume-row ${
                  resume.id === activeResumeId ? 'is-active' : ''
                }`}
              >
                <button
                  type="button"
                  className="ttc-resume-main"
                  onClick={() => setSelectedResume(resume.id)}
                >
                  <FileText size={16} />
                  <div>
                    <strong>{resume.file_name}</strong>
                    <span>
                      {PARSE_STATUS_LABEL[resume.parse_status]} ·{' '}
                      {formatDateTime(resume.created_at)}
                    </span>
                  </div>
                </button>
                <div className="ttc-card-actions">
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={reparse.isPending}
                    onClick={() => reparse.mutate(resume.id)}
                  >
                    <RefreshCw size={13} />
                    重新解析
                  </button>
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={removeResume.isPending}
                    onClick={() => removeResume.mutate(resume.id)}
                  >
                    <Trash2 size={13} />
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        </article>
      </section>

      {assessment && (
        <section className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">评估概览</h2>
              <p className="ttc-card-sub">
                {assessment.report.meta?.source || assessment.report.meta?.model_version || 'assessment'}{' '}
                · {assessment.status}
              </p>
            </div>
            <Link
              to={`/candidates/${candidate.id}/report?job=${jobId}&assessment=${assessment.id}`}
              className="ttc-btn ttc-btn-primary ttc-btn-sm"
            >
              完整报告
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="ttc-assessment-summary">
            <div className="ttc-score-hero">
              <span>匹配参考分</span>
              <strong>
                {assessment.report.match_ledger?.score != null
                  ? assessment.report.match_ledger.score.toFixed(1)
                  : '—'}
              </strong>
            </div>
            <div>
              <p>
                {explanation?.summary ||
                  '暂无 LLM 解释；可点击「小模型 + DeepSeek 匹配」生成。'}
              </p>
              {dimensions.length > 0 && (
                <div className="ttc-dimension-list">
                  {dimensions.map((dimension) => (
                    <div className="ttc-dimension-row" key={dimension.key}>
                      <div className="ttc-dimension-head">
                        <strong>{dimension.label}</strong>
                        <span>{dimension.score != null ? dimension.score.toFixed(1) : '未评分'}</span>
                      </div>
                      <p>
                        {EVIDENCE_STATE_LABEL[dimension.evidence_state]} · {dimension.reasoning}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">简历 claims</h2>
              <p className="ttc-card-sub">
                GET /resumes/{'{id}'}/claims · 仅展示原文可定位片段
              </p>
            </div>
            <span className="ttc-badge ttc-badge-blue">
              {claimsQuery.data?.claims.length ?? 0} 条
            </span>
          </div>
          {claimsQuery.isLoading && <p className="ttc-muted">正在读取 claims…</p>}
          {claimsQuery.isError && (
            <div className="ttc-inline-error">
              <AlertCircle size={15} />
              <span>{getApiErrorMessage(claimsQuery.error, '读取 claims 失败。')}</span>
            </div>
          )}
          <div className="ttc-claim-list">
            {(claimsQuery.data?.claims ?? []).map((claim: ResumeClaim) => (
              <article className="ttc-claim-card" key={claim.id}>
                <div className="ttc-claim-head">
                  <span className="ttc-chip ttc-chip-blue">
                    {CLAIM_TYPE_LABEL[claim.type] ?? claim.type}
                  </span>
                  <span className="ttc-muted">
                    置信度 {Math.round(claim.confidence * 100)}%
                    {claim.page_no ? ` · 第 ${claim.page_no} 页` : ''}
                  </span>
                </div>
                <p>{claim.raw_text}</p>
                {Object.keys(claim.normalized).length > 0 && (
                  <JsonBlock value={claim.normalized} />
                )}
              </article>
            ))}
          </div>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">时间线</h2>
              <p className="ttc-card-sub">GET /resumes/{'{id}'}/timeline</p>
            </div>
          </div>
          {timelineQuery.isLoading && <p className="ttc-muted">正在读取时间线…</p>}
          {!timelineQuery.isLoading && (timelineQuery.data?.items ?? []).length === 0 && (
            <p className="ttc-muted">暂无可展示的时间线条目。</p>
          )}
          <div className="ttc-timeline">
            {(timelineQuery.data?.items ?? []).map((item, index) => (
              <div className="ttc-timeline-item" key={item.claim_id ?? index}>
                <span className="ttc-timeline-dot" />
                <div>
                  <strong>
                    {String(item.title || item.type || item.kind || '经历')}
                  </strong>
                  <span>
                    {String(item.start ?? '')}
                    {item.end ? ` – ${String(item.end)}` : ''}
                    {item.needs_review ? ' · 待核验' : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {(timelineQuery.data?.conflicts ?? []).length > 0 && (
            <div className="ttc-inline-error" style={{ marginTop: 12 }}>
              <AlertCircle size={15} />
              <span>
                {[
                  ...new Set(
                    (timelineQuery.data?.conflicts ?? []).map(
                      (item) => item.note || `${item.type} 时间重叠`,
                    ),
                  ),
                ].join('；')}
              </span>
            </div>
          )}
        </article>
      </section>
    </div>
  )
}
