import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  BadgeCheck,
  FileText,
  Mic,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from 'lucide-react'
import { getCandidate, listCandidateResumes } from '../api/candidates'
import { listConsents } from '../api/consents'
import { confirmEvidence, listEvidence, searchEvidence } from '../api/evidence'
import { getJob } from '../api/jobs'
import { watchTask } from '../api/progress'
import { getResumeClaims, reparseResume, uploadResume } from '../api/resumes'
import { createAssessment } from '../api/assessments'
import { getVoiceSummary, listVoiceSessions } from '../api/voice'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime, formatDate } from '../lib/format'
import type { ConsentPurpose, ResumeClaim, TaskProgressMessage } from '../types'

const CLAIM_LABEL: Record<string, string> = {
  skill: '技能',
  education: '教育',
  work: '工作',
  project: '项目',
  publication: '论文',
  patent: '专利',
  award: '奖项',
  certificate: '证书',
}

const PURPOSE_LABEL: Record<ConsentPurpose, string> = {
  resume_process: '简历处理',
  voice_interview: '语音面试',
  recording: '录音',
  model_training: '模型训练',
}

const STAGE_LABEL: Record<string, string> = {
  queued: '排队中',
  running: '解析中',
  succeeded: '已完成',
  failed: '失败',
  canceled: '已取消',
}

