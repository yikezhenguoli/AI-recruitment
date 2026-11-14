import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowRight,
  Briefcase,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Upload,
  UserPlus,
  Users,
  XCircle,
} from 'lucide-react'
import { listJobs, getJob } from '../api/jobs'
import {
  createCandidate,
  listCandidateResumes,
  listCandidates,
} from '../api/candidates'
import { uploadResume } from '../api/resumes'
import { getAssessment, matchResume } from '../api/assessments'
import { watchTask } from '../api/progress'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { PARSE_STATUS_LABEL, JOB_STATUS_LABEL } from '../types'
import type { Candidate, ParseStatus } from '../types'

type RowStage =
  | 'creating'
  | 'uploading'
  | 'queued'
  | 'parsing'
  | 'evaluating'
  | 'done'
  | 'error'

interface BatchRow {
  candidateId: string
  name: string
  fileName: string
  stage: RowStage
  taskId?: string
  resumeId?: string
  parseStatus?: ParseStatus
  score?: number | null
  category?: string
  confidence?: number
  summary?: string
  assessmentId?: string
  error?: string
}

const STAGE_LABEL: Record<RowStage, string> = {
  creating: '创建候选人',
  uploading: '上传简历',
  queued: '等待解析',
  parsing: '解析简历',
  evaluating: '匹配评估',
  done: '已完成',
  error: '失败',
}

const FINAL_STAGES: RowStage[] = ['done', 'error']

function fileStem(name: string): string {
  return name.replace(/\.[^.]+$/, '').slice(0, 80) || '候选人'
}

