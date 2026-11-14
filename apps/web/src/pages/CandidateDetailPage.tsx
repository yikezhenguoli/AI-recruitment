import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  ExternalLink,
  FileText,
  Mic,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  UploadCloud,
} from 'lucide-react'
import { getCandidate, listCandidateResumes } from '../api/candidates'
import { listConsents } from '../api/consents'
import { confirmEvidence, listEvidence, searchEvidence } from '../api/evidence'
import { getJob } from '../api/jobs'
import { watchTask } from '../api/progress'
import { getResumeClaims, getResumeText, reparseResume, uploadResume } from '../api/resumes'
import { createAssessment } from '../api/assessments'
import { getVoiceSummary, listVoiceSessions } from '../api/voice'
import { getApiErrorMessage } from '../lib/apiError'
import { EVIDENCE_GRADE_CLASS, formatDate, formatDateTime, VOICE_STATUS_CLASS, VOICE_STATUS_LABELS } from '../lib/format'
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

type DetailTab = 'evidence' | 'voice' | 'consents'

function formatConfidence(value: number): string {
  const pct = value <= 1 ? Math.round(value * 100) : Math.round(value)
  return `${pct}%`
}

function getStageIndex(progress: TaskProgressMessage | null): number {
  if (!progress) return -1
  if (progress.type === 'done' || progress.stage === 'succeeded') return 2
  if (progress.stage === 'running') return 1
  return 0
}

const ACCEPTED_RESUME_EXTENSIONS = ['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.webp']

function ocrLabel(model?: string | null): string {
  const raw = model?.split('+ocr:')[1]
  return raw ? `OCR · ${raw.replace(/^vlm:/, '')}` : ''
}

