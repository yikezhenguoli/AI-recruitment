import { useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Bot,
  Mic,
  PlayCircle,
  RefreshCw,
  UserRound,
} from 'lucide-react'
import { runViewTransition } from '../components/layout/PageTransition'
import { listCandidates } from '../api/candidates'
import { listJobs } from '../api/jobs'
import { createVoiceSession, listVoiceSessions } from '../api/voice'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime, VOICE_STATUS_CLASS, VOICE_STATUS_LABELS } from '../lib/format'
import type { VoiceSessionStatus, VoiceSessionSummary } from '../types'

function StatusBadge({ status }: { status: VoiceSessionStatus }) {
  return (
    <span className={`ttc-badge ${VOICE_STATUS_CLASS[status] ?? 'ttc-badge-blue'}`}>
      {VOICE_STATUS_LABELS[status] ?? status}
    </span>
  )
}

export default function SessionsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const tableRef = useRef<HTMLDivElement>(null)
  const [filter, setFilter] = useState<'all' | VoiceSessionStatus>('all')
  const [candidateId, setCandidateId] = useState('')
  const [jobId, setJobId] = useState('')
  const [maxSeconds, setMaxSeconds] = useState(900)
  const [customQuestions, setCustomQuestions] = useState('')
  const [launchError, setLaunchError] = useState('')

  const sessionsQuery = useQuery({
    queryKey: ['voiceSessions', filter],
    queryFn: () =>
      listVoiceSessions(filter === 'all' ? {} : { status: filter, limit: 50 }),
    refetchInterval: 15_000,
  })
  const candidatesQuery = useQuery({ queryKey: ['candidates'], queryFn: () => listCandidates() })
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs() })

  const candidates = candidatesQuery.data ?? []
  const jobs = jobsQuery.data ?? []
  const sessions = sessionsQuery.data ?? []

  const selectedCandidate = useMemo(
    () => candidates.find((item) => item.id === candidateId),
    [candidates, candidateId],
  )

  // 候选人有绑定岗位时自动带出，但仍允许改成其他已发布岗位。
  const effectiveJobId = jobId || selectedCandidate?.job_id || ''
  const parsedCustomQuestions = customQuestions
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)

  const launch = useMutation({
    mutationFn: async () => {
      if (!candidateId) throw new Error('请选择候选人')
      if (!effectiveJobId) throw new Error('请选择岗位')
      if (parsedCustomQuestions.length > 5) throw new Error('HR 自定义问题最多 5 个')
      if (parsedCustomQuestions.some((item) => item.length > 200)) {
        throw new Error('每个 HR 自定义问题不能超过 200 个字符')
      }
      return createVoiceSession({
        candidate_id: candidateId,
        job_id: effectiveJobId,
        scenario: 'screen',
        max_seconds: maxSeconds,
        custom_questions: parsedCustomQuestions,
      })
    },
    onSuccess: (result) => {
      setLaunchError('')
      void queryClient.invalidateQueries({ queryKey: ['voiceSessions'] })
      navigate(`/sessions/${result.id}`)
    },
    onError: (error) => {
      setLaunchError(
        getApiErrorMessage(
          error,
          '无法创建语音会话：候选人必须已授予语音面试授权，且简历解析完成。',
        ),
      )
    },
  })

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            VOICE INTERVIEW
            <span className="hero-eyebrow-line" />
            <span>REALTIME TRANSCRIPT</span>
          </div>
          <h1>语音会话</h1>
          <p>
            AI 面试官通过通义千问实时语音提问，候选人回答实时转写。音频不落盘，会话结束即生成基于转写的报告。
          </p>
        </div>
        <div className="ttc-heading-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => void sessionsQuery.refetch()}
          >
            <RefreshCw size={15} className={sessionsQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </section>

      <section className="ttc-card ttc-launch-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">发起语音面试</h2>
            <p className="ttc-card-sub">
              会话创建即绑定候选人、岗位与授权记录。候选人接通后 HR 才能旁听；企业端不会由 HR 代替候选人接入 AI。
            </p>
          </div>
          <Mic size={18} className="ttc-accent-icon" />
        </div>

        <div className="ttc-launch-form">
          <label className="ttc-login-field">
            <span>候选人</span>
            <select
              value={candidateId}
              onChange={(event) => {
                setCandidateId(event.target.value)
                setJobId('')
              }}
            >
              <option value="">请选择候选人</option>
              {candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.display_name}
                  {candidate.is_synthetic ? '（合成样本）' : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="ttc-login-field">
            <span>岗位</span>
            <select value={effectiveJobId} onChange={(event) => setJobId(event.target.value)}>
              <option value="">请选择岗位</option>
              {jobs
                .filter((job) => job.status === 'published' || job.status === 'draft')
                .map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}（{job.status === 'published' ? '已发布' : '草稿'}）
                  </option>
                ))}
            </select>
          </label>

          <label className="ttc-login-field">
            <span>最长时长</span>
            <select
              value={maxSeconds}
              onChange={(event) => setMaxSeconds(Number(event.target.value))}
            >
              <option value={300}>5 分钟</option>
              <option value={900}>15 分钟</option>
              <option value={1200}>20 分钟</option>
              <option value={1800}>30 分钟</option>
            </select>
          </label>

          <label className="ttc-login-field ttc-custom-questions-field">
            <span>HR 指定问题（选填，每行一个，最多 5 个）</span>
            <textarea
              value={customQuestions}
              maxLength={1200}
              rows={3}
              placeholder={'例如：请说明你如何评估一次线上故障的影响范围？\n请介绍上一份工作中最有代表性的交付结果。'}
              onChange={(event) => setCustomQuestions(event.target.value)}
            />
            <small>
              HR 指定问题会置于 AI 问题之前并要求优先覆盖；为空时完全由 AI 根据简历和 JD 生成。
            </small>
          </label>

          <button
            type="button"
            className="ttc-btn ttc-btn-primary ttc-launch-submit"
            disabled={
              launch.isPending ||
              !candidateId ||
              parsedCustomQuestions.length > 5 ||
              parsedCustomQuestions.some((item) => item.length > 200)
            }
            onClick={() => launch.mutate()}
          >
            <PlayCircle size={16} />
            {launch.isPending ? '创建中…' : '创建面试会话'}
          </button>
        </div>

        {launchError && (
          <div className="ttc-inline-error">
            <AlertCircle size={16} />
            <span>{launchError}</span>
          </div>
        )}
      </section>

      <search className="ttc-filter-chips" aria-label="按语音会话状态筛选">
        {(
          [
            ['all', '全部'],
            ['created', '待接通'],
            ['live', '进行中'],
            ['ended', '已结束'],
            ['revoked', '授权撤回'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`ttc-chip ${filter === value ? 'ttc-chip-blue' : ''}`}
            onClick={() => runViewTransition(() => setFilter(value), tableRef.current)}
          >
            {label}
          </button>
        ))}
      </search>

      {sessionsQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取语音会话</strong>
            <span>{getApiErrorMessage(sessionsQuery.error)}</span>
          </div>
        </div>
      )}

      {sessionsQuery.isLoading && <div className="ttc-card ttc-skeleton-card" />}

      {!sessionsQuery.isLoading && !sessionsQuery.isError && sessions.length === 0 && (
        <div className="ttc-card ttc-empty-large">
          <Bot size={30} />
          <h2>还没有语音会话</h2>
          <p>选择一位已授权的候选人发起面试，AI 面试官会从岗位初始问题开场并根据回答动态追问。</p>
        </div>
      )}

      {sessions.length > 0 && (
        <div ref={tableRef} className="ttc-table-card">
          <div className="ttc-table-scroll ttc-table-container" tabIndex={0} role="region" aria-label="语音面试会话列表">
            <table className="ttc-result-table">
              <thead>
                <tr>
                  <th>候选人</th>
                  <th>岗位</th>
                  <th>状态</th>
                  <th>模型</th>
                  <th>能力评分</th>
                  <th>言行审核</th>
                  <th>创建时间</th>
                  <th>报告</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((session: VoiceSessionSummary) => (
                  <tr key={session.id}>
                    <td data-label="候选人">
                      <span className="ttc-result-person">
                        <UserRound size={15} />
                        {session.candidate_name}
                      </span>
                    </td>
                    <td data-label="岗位">{session.job_title ?? '—'}</td>
                    <td data-label="状态">
                      <StatusBadge status={session.status} />
                    </td>
                    <td data-label="模型" className="ttc-muted">{session.model}</td>
                    <td data-label="能力评分">
                      {typeof session.capability_score === 'number' ? (
                        <span
                          className={`ttc-badge ${
                            session.capability_score >= 80
                              ? 'ttc-badge-green'
                              : session.capability_score >= 60
                                ? 'ttc-badge-amber'
                                : 'ttc-badge-red'
                          }`}
                        >
                          {session.capability_score.toFixed(1)} / 100
                        </span>
                      ) : session.capability_status === 'unassessed' ? (
                        <span className="ttc-badge ttc-badge-amber">证据不足</span>
                      ) : (
                        <span className="ttc-muted">—</span>
                      )}
                    </td>
                    <td data-label="言行审核">
                      {session.conduct_veto ? (
                        <span className="ttc-badge ttc-badge-red">一票否决</span>
                      ) : typeof session.conduct_score === 'number' ? (
                        <span
                          className={`ttc-badge ${
                            session.conduct_score >= 80 ? 'ttc-badge-green' : 'ttc-badge-amber'
                          }`}
                        >
                          {session.conduct_score.toFixed(1)} / 100
                        </span>
                      ) : session.conduct_status === 'unassessed' ? (
                        <span className="ttc-badge ttc-badge-amber">待复核</span>
                      ) : (
                        <span className="ttc-muted">—</span>
                      )}
                    </td>
                    <td data-label="创建时间" className="ttc-muted">{formatDateTime(session.created_at)}</td>
                    <td data-label="报告">{session.has_report ? '已生成' : '—'}</td>
                    <td data-label="操作" className="ttc-col-action">
                      <Link className="ttc-text-link" to={`/sessions/${session.id}`}>
                        进入
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