export default function CandidatesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const jobId = searchParams.get('job') || ''
  const [files, setFiles] = useState<File[]>([])
  const [rows, setRows] = useState<Record<string, BatchRow>>({})
  const [batchRunning, setBatchRunning] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const cleanupsRef = useRef<Array<() => void>>([])
  const evaluatedRef = useRef<Set<string>>(new Set())

  useEffect(
    () => () => {
      cleanupsRef.current.forEach((cleanup) => cleanup())
      cleanupsRef.current = []
    },
    [],
  )

  const jobsQuery = useQuery({
    queryKey: ['jobs', 'candidates'],
    queryFn: () => listJobs({ limit: 100 }),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
  })
  const candidatesQuery = useQuery({
    queryKey: ['candidates', jobId],
    queryFn: () => listCandidates({ job_id: jobId, limit: 100 }),
    enabled: Boolean(jobId),
  })

  const job = jobQuery.data
  const existing = candidatesQuery.data ?? []
  const rowsList = Object.values(rows)

  const updateRow = (candidateId: string, patch: Partial<BatchRow>) => {
    setRows((prev) => {
      const row = prev[candidateId]
      if (!row) return prev
      return { ...prev, [candidateId]: { ...row, ...patch } }
    })
  }

  const evaluate = async (row: BatchRow, resumeId: string, force = false) => {
    if (!force && evaluatedRef.current.has(row.candidateId)) return
    evaluatedRef.current.add(row.candidateId)
    updateRow(row.candidateId, { stage: 'evaluating', resumeId })
    try {
      const match = await matchResume(resumeId, {
        job_id: jobId,
        explain: true,
        top_k: 5,
      })
      const assessment = await getAssessment(match.assessment_id)
      const dimensions = assessment.report.match_ledger?.dimensions ?? []
      const summary =
        match.explanation?.summary ||
        dimensions.find((item) => item.score != null)?.reasoning ||
        ''
      updateRow(row.candidateId, {
        stage: 'done',
        score: match.match_score,
        category: match.category,
        confidence: match.confidence,
        summary,
        assessmentId: match.assessment_id,
      })
    } catch (err: unknown) {
      evaluatedRef.current.delete(row.candidateId)
      updateRow(row.candidateId, {
        stage: 'error',
        error: getApiErrorMessage(err, '匹配评估失败。'),
      })
    }
  }

  const pollResume = (candidateId: string, resumeId: string, row: BatchRow) => {
    let attempts = 0
    const timer = window.setInterval(async () => {
      attempts += 1
      try {
        const resumes = await listCandidateResumes(candidateId)
        const target = resumes.find((item) => item.id === resumeId)
        if (!target) return
        updateRow(candidateId, { parseStatus: target.parse_status })
        if (target.parse_status === 'done') {
          window.clearInterval(timer)
          await evaluate(row, resumeId)
        } else if (target.parse_status === 'failed') {
          window.clearInterval(timer)
          updateRow(candidateId, { stage: 'error', error: '后端解析失败，请查看 resume 状态或重试。' })
        }
      } catch {
        // 轮询失败时保持原状态，下一次继续。
      }
      if (attempts >= 120) {
        window.clearInterval(timer)
        updateRow(candidateId, {
          stage: 'error',
          error: '解析超时（10 分钟）。请确认 worker 正在运行。',
        })
      }
    }, 3000)
    cleanupsRef.current.push(() => window.clearInterval(timer))
  }

  const watchParseTask = (
    candidateId: string,
    taskId: string,
    resumeId: string,
    row: BatchRow,
  ) => {
    const cleanup = watchTask(taskId, {
      onEvent: (event) => {
        if (event.type === 'progress') {
          updateRow(candidateId, {
            stage: event.stage === 'running' ? 'parsing' : 'queued',
          })
        } else if (event.type === 'done') {
          updateRow(candidateId, { stage: 'evaluating' })
          void evaluate(row, resumeId)
        } else if (event.type === 'error') {
          updateRow(candidateId, {
            stage: 'error',
            error: event.message || '简历解析任务失败。',
          })
        }
      },
      onError: (message) => {
        // WebSocket 失败不直接判死；轮询会继续兜底。
        updateRow(candidateId, { error: `${message} 已切换轮询。` })
      },
    })
    cleanupsRef.current.push(cleanup)
    pollResume(candidateId, resumeId, row)
  }

  const processFile = async (file: File) => {
    const displayName = fileStem(file.name)
    let candidateId = ''
    try {
      const candidate = await createCandidate({
        display_name: displayName,
        job_id: jobId,
        source: 'upload',
        is_synthetic: true,
      })
      candidateId = candidate.id
      setRows((prev) => ({
        ...prev,
        [candidateId]: {
          candidateId,
          name: displayName,
          fileName: file.name,
          stage: 'uploading',
        },
      }))
      const uploaded = await uploadResume(candidateId, jobId, file)
      updateRow(candidateId, {
        stage: 'queued',
        taskId: uploaded.task_id,
        resumeId: uploaded.resume_id,
        parseStatus: uploaded.parse_status,
      })
      const row: BatchRow = {
        candidateId,
        name: displayName,
        fileName: file.name,
        stage: 'queued',
      }
      if (uploaded.task_id) {
        watchParseTask(candidateId, uploaded.task_id, uploaded.resume_id, row)
      } else {
        pollResume(candidateId, uploaded.resume_id, row)
      }
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, '上传或创建候选人失败。')
      if (candidateId) {
        updateRow(candidateId, { stage: 'error', error: message })
      } else {
        setPageError(message)
      }
    }
  }

  const startBatch = async () => {
    if (!jobId || files.length === 0) return
    setPageError(null)
    setBatchRunning(true)
    try {
      for (const file of files) {
        await processFile(file)
      }
      setFiles([])
    } finally {
      setBatchRunning(false)
      await queryClient.invalidateQueries({ queryKey: ['candidates', jobId] })
    }
  }

  const rerunCandidate = async (candidate: Candidate) => {
    setPageError(null)
    try {
      const resumes = await listCandidateResumes(candidate.id)
      const resume = resumes[0]
      if (!resume) {
        setPageError(`${candidate.display_name} 没有简历，无法评估。`)
        return
      }
      setRows((prev) => ({
        ...prev,
        [candidate.id]: {
          candidateId: candidate.id,
          name: candidate.display_name,
          fileName: resume.file_name,
          stage: 'evaluating',
          resumeId: resume.id,
          parseStatus: resume.parse_status,
        },
      }))
      await evaluate(
        {
          candidateId: candidate.id,
          name: candidate.display_name,
          fileName: resume.file_name,
          stage: 'evaluating',
        },
        resume.id,
        true,
      )
    } catch (err: unknown) {
      setPageError(getApiErrorMessage(err, '读取候选人简历失败。'))
    }
  }

  const selectJob = (nextJobId: string) => {
    setSearchParams(nextJobId ? { job: nextJobId } : {})
    setRows({})
    setFiles([])
    setPageError(null)
  }

  const onFiles = (list: FileList | null) => {
    if (!list) return
    const next: File[] = []
    for (const file of Array.from(list)) {
      const lower = file.name.toLowerCase()
      if (!lower.endsWith('.pdf') && !lower.endsWith('.docx') && !lower.endsWith('.txt')) {
        setPageError(`不支持的文件类型：${file.name}（仅 PDF / DOCX / TXT）。`)
        continue
      }
      if (file.size > 20 * 1024 * 1024) {
        setPageError(`文件超过 20 MB：${file.name}`)
        continue
      }
      next.push(file)
    }
    setFiles((prev) => [...prev, ...next])
  }

  const resolved = rowsList.filter((row) => FINAL_STAGES.includes(row.stage)).length
  const progress =
    rowsList.length > 0 ? Math.round((resolved / rowsList.length) * 100) : 0

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            CANDIDATE PIPELINE
            <span className="hero-eyebrow-line" />
            <span>/api/v1/candidates</span>
          </div>
          <h1>候选人筛选</h1>
          <p>
            选择岗位后批量上传简历；后端 worker 解析 claims，小模型 + DeepSeek 生成匹配结果，
            失败时如实显示原因。
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <Briefcase size={15} />
            岗位管理
          </Link>
          {jobId && (
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary"
              onClick={() => selectJob('')}
            >
              <RefreshCw size={15} />
              更换岗位
            </button>
          )}
        </div>
      </section>

      {pageError && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertCircle size={15} />
          <span>{pageError}</span>
        </div>
      )}

      {!jobId && (
        <section className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">选择岗位</h2>
              <p className="ttc-card-sub">候选人必须归属岗位；岗位来自 /api/v1/jobs</p>
            </div>
          </div>
          {jobsQuery.isLoading && <p className="ttc-muted">正在读取岗位…</p>}
          {jobsQuery.isError && (
            <div className="ttc-inline-error">
              <AlertCircle size={16} />
              <span>{getApiErrorMessage(jobsQuery.error, '读取岗位失败。')}</span>
            </div>
          )}
          {!jobsQuery.isLoading && (jobsQuery.data ?? []).length === 0 && (
            <div className="ttc-empty-state ttc-empty-compact">
              <Briefcase size={22} />
              <strong>还没有岗位</strong>
              <Link to="/jobs/new" className="ttc-btn ttc-btn-primary ttc-btn-sm">
                <Plus size={14} />
                新建岗位
              </Link>
            </div>
          )}
          <div className="ttc-job-grid-compact">
            {(jobsQuery.data ?? []).map((item) => (
              <button
                key={item.id}
                type="button"
                className="ttc-job-pick-card"
                onClick={() => selectJob(item.id)}
              >
                <span className="ttc-job-icon">
                  <Briefcase size={17} />
                </span>
                <div>
                  <strong>{item.title}</strong>
                  <span>
                    {item.department || '未设置部门'} · {JOB_STATUS_LABEL[item.status]}
                  </span>
                </div>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        </section>
      )}

      {jobId && (
        <>
          <section className="ttc-selected-job">
            <span className="ttc-job-icon">
              <Briefcase size={18} />
            </span>
            <div>
              <strong>{job?.title ?? '正在读取岗位…'}</strong>
              <span>
                {job ? `${JOB_STATUS_LABEL[job.status]} · ${job.department || '未设置部门'}` : ''}
              </span>
            </div>
            <Link to={`/jobs/${jobId}`} className="ttc-text-link">
              查看岗位
              <ArrowRight size={14} />
            </Link>
          </section>

          <section className="ttc-upload-panel">
            <div className="ttc-upload-head">
              <div>
                <div className="ttc-mini-heading">
                  <Upload size={14} />
                  RESUME INTAKE
                </div>
                <h2>批量上传简历</h2>
                <p>
                  每个文件会创建一个合成候选人、上传简历并提交解析任务；仅支持 PDF / DOCX /
                  TXT，单文件 ≤ 20 MB。
                </p>
              </div>
              <span className="ttc-badge ttc-badge-blue">{files.length} 个待上传</span>
            </div>

            <label className="ttc-dropzone">
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                onChange={(event) => onFiles(event.target.files)}
              />
              <Upload size={26} />
              <strong>点击选择或拖入简历文件</strong>
              <span>上传后由后端 worker 解析，不使用前端模拟数据。</span>
            </label>

            {files.length > 0 && (
              <div className="ttc-file-list">
                {files.map((file, index) => (
                  <div className="ttc-file-row" key={`${file.name}-${index}`}>
                    <FileText size={16} />
                    <span>{file.name}</span>
                    <small>{(file.size / 1024).toFixed(0)} KB</small>
                    <button
                      type="button"
                      className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                      onClick={() =>
                        setFiles((prev) => prev.filter((_, itemIndex) => itemIndex !== index))
                      }
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="ttc-upload-actions">
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                onClick={() => setRows({})}
                disabled={rowsList.length === 0 || batchRunning}
              >
                清空本次结果
              </button>
              <button
                type="button"
                className="ttc-btn ttc-btn-primary"
                onClick={() => void startBatch()}
                disabled={files.length === 0 || batchRunning}
              >
                {batchRunning ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Sparkles size={16} />
                )}
                开始解析与匹配
              </button>
            </div>
          </section>

          {rowsList.length > 0 && (
            <section className="ttc-results-panel">
              <div className="ttc-results-head">
                <div>
                  <h2>本次处理进度</h2>
                  <p>
                    {resolved} / {rowsList.length} 已完成 · WebSocket 实时进度 + 轮询兜底
                  </p>
                </div>
                <span className="ttc-badge ttc-badge-blue">{progress}%</span>
              </div>
              <div className="ttc-progress-track">
                <i style={{ width: `${progress}%` }} />
              </div>
              <div className="ttc-table-scroll">
                <table className="ttc-result-table">
                  <thead>
                    <tr>
                      <th>候选人</th>
                      <th>文件</th>
                      <th>解析</th>
                      <th>匹配分</th>
                      <th>类别</th>
                      <th>结论</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rowsList.map((row) => (
                      <tr key={row.candidateId}>
                        <td>
                          <strong>{row.name}</strong>
                          <span className={`ttc-stage-pill ttc-stage-${row.stage}`}>
                            {STAGE_LABEL[row.stage]}
                          </span>
                        </td>
                        <td>
                          <span className="ttc-muted">{row.fileName}</span>
                        </td>
                        <td>
                          {row.parseStatus
                            ? PARSE_STATUS_LABEL[row.parseStatus]
                            : row.stage === 'error'
                              ? '—'
                              : '处理中'}
                        </td>
                        <td>
                          <span className="ttc-score-badge">
                            {row.score != null ? row.score.toFixed(1) : '—'}
                          </span>
                        </td>
                        <td>
                          {row.category ?? '—'}
                          {row.confidence != null && (
                            <small className="ttc-muted">
                              {' '}
                              ({Math.round(row.confidence * 100)}%)
                            </small>
                          )}
                        </td>
                        <td>
                          {row.error ? (
                            <span className="ttc-inline-error-text">{row.error}</span>
                          ) : (
                            <span className="ttc-muted">
                              {row.summary || (row.stage === 'done' ? '已完成' : '处理中…')}
                            </span>
                          )}
                        </td>
                        <td>
                          {row.stage === 'done' && (
                            <Link
                              to={`/candidates/${row.candidateId}/report?job=${jobId}${
                                row.assessmentId ? `&assessment=${row.assessmentId}` : ''
                              }`}
                              className="ttc-text-link"
                            >
                              报告
                              <ArrowRight size={13} />
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="ttc-card ttc-card-pad">
            <div className="ttc-card-header">
              <div>
                <h2 className="ttc-card-title">岗位候选人</h2>
                <p className="ttc-card-sub">
                  GET /api/v1/candidates?job_id=… · 共 {existing.length} 人
                </p>
              </div>
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                onClick={() => void candidatesQuery.refetch()}
              >
                <RefreshCw size={14} className={candidatesQuery.isFetching ? 'animate-spin' : ''} />
                刷新
              </button>
            </div>

            {candidatesQuery.isError && (
              <div className="ttc-inline-error">
                <AlertCircle size={16} />
                <span>{getApiErrorMessage(candidatesQuery.error, '读取候选人失败。')}</span>
              </div>
            )}

            {existing.length === 0 && !candidatesQuery.isLoading && (
              <div className="ttc-empty-state ttc-empty-compact">
                <Users size={22} />
                <strong>该岗位还没有候选人</strong>
                <span>上传简历后会自动创建候选人记录。</span>
              </div>
            )}

            <div className="ttc-candidate-list">
              {existing.map((candidate) => {
                const row = rows[candidate.id]
                return (
                  <article className="ttc-candidate-row" key={candidate.id}>
                    <span className="ttc-avatar">{candidate.display_name.slice(0, 2)}</span>
                    <div>
                      <strong>{candidate.display_name}</strong>
                      <span>
                        {candidate.source} · 创建于 {formatDateTime(candidate.created_at)}
                      </span>
                    </div>
                    {row?.stage === 'done' && row.score != null && (
                      <span className="ttc-score-badge">{row.score.toFixed(1)}</span>
                    )}
                    <div className="ttc-card-actions">
                      <Link
                        to={`/candidates/${candidate.id}?job=${jobId}`}
                        className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                      >
                        详情
                      </Link>
                      <button
                        type="button"
                        className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        onClick={() => void rerunCandidate(candidate)}
                      >
                        <Sparkles size={13} />
                        重新匹配
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        </>
      )}

      {candidatesQuery.isLoading && jobId && (
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      )}

      {rowsList.some((row) => row.stage === 'done') && (
        <div className="ttc-results-foot">
          <CheckCircle2 size={15} />
          已完成 {rowsList.filter((row) => row.stage === 'done').length} 人；
          <XCircle size={15} />
          失败 {rowsList.filter((row) => row.stage === 'error').length} 人。
        </div>
      )}
    </div>
  )
}