export default function CandidateDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [resumeId, setResumeId] = useState('')
  const [claimFilter, setClaimFilter] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<DetailTab>('evidence')
  const [isDragging, setIsDragging] = useState(false)
  const [task, setTask] = useState<{ id: string; label: string } | null>(null)
  const [progress, setProgress] = useState<TaskProgressMessage | null>(null)
  const [error, setError] = useState('')
  const [resumeText, setResumeText] = useState<{
    version: number
    extractor_model: string | null
    text: string
  } | null>(null)
  const [textLoading, setTextLoading] = useState(false)
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

  const resumes = resumesQuery.data ?? []

  useEffect(() => {
    if (!resumeId && resumes.length > 0) {
      setResumeId(resumes[0].id)
    }
  }, [resumeId, resumes])

  useEffect(() => {
    if (!task) return
    setProgress(null)
    return watchTask(task.id, {
      onProgress: (msg) => {
        setProgress(msg)
        if (msg.type === 'done') {
          setMessage(`${task.label}已完成。`)
          void queryClient.invalidateQueries({ queryKey: ['candidateResumes', id] })
          if (resumeId) void queryClient.invalidateQueries({ queryKey: ['resumeClaims', resumeId] })
          if (task.label.includes('证据')) {
            void queryClient.invalidateQueries({ queryKey: ['evidence', id] })
          }
        }
        if (msg.type === 'error') {
          setError(`${task.label}失败：${msg.message ?? '未知原因'}`)
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
      setError('')
      void queryClient.invalidateQueries({ queryKey: ['candidateResumes', id] })
      setTask({ id: result.task_id, label: '简历重解析' })
    },
    onError: (err) => setError(getApiErrorMessage(err, '重新解析失败。')),
  })

  const search = useMutation({
    mutationFn: () => searchEvidence(id),
    onSuccess: (result) => {
      setError('')
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
      setError('')
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

  const claimList = claimsQuery.data?.claims ?? []
  const claimTypes = useMemo(() => {
    const types = new Set<string>()
    for (const item of claimList) types.add(item.type)
    return Array.from(types)
  }, [claimList])

  const needsReviewCount = useMemo(
    () => claimList.filter((item) => item.needs_review).length,
    [claimList],
  )

  const filteredClaims = useMemo(() => {
    if (claimFilter === 'all') return claimList
    if (claimFilter === 'needs_review') return claimList.filter((item) => item.needs_review)
    return claimList.filter((item) => item.type === claimFilter)
  }, [claimList, claimFilter])

  const groupedClaims = useMemo(
    () =>
      Object.entries(
        filteredClaims.reduce<Record<string, ResumeClaim[]>>((acc, claim) => {
          ;(acc[claim.type] ??= []).push(claim)
          return acc
        }, {}),
      ),
    [filteredClaims],
  )

  function handleSelectedFile(file?: File) {
    if (!file) return
    const lower = file.name.toLowerCase()
    if (!ACCEPTED_RESUME_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setError('仅支持上传 PDF、DOCX、TXT 或 PNG/JPEG/WebP 图片简历。')
      return
    }
    upload.mutate(file)
  }

  async function toggleText() {
    if (resumeText) {
      setResumeText(null)
      return
    }
    if (!resumeId) return
    setTextLoading(true)
    try {
      setResumeText(await getResumeText(resumeId))
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '读取转写文本失败。'))
    } finally {
      setTextLoading(false)
    }
  }

  function downloadText(text: string, fileName: string) {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${fileName.replace(/\.[^.]+$/, '')}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (candidateQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-skeleton-card" />
      </div>
    )
  }

  if (candidateQuery.isError || !candidate) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取候选人</strong>
            <span>{getApiErrorMessage(candidateQuery.error)}</span>
          </div>
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回候选人
          </Link>
        </div>
      </div>
    )
  }

  const evidenceList = evidenceQuery.data ?? []
  const sessionsList = sessionsQuery.data ?? []
  const consentsList = consentsQuery.data ?? []
  const voiceConsent = consentsList.find(
    (item) => item.purpose === 'voice_interview' && item.status === 'granted',
  )
  const selectedResume = resumes.find((item) => item.id === resumeId)
  const stageIdx = getStageIndex(progress)
  const stageSteps = [
    { key: 'queued', label: '队列接收' },
    { key: 'running', label: '结构化解析' },
    { key: 'succeeded', label: '声明落库' },
  ]

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="ttc-mini-heading">
            <FileText size={14} />
            <span>{candidate.is_synthetic ? 'SYNTHETIC DEMO PROFILE' : 'CANDIDATE WORKBENCH'}</span>
          </div>
          <h1>{candidate.display_name}</h1>
          <p>
            {jobQuery.data ? `应聘岗位：${jobQuery.data.title}` : '未绑定岗位'} ·{' '}
            来源 {candidate.source} · 创建于 {formatDateTime(candidate.created_at)}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary">
            返回列表
          </Link>
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            disabled={!candidate.job_id || assess.isPending}
            title={candidate.job_id ? undefined : '候选人尚未绑定岗位'}
            onClick={() => assess.mutate()}
          >
            <BadgeCheck size={16} />
            {assess.isPending ? '生成中…' : '生成双账本评估'}
          </button>
          <Link to="/sessions" className="ttc-btn ttc-btn-primary">
            <Mic size={16} />
            语音初筛
          </Link>
        </div>
      </section>

      {(error || message) && (
        <div className={error ? 'ttc-inline-error' : 'ttc-inline-ok'} role={error ? 'alert' : 'status'}>
          {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{error || message}</span>
        </div>
      )}

      {progress && (
        <div className="ttc-progress-card">
          <div className="ttc-progress-top">
            <strong>{task?.label}</strong>
            <span>{STAGE_LABEL[progress.stage] ?? progress.stage}</span>
          </div>
          <div className="ttc-stepper" aria-label="任务阶段进度">
            {stageSteps.map((step, index) => {
              const isDone = progress.type === 'done' || stageIdx > index
              const isCurrent = progress.type !== 'done' && progress.type !== 'error' && stageIdx === index
              const isError = progress.type === 'error' && stageIdx === index
              return (
                <div
                  key={step.key}
                  className={`ttc-step-node ${isDone ? 'is-done' : ''} ${isCurrent ? 'is-current' : ''} ${isError ? 'is-error' : ''}`}
                >
                  <span className="ttc-step-dot">{isDone ? '✓' : index + 1}</span>
                  <span className="ttc-step-name">{step.label}</span>
                </div>
              )
            })}
          </div>
          <div className="ttc-progress-track">
            <div
              className="ttc-progress-fill"
              style={{
                width:
                  progress.type === 'done'
                    ? '100%'
                    : progress.stage === 'running'
                      ? '62%'
                      : progress.type === 'error'
                        ? '100%'
                        : '28%',
              }}
            />
          </div>
          {progress.message && <p className="ttc-muted">{progress.message}</p>}
        </div>
      )}

      <div className="ttc-workbench-grid">
        <div className="ttc-workbench-col">
          <article className="ttc-card">
            <div className="ttc-card-head">
              <div>
                <h2>简历版本与解析</h2>
                <p className="ttc-card-sub">拖拽或选择 PDF / DOCX / TXT / 图片触发真实解析流水线；扫描件自动视觉 OCR 转写</p>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.webp"
                hidden
                onChange={(event) => {
                  handleSelectedFile(event.target.files?.[0])
                  event.target.value = ''
                }}
              />
            </div>

            <div
              className={`ttc-dropzone ${isDragging ? 'is-dragging' : ''}`}
              onDragOver={(event) => {
                event.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setIsDragging(false)
                handleSelectedFile(event.dataTransfer.files?.[0])
              }}
            >
              <UploadCloud size={24} className="ttc-accent-icon" aria-hidden="true" />
              <div>
                <strong>拖拽 PDF / DOCX / TXT / 图片简历到此处，或点击按钮上传</strong>
                <span>文件直传后端队列，通过 WebSocket 实时推回解析与声明落库阶段</span>
              </div>
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                disabled={upload.isPending}
                onClick={() => fileRef.current?.click()}
              >
                <Upload size={14} />
                {upload.isPending ? '上传中…' : '选择文件'}
              </button>
            </div>

            <div className="ttc-resume-list">
              {resumes.map((resume) => (
                <div
                  key={resume.id}
                  className={`ttc-resume-row ${resumeId === resume.id ? 'is-active' : ''}`}
                >
                  <button
                    type="button"
                    className="ttc-resume-select"
                    onClick={() => {
                      setResumeId(resume.id)
                      setResumeText(null)
                    }}
                  >
                    <strong>{resume.file_name}</strong>
                    <span className="ttc-muted">
                      解析状态：{resume.parse_status} · 上传于 {formatDate(resume.created_at)}
                      {ocrLabel(resume.extractor_model) && ` · ${ocrLabel(resume.extractor_model)}`}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={reparse.isPending}
                    onClick={() => reparse.mutate(resume.id)}
                  >
                    <RefreshCw size={13} />
                    重解析
                  </button>
                </div>
              ))}
              {resumes.length === 0 && <p className="ttc-muted">还没有上传过简历。</p>}
            </div>
          </article>

          <article className="ttc-card">
            <div className="ttc-card-head">
              <div>
                <h2>结构化声明（Claims）</h2>
                <p className="ttc-card-sub">
                  {selectedResume
                    ? `来自「${selectedResume.file_name}」· 标注页码与抽取置信度`
                    : '选择上方简历以查看解析出的声明'}
                </p>
              </div>
              <div className="ttc-card-actions">
                <button
                  type="button"
                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                  disabled={!resumeId || textLoading}
                  onClick={() => void toggleText()}
                >
                  <FileText size={14} />
                  {resumeText ? '收起转写文本' : textLoading ? '读取中…' : '查看转写文本'}
                </button>
                <span className="ttc-badge ttc-badge-blue">{claimList.length} 条</span>
              </div>
            </div>

            {resumeText && (
              <div className="ttc-transcript-block">
                <div className="ttc-transcript-head">
                  <span>
                    第 {resumeText.version} 版 · {resumeText.extractor_model ?? '未知模型'} ·{' '}
                    {resumeText.text.length} 字符
                  </span>
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-ghost ttc-btn-sm"
                    onClick={() => downloadText(resumeText.text, selectedResume?.file_name ?? 'resume')}
                  >
                    下载 .txt
                  </button>
                </div>
                <pre className="ttc-transcript">{resumeText.text}</pre>
              </div>
            )}

            {claimList.length > 0 && (
              <div className="ttc-chip-row ttc-chip-row-spaced" role="group" aria-label="按类型筛选声明">
                <button
                  type="button"
                  className={`ttc-chip ${claimFilter === 'all' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setClaimFilter('all')}
                >
                  全部 ({claimList.length})
                </button>
                <button
                  type="button"
                  className={`ttc-chip ${claimFilter === 'needs_review' ? 'ttc-chip-blue' : ''}`}
                  onClick={() => setClaimFilter('needs_review')}
                >
                  需人工确认 ({needsReviewCount})
                </button>
                {claimTypes.map((type) => (
                  <button
                    key={type}
                    type="button"
                    className={`ttc-chip ${claimFilter === type ? 'ttc-chip-blue' : ''}`}
                    onClick={() => setClaimFilter(type)}
                  >
                    {CLAIM_LABEL[type] ?? type}
                  </button>
                ))}
              </div>
            )}

            {claimsQuery.isLoading && <p className="ttc-muted">正在读取声明…</p>}
            {claimsQuery.isError && <p className="ttc-muted">{getApiErrorMessage(claimsQuery.error)}</p>}

            {claimsQuery.data && (
              <div className="ttc-claim-groups">
                {groupedClaims.map(([type, list]) => (
                  <div key={type} className="ttc-claim-group">
                    <h3>
                      {CLAIM_LABEL[type] ?? type}
                      <span className="ttc-dimension-count">{list.length}</span>
                    </h3>
                    <ul>
                      {list.map((claim) => (
                        <li key={claim.id} className={claim.needs_review ? 'needs-review' : ''}>
                          <div className="ttc-claim-line-body">
                            <span>{claim.raw_text}</span>
                            <div className="ttc-claim-pills">
                              {claim.page_no !== null && <span className="ttc-mini-pill">P{claim.page_no}</span>}
                              {claim.confidence !== null && (
                                <span className="ttc-mini-pill">置信 {formatConfidence(claim.confidence)}</span>
                              )}
                              {claim.needs_review && (
                                <span className="ttc-badge ttc-badge-amber">待核对</span>
                              )}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
                {groupedClaims.length === 0 && (
                  <p className="ttc-muted">当前筛选下没有匹配的解析声明。</p>
                )}
              </div>
            )}
          </article>
        </div>

        <aside className="ttc-workbench-col">
          <div className="ttc-tablist" role="tablist" aria-label="候选人核验、语音与授权面板">
            <button
              type="button"
              role="tab"
              id="tab-evidence"
              aria-selected={activeTab === 'evidence'}
              aria-controls="panel-evidence"
              className={`ttc-tab ${activeTab === 'evidence' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('evidence')}
            >
              证据链核验
              <span className="ttc-tab-count">{evidenceList.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              id="tab-voice"
              aria-selected={activeTab === 'voice'}
              aria-controls="panel-voice"
              className={`ttc-tab ${activeTab === 'voice' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('voice')}
            >
              语音初筛
              <span className="ttc-tab-count">{sessionsList.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              id="tab-consents"
              aria-selected={activeTab === 'consents'}
              aria-controls="panel-consents"
              className={`ttc-tab ${activeTab === 'consents' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('consents')}
            >
              隐私授权
              <span className="ttc-tab-count">{consentsList.length}</span>
            </button>
          </div>

          {activeTab === 'evidence' && (
            <article
              id="panel-evidence"
              role="tabpanel"
              aria-labelledby="tab-evidence"
              className="ttc-card"
            >
              <div className="ttc-card-head">
                <div>
                  <h2>外部证据检索与复核</h2>
                  <p className="ttc-card-sub">
                    基于声明中的 DOI 调用 Crossref 检索（绝不凭姓名推断），并由人工点击确认。
                  </p>
                </div>
                <button
                  type="button"
                  className="ttc-btn ttc-btn-primary ttc-btn-sm"
                  disabled={search.isPending}
                  onClick={() => search.mutate()}
                >
                  <Search size={14} />
                  {search.isPending ? '提交中…' : 'Crossref 检验证据'}
                </button>
              </div>

              <div className="ttc-evidence-list">
                {evidenceList.map((item) => (
                  <div key={item.id} className="ttc-evidence-row">
                    <div className="ttc-evidence-head">
                      <span className={`ttc-badge ${EVIDENCE_GRADE_CLASS[item.grade]}`}>
                        等级 {item.grade}
                      </span>
                      <strong>{item.title ?? item.source_name}</strong>
                      <span className="ttc-muted">{item.match_method ?? item.source_name}</span>
                    </div>
                    {item.snippet && <p>{item.snippet}</p>}
                    <div className="ttc-evidence-foot">
                      <div className="ttc-dim-refs">
                        {item.source_url && (
                          <a className="ttc-text-link" href={item.source_url} target="_blank" rel="noreferrer">
                            查看来源 <ExternalLink size={12} />
                          </a>
                        )}
                        <span className="ttc-muted">检索于 {formatDate(item.accessed_at)}</span>
                      </div>
                      {item.verified_by ? (
                        <span className="ttc-badge ttc-badge-green">已人工复核</span>
                      ) : (
                        <button
                          type="button"
                          className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          disabled={confirm.isPending}
                          onClick={() => confirm.mutate(item.id)}
                        >
                          <CheckCircle2 size={14} />
                          确认该证据
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {evidenceList.length === 0 && (
                  <p className="ttc-muted">
                    暂无外部证据记录。上传包含论文 DOI 的简历后，可点击上方按钮检索 Crossref。
                  </p>
                )}
              </div>
            </article>
          )}

          {activeTab === 'voice' && (
            <article
              id="panel-voice"
              role="tabpanel"
              aria-labelledby="tab-voice"
              className="ttc-card"
            >
              <div className="ttc-card-head">
                <div>
                  <h2>语音面试会话与纪要</h2>
                  <p className="ttc-card-sub">
                    展示最近一次 AI 语音初筛的通话列表与整理纪要（仅依据转写文本，不做录用决定）
                  </p>
                </div>
                <Link to="/sessions" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
                  <Mic size={14} />
                  去发起会话
                </Link>
              </div>

              {sessionsList.length > 0 ? (
                <div className="ttc-session-mini-list">
                  {sessionsList.map((session) => (
                    <Link key={session.id} to={`/sessions/${session.id}`} className="ttc-session-mini">
                      <span className={`ttc-badge ${VOICE_STATUS_CLASS[session.status] ?? 'ttc-badge-blue'}`}>
                        {VOICE_STATUS_LABELS[session.status] ?? session.status}
                      </span>
                      <strong>{session.job_title ?? '语音初筛'}</strong>
                      <span className="ttc-muted">{formatDateTime(session.created_at)}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="ttc-muted">暂无语音初筛会话。</p>
              )}

              <div className="ttc-voice-summary-box">
                <h3 className="ttc-report-subhead">最近沟通纪要</h3>
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
                        <h4 className="ttc-report-subhead">问答要点</h4>
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
                        <h4 className="ttc-report-subhead">建议进一步确认</h4>
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
                      查看完整通话与转写
                    </Link>
                  </>
                )}
              </div>
            </article>
          )}

          {activeTab === 'consents' && (
            <article
              id="panel-consents"
              role="tabpanel"
              aria-labelledby="tab-consents"
              className="ttc-card"
            >
              <div className="ttc-card-head">
                <div>
                  <h2>候选人隐私授权记录</h2>
                  <p className="ttc-card-sub">
                    未授权或撤回授权时，简历解析与实时语音初筛会被后端合规门禁拦截。
                  </p>
                </div>
                <ShieldCheck size={18} className="ttc-accent-icon" />
              </div>

              <div className="ttc-consent-list">
                {consentsList.map((consent) => (
                  <div key={consent.id} className="ttc-consent-row">
                    <div>
                      <strong>{PURPOSE_LABEL[consent.purpose] ?? consent.purpose}</strong>
                      <span className="ttc-muted">
                        授权时间：{consent.accepted_at ? formatDateTime(consent.accepted_at) : '—'}
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
                {consentsList.length === 0 && (
                  <p className="ttc-muted">没有任何授权记录，语音面试会被后端拒绝。</p>
                )}
              </div>

              {!voiceConsent && (
                <p className="ttc-inline-hint">
                  缺少「语音面试」授权：需要候选人本人授予后才能创建语音初筛会话。
                </p>
              )}
            </article>
          )}
        </aside>
      </div>
    </div>
  )
}
