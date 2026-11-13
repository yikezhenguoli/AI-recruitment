import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowRight,
  Briefcase,
  FileText,
  Plus,
  RefreshCw,
  Users,
} from 'lucide-react'
import { ResumeUpload } from '../components/ResumeUpload'
import { ProcessingPanel } from '../components/candidates/ProcessingPanel'
import { CandidateResults } from '../components/candidates/CandidateResults'
import { getSessionResults } from '../api/candidates'
import { getSavedJob, listSavedJobs } from '../api/jobs'
import { closeResumeSession } from '../api/resumes'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useSessionStore } from '../store/sessionStore'
import type {
  GraduationYearFilterConfig,
  SessionResultsResponse,
} from '../types'

const DEFAULT_GRADUATION_FILTER: GraduationYearFilterConfig = {
  enabled: false,
  accepted_years: [],
  unknown_year_behavior: 'manual_review',
  degree_selection: 'highest_relevant_degree',
}

type PageStage = 'select' | 'upload' | 'processing' | 'results'

export default function CandidatesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const session = useSessionStore((state) => state.session)
  const setSession = useSessionStore((state) => state.setSession)
  const clearSession = useSessionStore((state) => state.clearSession)

  const queryJob = searchParams.get('job') || ''
  const [selectedJobName, setSelectedJobName] = useState(queryJob || session?.jobName || '')
  const [stage, setStage] = useState<PageStage>(session ? 'processing' : queryJob ? 'upload' : 'select')
  const [results, setResults] = useState<SessionResultsResponse | null>(null)
  const [initializing, setInitializing] = useState(Boolean(session))
  const [pageError, setPageError] = useState<string | null>(null)
  const sessionStartedHereRef = useRef(false)

  const jobsQuery = useQuery({
    queryKey: ['savedJobs'],
    queryFn: listSavedJobs,
  })

  const jobQuery = useQuery({
    queryKey: ['savedJob', selectedJobName],
    queryFn: () => getSavedJob(selectedJobName),
    enabled: Boolean(selectedJobName),
  })

  useEffect(() => {
    if (!session) {
      setInitializing(false)
      setResults(null)
      if (stage === 'processing' || stage === 'results') {
        setStage(selectedJobName ? 'upload' : 'select')
      }
      return
    }

    // A session created by this page's upload action is already owned by the
    // mounted ProcessingPanel; do not unmount it for an immediate result fetch.
    if (sessionStartedHereRef.current) {
      sessionStartedHereRef.current = false
      setInitializing(false)
      return
    }

    let cancelled = false
    setInitializing(true)
    setPageError(null)

    getSessionResults(session.sessionId)
      .then((response) => {
        if (cancelled) return
        setResults(response)
        setStage(response.status === 'done' && response.results.length > 0 ? 'results' : 'processing')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        clearSession()
        setResults(null)
        setSelectedJobName((current) => current || '')
        setStage(selectedJobName ? 'upload' : 'select')
        setPageError(
          `上一次筛选会话已失效，请重新上传简历。${getApiErrorMessage(error, '')}`,
        )
      })
      .finally(() => {
        if (!cancelled) setInitializing(false)
      })

    return () => {
      cancelled = true
    }
    // The effect intentionally runs only when the persisted session changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.sessionId])

  const roleTitle =
    jobQuery.data?.structured.role_title ||
    session?.jobRoleTitle ||
    '未选择岗位'

  const selectJob = async (name: string) => {
    if (session) {
      try {
        await closeResumeSession(session.sessionId)
      } catch {
        // A stale session can already be gone; local reset is enough.
      }
      clearSession()
    }
    setSelectedJobName(name)
    setSearchParams({ job: name })
    setStage('upload')
    setResults(null)
    setPageError(null)
  }

  const handleProcessingStarted = (sessionId: string, totalFiles: number) => {
    const job = jobQuery.data
    sessionStartedHereRef.current = true
    setSession({
      sessionId,
      jobName: job?.name || selectedJobName,
      jobRoleTitle: job?.structured.role_title,
      totalFiles,
      startedAt: new Date().toISOString(),
    })
    setStage('processing')
    setPageError(null)
  }

  const handleComplete = (finalResults: SessionResultsResponse) => {
    setResults(finalResults)
    setStage('results')
  }

  const handleNewBatch = async () => {
    if (session) {
      try {
        await closeResumeSession(session.sessionId)
      } catch {
        // ignore stale sessions
      }
    }
    clearSession()
    setResults(null)
    setStage(selectedJobName ? 'upload' : 'select')
    setPageError(null)
  }

  const handleChangeJob = async () => {
    if (session) {
      try {
        await closeResumeSession(session.sessionId)
      } catch {
        // ignore stale sessions
      }
      clearSession()
    }
    setSelectedJobName('')
    setResults(null)
    setStage('select')
    setSearchParams({})
    setPageError(null)
  }

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            CANDIDATE PIPELINE
            <span className="hero-eyebrow-line" />
            <span>AI SCREENING</span>
          </div>
          <h1>候选人筛选</h1>
          <p>选择岗位、批量上传简历，实时查看 DeepSeek 解析与评分进度，并查看真实排名。</p>
        </div>
        <div className="ttc-heading-actions">
          {stage !== 'select' && (
            <button type="button" className="ttc-btn ttc-btn-secondary" onClick={() => void handleChangeJob()}>
              <RefreshCw size={15} />
              更换岗位
            </button>
          )}
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <Briefcase size={15} />
            岗位管理
          </Link>
        </div>
      </section>

      {pageError && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertCircle size={15} />
          <span>{pageError}</span>
        </div>
      )}

      {initializing && (
        <div className="ttc-card ttc-card-pad ttc-skeleton-block">
          <span className="ttc-muted">正在恢复上一次筛选会话…</span>
        </div>
      )}

      {!initializing && stage === 'select' && (
        <section className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">选择招聘岗位</h2>
              <p className="ttc-card-sub">从已保存岗位中选择一个，使用其 JD 与评分维度进行筛选</p>
            </div>
            <Link to="/jobs/new" className="ttc-btn ttc-btn-primary ttc-btn-sm">
              <Plus size={14} />
              新建岗位
            </Link>
          </div>

          {jobsQuery.isLoading && (
            <div className="ttc-job-grid ttc-job-grid-compact">
              <div className="ttc-skeleton-card" />
              <div className="ttc-skeleton-card" />
            </div>
          )}

          {jobsQuery.isError && (
            <div className="ttc-inline-error">
              <AlertCircle size={16} />
              <div>
                <strong>无法读取岗位列表</strong>
                <span>{getApiErrorMessage(jobsQuery.error, '请确认后端服务已启动。')}</span>
              </div>
            </div>
          )}

          {!jobsQuery.isLoading && !jobsQuery.isError && (jobsQuery.data ?? []).length === 0 && (
            <div className="ttc-empty-state">
              <Briefcase size={24} />
              <strong>还没有可用的岗位</strong>
              <span>请先创建岗位并完成 JD 解析，再开始候选人筛选。</span>
              <Link to="/jobs/new" className="ttc-btn ttc-btn-primary ttc-btn-sm">
                <Plus size={14} />
                创建岗位
              </Link>
            </div>
          )}

          {!jobsQuery.isLoading && !jobsQuery.isError && (jobsQuery.data ?? []).length > 0 && (
            <div className="ttc-job-grid ttc-job-grid-compact">
              {(jobsQuery.data ?? []).map((job) => (
                <article key={job.name} className="ttc-job-card ttc-job-pick-card">
                  <div className="ttc-job-card-top">
                    <span className="ttc-job-icon">
                      <Briefcase size={18} />
                    </span>
                    <span className="ttc-badge ttc-badge-blue">已保存</span>
                  </div>
                  <h3>{job.role_title}</h3>
                  <p>{job.name}</p>
                  <div className="ttc-job-card-foot">
                    <span>更新于 {formatDateTime(job.updated_at)}</span>
                    <button
                      type="button"
                      className="ttc-text-link"
                      onClick={() => void selectJob(job.name)}
                    >
                      选择此岗位 <ArrowRight size={13} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {!initializing && stage === 'upload' && selectedJobName && (
        <>
          {jobQuery.isLoading && (
            <div className="ttc-card ttc-card-pad ttc-skeleton-block">
              <span className="ttc-muted">正在加载岗位信息…</span>
            </div>
          )}

          {jobQuery.isError && (
            <div className="ttc-error-panel">
              <AlertCircle size={18} />
              <div>
                <strong>岗位信息读取失败</strong>
                <span>{getApiErrorMessage(jobQuery.error, '该岗位可能已被删除。')}</span>
              </div>
              <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm" onClick={() => void handleChangeJob()}>
                重新选择
              </button>
            </div>
          )}

          {jobQuery.data && (
            <>
              <div className="ttc-selected-job">
                <div>
                  <span className="ttc-mini-heading">
                    <Briefcase size={14} />
                    当前岗位
                  </span>
                  <strong>{jobQuery.data.structured.role_title}</strong>
                  <span>{jobQuery.data.name}</span>
                </div>
                <Link
                  to={`/jobs/${encodeURIComponent(jobQuery.data.name)}`}
                  className="ttc-text-link"
                >
                  查看岗位详情 <ArrowRight size={13} />
                </Link>
              </div>

              <ResumeUpload
                jdText={jobQuery.data.jd_text}
                jdStructured={jobQuery.data.structured}
                scoringSchema={jobQuery.data.scoring_schema}
                graduationFilter={DEFAULT_GRADUATION_FILTER}
                onProcessingStarted={handleProcessingStarted}
              />
            </>
          )}
        </>
      )}

      {!initializing && stage === 'processing' && session && (
        <ProcessingPanel
          sessionId={session.sessionId}
          totalFiles={session.totalFiles}
          jobRoleTitle={roleTitle}
          onComplete={handleComplete}
        />
      )}

      {!initializing && stage === 'results' && session && results && (
        <CandidateResults
          sessionId={session.sessionId}
          results={results}
          jobRoleTitle={roleTitle}
          scoringSchema={jobQuery.data?.scoring_schema}
          onNewBatch={() => void handleNewBatch()}
        />
      )}

      {!initializing && stage === 'results' && (!session || !results) && (
        <section className="ttc-card ttc-card-pad ttc-empty-large">
          <Users size={30} />
          <h2>没有可展示的候选人结果</h2>
          <p>当前会话没有返回结果，请重新开始一轮筛选。</p>
          <Link to="/candidates" className="ttc-btn ttc-btn-primary">
            重新选择岗位
          </Link>
        </section>
      )}

      <div className="ttc-notice">
        <FileText size={15} />
        <span>
          当前候选人流程使用真实后端接口 <code>/api/resumes/process</code>、<code>/ws/:session_id</code>、
          <code>/api/resumes/results</code> 与 <code>/api/resumes/detail</code>；不使用前端模拟进度或伪造评分。
        </span>
      </div>
    </div>
  )
}