export default function CandidateDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [resumeId, setResumeId] = useState('')
  const [task, setTask] = useState<{ id: string; label: string } | null>(null)
  const [progress, setProgress] = useState<TaskProgressMessage | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  const candidateQuery = useQuery({
    queryKey: ['candidate', id],
    queryFn: () => getCandidate(id),
    enabled: Boolean(id),
  })
  const candidate = candidateQuery.data

  const jobQuery = useQuery({
    queryKey: ['job', candidate?.job_id],
    queryFn: () => getJob(candidate!.job_id!),
    enabled: Boolean(candidate?.job_id),
  })
  const resumesQuery = useQuery({
    queryKey: ['candidateResumes', id],
    queryFn: () => listCandidateResumes(id),
    enabled: Boolean(id),
  })
  const consentsQuery = useQuery({
    queryKey: ['consents', id],
    queryFn: () => listConsents(id),
    enabled: Boolean(id),
  })
  const evidenceQuery = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => listEvidence(id),
    enabled: Boolean(id),
  })
  const sessionsQuery = useQuery({
    queryKey: ['candidateSessions', id],
    queryFn: () => listVoiceSessions({ candidate_id: id, limit: 20 }),
    enabled: Boolean(id),
  })
  const latestReportedSession = (sessionsQuery.data ?? []).find((session) => session.has_report)
  const summaryQuery = useQuery({
    queryKey: ['voiceSummary', latestReportedSession?.id],
    queryFn: () => getVoiceSummary(latestReportedSession!.id),
    enabled: Boolean(latestReportedSession?.id),
    retry: false,
  })
  const claimsQuery = useQuery({
    queryKey: ['resumeClaims', resumeId],
    queryFn: () => getResumeClaims(resumeId),
    enabled: Boolean(resumeId),
  })

  useEffect(() => {
    if (!task) return
    setProgress(null)
    return watchTask(task.id, {
      onProgress: (message) => {
        setProgress(message)
        if (message.type === 'done') {
          setMessage(`${task.label}已完成。`)
          void queryClient.invalidateQueries({ queryKey: ['candidateResumes', id] })
          if (resumeId) void queryClient.invalidateQueries({ queryKey: ['resumeClaims', resumeId] })
          if (task.label.includes('证据')) {
            void queryClient.invalidateQueries({ queryKey: ['evidence', id] })
          }
        }
        if (message.type === 'error') {
          setError(`${task.label}失败：${message.message ?? '未知原因'}`)
        }
      },
      onClose: (reason) => setError(reason),
    })
  }, [task, id, resumeId, queryClient])

  const upload = useMutation({
    mutationFn: (file: File) => uploadResume(id, file, candidate?.job_id ?? null),
    onSuccess: (result) => {
      setError('')
      setMessage(
        result.duplicate ? '这份简历已上传过，直接使用已有解析结果。' : '简历已上传，开始解析。',
      )
      void queryClient.invalidateQueries({ queryKey: ['candidateResumes', id] })
      if (result.task_id) setTask({ id: result.task_id, label: '简历解析' })
    },
    onError: (err) => setError(getApiErrorMessage(err, '上传简历失败。')),
  })

  const reparse = useMutation({
    mutationFn: (target: string) => reparseResume(target),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['candidateResumes', id] })
      setTask({ id: result.task_id, label: '简历重解析' })
    },
    onError: (err) => setError(getApiErrorMessage(err, '重新解析失败。')),
  })

  const search = useMutation({
    mutationFn: () => searchEvidence(id),
    onSuccess: (result) => {
      setMessage(`已提交 ${result.entities} 条论文声明到 Crossref 检索。`)
      setTask({ id: result.task_id, label: '证据检索' })
    },
    onError: (err) =>
      setError(
        getApiErrorMessage(
          err,
          '证据检索失败：只有带 DOI 的论文声明才能检索，且不能凭名称推断匹配。',
        ),
      ),
  })

  const confirm = useMutation({
    mutationFn: (evidenceId: string) => confirmEvidence(evidenceId),
    onSuccess: () => {
      setMessage('已记录人工复核。')
      void queryClient.invalidateQueries({ queryKey: ['evidence', id] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '确认证据失败。')),
  })

  const assess = useMutation({
    mutationFn: () => createAssessment(id, candidate!.job_id!),
    onSuccess: (assessment) => navigate(`/candidates/${id}/report?assessment=${assessment.id}`),
    onError: (err) =>
      setError(
        getApiErrorMessage(err, '生成评估失败：需要已解析简历、岗位权重与（真实候选人的）授权。'),
      ),
  })

  if (candidateQuery.isError) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取候选人</strong>
            <span>{getApiErrorMessage(candidateQuery.error)}</span>
          </div>
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回列表
          </Link>
        </div>
      </div>
    )
  }

  const resumes = resumesQuery.data ?? []
  const claims = claimsQuery.data
  const voiceConsent = (consentsQuery.data ?? []).find(
    (item) => item.purpose === 'voice_interview' && item.status === 'granted',
  )
  const selectedResume = resumes.find((item) => item.id === resumeId)

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            CANDIDATE FILE
            <span className="hero-eyebrow-line" />
            <span>{candidate?.is_synthetic ? 'SYNTHETIC' : 'REAL'}</span>
          </div>
          <h1>{candidate?.display_name ?? '候选人'}</h1>
          <p>
            {candidate?.job_id ? (
              <Link className="ttc-text-link" to={`/jobs/${candidate.job_id}`}>
                {jobQuery.data?.title ?? '关联岗位'}
              </Link>
            ) : (
              '未绑定岗位'
            )}{' '}
            · 创建于 {formatDateTime(candidate?.created_at)}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary">
            返回列表
          </Link>
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            disabled={!candidate?.job_id || assess.isPending}
            title={candidate?.job_id ? undefined : '候选人或岗位未绑定'}
            onClick={() => assess.mutate()}
          >
            <BadgeCheck size={16} />
            {assess.isPending ? '生成中…' : '生成评估'}
          </button>
          <Link to="/sessions" className="ttc-btn ttc-btn-primary">
            <Mic size={16} />
            发起语音面试
          </Link>
        </div>
      </section>

      {(message || error) && (
        <div className={error ? 'ttc-inline-error' : 'ttc-inline-ok'}>
          {error ? <AlertCircle size={16} /> : <BadgeCheck size={16} />}
          <span>{error || message}</span>
        </div>
      )}

      <div className="ttc-detail-grid">
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">简历</h2>
              <p className="ttc-card-sub">上传后进入解析队列，进度通过 WebSocket 推送。</p>
            </div>
            <FileText size={18} className="ttc-accent-icon" />
          </div>

          <div className="ttc-upload-actions">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.txt"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) upload.mutate(file)
                event.target.value = ''
              }}
            />
            <button
              type="button"
              className="ttc-btn ttc-btn-primary ttc-btn-sm"
              disabled={upload.isPending}
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={15} />
              {upload.isPending ? '上传中…' : '上传简历'}
            </button>
            <span className="ttc-muted">支持 PDF / DOCX / TXT，单个不超过 20 MB</span>
          </div>

          {progress && (
            <div className="ttc-progress-card">
              <div className="ttc-progress-top">
                <strong>{task?.label}</strong>
                <span>{STAGE_LABEL[progress.stage] ?? progress.stage}</span>
              </div>
              <div className="ttc-progress-track">
                <div
                  className="ttc-progress-fill"
                  style={{
                    width:
                      progress.type === 'done'
                        ? '100%'
                        : progress.stage === 'running'
                          ? '60%'
                          : '20%',
                  }}
                />
              </div>
              {progress.message && <p className="ttc-muted">{progress.message}</p>}
            </div>
          )}

          <div className="ttc-file-list">
            {resumes.map((resume) => (
              <div key={resume.id} className={`ttc-file-row ${resume.id === resumeId ? 'is-selected' : ''}`}>
                <button
                  type="button"
                  className="ttc-file-block"
                  onClick={() => setResumeId(resume.id)}
                >
                  <span className="ttc-file-block-head">
                    <FileText size={15} />
                    {resume.file_name}
                  </span>
                  <span className="ttc-file-meta">
                    {resume.parse_status} · {formatDateTime(resume.created_at)}
                  </span>
                </button>
                <button
                  type="button"
                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                  disabled={reparse.isPending}
                  onClick={() => reparse.mutate(resume.id)}
                >
                  <RefreshCw size={14} />
                  重解析
                </button>
              </div>
            ))}
            {resumes.length === 0 && <p className="ttc-muted">还没有上传简历。</p>}
          </div>
        </article>

        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">授权状态</h2>
              <p className="ttc-card-sub">授权只能由候选人本人授予或撤回。</p>
            </div>
            <ShieldCheck size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-consent-list">
            {(consentsQuery.data ?? []).map((consent) => (
              <div key={consent.id} className="ttc-consent-row">
                <div>
                  <strong>{PURPOSE_LABEL[consent.purpose] ?? consent.purpose}</strong>
                  <span className="ttc-muted">
                    {consent.accepted_at ? formatDateTime(consent.accepted_at) : '—'}
                    {consent.revoked_at ? ` · 撤回于 ${formatDateTime(consent.revoked_at)}` : ''}
                  </span>
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
            {(consentsQuery.data ?? []).length === 0 && (
              <p className="ttc-muted">没有任何授权记录，语音面试会被后端拒绝。</p>
            )}
          </div>
          {!voiceConsent && (
            <p className="ttc-inline-hint">
              缺少「语音面试」授权：需要候选人本人授予后才能创建会话。
            </p>
          )}
        </article>
      </div>

      {selectedResume && (
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">声明抽取 · {selectedResume.file_name}</h2>
              <p className="ttc-card-sub">
                共 {claims?.claims.length ?? 0} 条，版本 {claims?.version ?? '—'}（
                {claims?.status ?? '—'}）
              </p>
            </div>
            <FileText size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-claim-groups">
            {Object.entries(
              (claims?.claims ?? []).reduce<Record<string, ResumeClaim[]>>((groups, claim) => {
                groups[claim.type] = [...(groups[claim.type] ?? []), claim]
                return groups
              }, {}),
            ).map(([type, list]) => (
              <div key={type} className="ttc-claim-group">
                <h3>
                  {CLAIM_LABEL[type] ?? type}
                  <span className="ttc-dimension-count">{list.length}</span>
                </h3>
                <ul>
                  {list.map((claim) => (
                    <li key={claim.id} className={claim.needs_review ? 'needs-review' : ''}>
                      {claim.raw_text}
                      {claim.needs_review && <span className="ttc-badge ttc-badge-amber">待核</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {(claims?.claims ?? []).length === 0 && (
              <p className="ttc-muted">这份简历还没有抽取到声明，或解析尚未完成。</p>
            )}
          </div>
        </article>
      )}

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">证据</h2>
            <p className="ttc-card-sub">Crossref DOI 精确检索；A/B 级证据才计入评分。</p>
          </div>
          <div className="ttc-card-actions">
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              disabled={search.isPending}
              onClick={() => search.mutate()}
            >
              <Search size={15} />
              {search.isPending ? '提交中…' : '检索论文证据'}
            </button>
          </div>
        </div>

        <div className="ttc-evidence-list">
          {(evidenceQuery.data ?? []).map((item) => (
            <div key={item.id} className="ttc-evidence-row">
              <div className="ttc-evidence-head">
                <span className={`ttc-badge ${item.grade === 'A' ? 'ttc-badge-green' : 'ttc-badge-blue'}`}>
                  {item.grade} 级
                </span>
                <strong>{item.title ?? item.source_name}</strong>
                <span className="ttc-muted">{formatDate(item.accessed_at)}</span>
              </div>
              <p className="ttc-muted">{item.snippet}</p>
              <div className="ttc-evidence-foot">
                {item.source_url && (
                  <a className="ttc-text-link" href={item.source_url} target="_blank" rel="noreferrer">
                    查看来源
                  </a>
                )}
                {item.verified_by ? (
                  <span className="ttc-badge ttc-badge-green">已人工复核</span>
                ) : (
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={confirm.isPending}
                    onClick={() => confirm.mutate(item.id)}
                  >
                    记录复核
                  </button>
                )}
              </div>
            </div>
          ))}
          {(evidenceQuery.data ?? []).length === 0 && (
            <p className="ttc-muted">还没有证据记录。</p>
          )}
        </div>
      </article>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">语音会话</h2>
            <p className="ttc-card-sub">该候选人的最近语音面试记录。</p>
          </div>
          <Mic size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-session-mini-list">
          {(sessionsQuery.data ?? []).map((session) => (
            <Link key={session.id} to={`/sessions/${session.id}`} className="ttc-session-mini">
              <span className={`ttc-badge ${session.status === 'live' ? 'ttc-badge-green' : 'ttc-badge-blue'}`}>
                {session.status}
              </span>
              <span>{formatDateTime(session.created_at)}</span>
              <span className="ttc-muted">{session.has_report ? '有报告' : '无报告'}</span>
            </Link>
          ))}
          {(sessionsQuery.data ?? []).length === 0 && (
            <p className="ttc-muted">还没有语音会话。</p>
          )}
        </div>
      </article>
      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">沟通纪要</h2>
            <p className="ttc-card-sub">最近一次 AI 语音面试的整理结果，模型只依据通话转写，不做录用建议。</p>
          </div>
          <FileText size={18} className="ttc-accent-icon" />
        </div>

        {!latestReportedSession ? (
          <p className="ttc-muted">该候选人还没有生成过沟通纪要。</p>
        ) : summaryQuery.isLoading ? (
          <p className="ttc-muted">正在读取沟通纪要…</p>
        ) : summaryQuery.isError || !summaryQuery.data ? (
          <p className="ttc-muted">
            {getApiErrorMessage(summaryQuery.error, '沟通纪要读取失败。')}
          </p>
        ) : (
          <>
            <div className="ttc-report-meta">
              <span>轮次：{summaryQuery.data.turn_count}</span>
              <span>模型：{summaryQuery.data.model_version}</span>
              <span>生成于 {formatDateTime(summaryQuery.data.generated_at)}</span>
            </div>
            {summaryQuery.data.overview && (
              <p className="ttc-report-overview">{summaryQuery.data.overview}</p>
            )}
            {summaryQuery.data.qa.length > 0 && (
              <>
                <h3 className="ttc-report-subhead">问答要点</h3>
                <ul className="ttc-plain-list">
                  {summaryQuery.data.qa.map((item) => (
                    <li key={item.question}>
                      <strong>{item.question}</strong>
                      <br />
                      {item.answer_summary}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {summaryQuery.data.followups.length > 0 && (
              <>
                <h3 className="ttc-report-subhead">建议进一步确认</h3>
                <ul className="ttc-plain-list">
                  {summaryQuery.data.followups.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            )}
            {summaryQuery.data.limitations.length > 0 && (
              <ul className="ttc-plain-list ttc-report-limits">
                {summaryQuery.data.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
            <Link
              to={`/sessions/${summaryQuery.data.session_id}`}
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
            >
              查看通话详情
            </Link>
          </>
        )}
      </article>
    </div>
  )
}
