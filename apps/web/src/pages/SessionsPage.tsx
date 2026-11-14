import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import {
  AlertTriangle,
  AudioLines,
  Bot,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  Mic,
  Phone,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserRound,
  Waves,
} from 'lucide-react'
import { listJobs } from '../api/jobs'
import { listCandidates } from '../api/candidates'
import {
  createVoiceSession,
  getVoiceReport,
  getVoiceSession,
} from '../api/voice'
import { VoiceCallPanel } from '../components/voice/VoiceCallPanel'
import { useAuthStore } from '../store/authStore'
import type {
  CallReport,
  CreateVoiceSessionResult,
  VoicePlan,
  VoiceScenario,
} from '../types'
import { VOICE_STATUS_LABEL } from '../types'

const SCENARIOS: Array<{ value: VoiceScenario; label: string; hint: string }> = [
  { value: 'screen', label: '初筛沟通', hint: '按固定问题了解经历与求职意向' },
  { value: 'verify', label: '经历核验', hint: '围绕简历陈述逐项确认' },
  { value: 'skill', label: '技能面', hint: '聚焦岗位相关技能与项目' },
  { value: 'mock', label: '模拟面试', hint: '用于演练，不产出录用结论' },
]

const DURATIONS = [
  { value: 300, label: '5 分钟' },
  { value: 600, label: '10 分钟' },
  { value: 1200, label: '20 分钟' },
  { value: 1800, label: '30 分钟' },
]

interface RecentSession {
  id: string
  candidateName: string
  jobTitle: string
  createdAt: string
}

const RECENT_KEY = 'ttc-voice-sessions-v1'

function loadRecent(): RecentSession[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item): item is RecentSession => {
        const record = item as Record<string, unknown>
        return typeof record?.id === 'string'
      })
      .slice(0, 8)
  } catch {
    return []
  }
}

function saveRecent(list: RecentSession[]): void {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 8)))
  } catch {
    // localStorage 不可用时不影响主流程
  }
}

function readableError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined
    const message = data?.message
    if (typeof message === 'string' && message.trim()) return message
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (error.code === 'ECONNABORTED') return '请求超时，请检查后端与实时语音服务状态。'
    if (!error.response) return '无法连接后端，请确认 apps/api 已启动且 Vite 代理可用。'
    return `请求失败（HTTP ${error.response.status}）。`
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试。'
}

function normalizePlan(value: unknown): VoicePlan | null {
  let candidate: unknown = value
  if (typeof candidate === 'string') {
    try {
      candidate = JSON.parse(candidate)
    } catch {
      return null
    }
  }
  if (!candidate || typeof candidate !== 'object') return null
  const record = candidate as Record<string, unknown>
  if (!Array.isArray(record.questions)) return null
  return record as unknown as VoicePlan
}

function planOf(
  result: CreateVoiceSessionResult | null,
  sessionPlan?: VoicePlan | string,
): VoicePlan | null {
  return normalizePlan(result?.plan) ?? normalizePlan(sessionPlan)
}

export default function SessionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const user = useAuthStore((state) => state.user)

  const [selectedJobId, setSelectedJobId] = useState(searchParams.get('job') ?? '')
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [scenario, setScenario] = useState<VoiceScenario>('screen')
  const [maxSeconds, setMaxSeconds] = useState(600)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [created, setCreated] = useState<CreateVoiceSessionResult | null>(null)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    searchParams.get('session'),
  )
  const [recent, setRecent] = useState<RecentSession[]>(() => loadRecent())
  const [latestReport, setLatestReport] = useState<CallReport | null>(null)

  const jobsQuery = useQuery({ queryKey: ['jobs', 'voice'], queryFn: () => listJobs({ limit: 100 }) })
  const candidatesQuery = useQuery({
    queryKey: ['candidates', 'voice'],
    queryFn: () => listCandidates({ limit: 100 }),
  })

  const jobs = jobsQuery.data ?? []
  const allCandidates = candidatesQuery.data ?? []

  const candidates = useMemo(() => {
    if (!selectedJobId) return allCandidates
    return allCandidates.filter(
      (candidate) => !candidate.job_id || candidate.job_id === selectedJobId,
    )
  }, [allCandidates, selectedJobId])

  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? null
  const selectedCandidate =
    allCandidates.find((candidate) => candidate.id === selectedCandidateId) ?? null

  const sessionQuery = useQuery({
    queryKey: ['voiceSession', activeSessionId],
    queryFn: () => getVoiceSession(activeSessionId as string),
    enabled: Boolean(activeSessionId),
    retry: 1,
  })

  const sessionStatus = sessionQuery.data?.status
  const reportQuery = useQuery({
    queryKey: ['voiceReport', activeSessionId, sessionStatus],
    queryFn: () => getVoiceReport(activeSessionId as string),
    enabled:
      Boolean(activeSessionId) &&
      (sessionStatus === 'ended' ||
        sessionStatus === 'failed' ||
        sessionStatus === 'revoked'),
    retry: false,
  })

  useEffect(() => {
    if (selectedCandidateId && !candidates.some((item) => item.id === selectedCandidateId)) {
      setSelectedCandidateId('')
    }
  }, [candidates, selectedCandidateId])

  useEffect(() => {
    const target = activeSessionId ?? ''
    const current = searchParams.get('session') ?? ''
    if (target === current) return
    const next = new URLSearchParams(searchParams)
    if (target) next.set('session', target)
    else next.delete('session')
    setSearchParams(next, { replace: true })
  }, [activeSessionId, searchParams, setSearchParams])

  const chooseJob = (jobId: string) => {
    setSelectedJobId(jobId)
    const next = new URLSearchParams(searchParams)
    if (jobId) next.set('job', jobId)
    else next.delete('job')
    setSearchParams(next, { replace: true })
  }

  const rememberSession = (sessionId: string) => {
    if (!selectedCandidate || !selectedJob) return
    const entry: RecentSession = {
      id: sessionId,
      candidateName: selectedCandidate.display_name,
      jobTitle: selectedJob.title,
      createdAt: new Date().toISOString(),
    }
    const next = [entry, ...recent.filter((item) => item.id !== sessionId)].slice(0, 8)
    setRecent(next)
    saveRecent(next)
  }

  const handleCreate = async () => {
    if (!selectedJobId || !selectedCandidateId) {
      setCreateError('请先选择岗位和候选人。')
      return
    }
    setCreating(true)
    setCreateError(null)
    setLatestReport(null)
    try {
      const result = await createVoiceSession({
        candidate_id: selectedCandidateId,
        job_id: selectedJobId,
        scenario,
        provider: 'qwen_realtime',
        max_seconds: maxSeconds,
      })
      setCreated(result)
      setActiveSessionId(result.id)
      rememberSession(result.id)
    } catch (error) {
      setCreateError(readableError(error))
    } finally {
      setCreating(false)
    }
  }

  const openRecent = (item: RecentSession) => {
    setActiveSessionId(item.id)
    setCreated(null)
    setLatestReport(null)
  }

  const activeSession = sessionQuery.data ?? null
  const activePlan = planOf(created, activeSession?.plan_json)
  const canUseVoice = user?.role === 'hr' || user?.role === 'admin'
  const createBlockReason = !canUseVoice
    ? `当前账号是「${user?.role ?? '未登录'}」，创建会话需要 HR 或管理员账号。`
    : jobsQuery.isLoading || candidatesQuery.isLoading
      ? '正在加载岗位与候选人…'
      : jobsQuery.isError || candidatesQuery.isError
        ? '岗位或候选人在线数据加载失败，请确认后端 8001 与 Vite 代理可用。'
        : jobs.length === 0
          ? '还没有岗位，请先到「岗位管理」创建岗位。'
          : allCandidates.length === 0
            ? '还没有候选人，请先到「候选人」创建候选人并上传简历。'
            : !selectedJobId
              ? '请先选择岗位。'
              : !selectedCandidateId
                ? '请先选择候选人。'
                : null

  // 本地联调快捷选择：优先选中 E2E 演示岗位/演示候选人，省去手动查找。
  // 生产构建不会自动替用户做选择。
  useEffect(() => {
    if (!import.meta.env.DEV) return
    if (!selectedJobId && jobs.length > 0) {
      const preferred =
        jobs.find((job) => job.title.includes('E2E')) ?? jobs[0]
      chooseJob(preferred.id)
    }
    if (!selectedCandidateId && allCandidates.length > 0) {
      const preferred =
        allCandidates.find((item) => item.display_name === '演示候选人') ??
        allCandidates[0]
      setSelectedCandidateId(preferred.id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs, allCandidates])

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            VOICE SESSION
            <span className="hero-eyebrow-line" />
            <span>QWEN REALTIME RELAY</span>
          </div>
          <h1>语音会话</h1>
          <p>
            选择岗位与候选人创建真实语音会话：浏览器麦克风经 TTC 后端 WebSocket 中转连接通义千问
            Realtime，AI 会实时用语音提问与回应，并产出文字转写报告。
          </p>
        </div>
        <div className="ttc-heading-actions">
          <span className="ttc-status ttc-status-ok">
            <i />
            真实链路 · Qwen Realtime
          </span>
        </div>
      </section>

      {!canUseVoice && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertTriangle size={16} />
          <span>
            当前账号角色为「{user?.role ?? '未登录'}」。创建语音会话需要 HR 或管理员账号；
            候选人只能在获得会话后加入。
          </span>
        </div>
      )}

      <section className="ttc-voice-stats" aria-label="语音会话状态">
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon">
            <Mic size={17} />
          </span>
          <div>
            <span>采集与播放</span>
            <strong>浏览器 PCM · 实时</strong>
          </div>
        </article>
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon ttc-voice-stat-icon-blue">
            <Waves size={17} />
          </span>
          <div>
            <span>语音上游</span>
            <strong>DashScope Qwen</strong>
          </div>
        </article>
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon ttc-voice-stat-icon-amber">
            <ShieldCheck size={17} />
          </span>
          <div>
            <span>授权前置</span>
            <strong>需 voice_interview</strong>
          </div>
        </article>
      </section>

      <section className="ttc-card ttc-card-pad mt-6">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">创建语音会话</h2>
            <p className="ttc-card-sub">
              候选人必须已解析出一份简历，并持有有效的 voice_interview 授权；否则后端会返回真实原因。
            </p>
          </div>
          <span className="ttc-job-icon">
            <Phone size={18} />
          </span>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>岗位</span>
            <select
              className="w-full rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              value={selectedJobId}
              onChange={(event) => chooseJob(event.target.value)}
              disabled={creating || jobsQuery.isLoading}
            >
              <option value="">请选择岗位</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                  {job.department ? ` · ${job.department}` : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>候选人</span>
            <select
              className="w-full rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              value={selectedCandidateId}
              onChange={(event) => setSelectedCandidateId(event.target.value)}
              disabled={creating || candidatesQuery.isLoading}
            >
              <option value="">请选择候选人</option>
              {candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.display_name}
                  {candidate.job_id ? '' : ' · 未绑定岗位'}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>场景</span>
            <select
              className="w-full rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              value={scenario}
              onChange={(event) => setScenario(event.target.value as VoiceScenario)}
              disabled={creating}
            >
              {SCENARIOS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>最长时长</span>
            <select
              className="w-full rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              value={maxSeconds}
              onChange={(event) => setMaxSeconds(Number(event.target.value))}
              disabled={creating}
            >
              {DURATIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="ttc-muted">
            {SCENARIOS.find((item) => item.value === scenario)?.hint}
            {selectedCandidate ? ` · 候选人为「${selectedCandidate.display_name}」` : ''}
          </span>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            onClick={() => void handleCreate()}
            disabled={Boolean(createBlockReason) || creating}
            title={createBlockReason ?? '创建后点击「开始通话」即可与 AI 实时对话'}
          >
            {creating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {creating ? '正在创建…' : '创建语音会话'}
          </button>
        </div>

        {createBlockReason && (
          <div className="ttc-inline-error" role="status" style={{ marginTop: 12 }}>
            <AlertTriangle size={15} />
            <div>
              <strong>暂时不能创建会话</strong>
              <span>{createBlockReason}</span>
              {jobsQuery.isError || candidatesQuery.isError ? (
                <span>
                  请确认当前打开的是重启后的前端（推荐 http://127.0.0.1:5175），
                  且 Vite 的 /api 代理指向 127.0.0.1:8001。
                </span>
              ) : null}
            </div>
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => {
                void jobsQuery.refetch()
                void candidatesQuery.refetch()
              }}
            >
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        )}

        {createError && (
          <div className="ttc-inline-error" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>创建失败</strong>
              <span>{createError}</span>
              <span>
                如果提示缺少授权，请由候选人账号（例如演示账号 candidate@ttc.local）先调用
                「授权 voice_interview」；HR 不能替候选人授权。
              </span>
            </div>
          </div>
        )}

        {(jobsQuery.isError || candidatesQuery.isError) && (
          <div className="ttc-inline-error" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>无法读取岗位或候选人</strong>
              <span>
                {readableError(jobsQuery.error ?? candidatesQuery.error)}
              </span>
            </div>
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => {
                void jobsQuery.refetch()
                void candidatesQuery.refetch()
              }}
            >
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        )}
      </section>

      {activeSessionId && (
        <section className="ttc-card ttc-card-pad mt-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="ttc-mini-heading">
              <CalendarClock size={14} />
              SESSION {activeSessionId.slice(0, 8)}
            </div>
            <h2>
              {selectedCandidate?.display_name ||
                recent.find((item) => item.id === activeSessionId)?.candidateName ||
                '语音会话'}
              <span className="ttc-muted">
                {' '}
                · {selectedJob?.title || recent.find((item) => item.id === activeSessionId)?.jobTitle}
              </span>
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`ttc-voice-badge ttc-voice-badge-${
                activeSession?.status === 'live'
                  ? 'ok'
                  : activeSession?.status === 'failed' || activeSession?.status === 'revoked'
                    ? 'danger'
                    : 'muted'
              }`}
            >
              {activeSession ? VOICE_STATUS_LABEL[activeSession.status] : '读取中'}
            </span>
            {activePlan && (
              <span className="ttc-voice-badge ttc-voice-badge-muted">
                {activePlan.questions.length} 个预设问题
              </span>
            )}
          </div>
        </section>
      )}

      {activeSessionId && activePlan && (
        <section className="ttc-card ttc-card-pad mt-4">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">本次面试计划</h2>
              <p className="ttc-card-sub">
                后端已把以下问题写入会话 instructions；AI 会按顺序用语音提问。
              </p>
            </div>
            <Bot size={18} className="ttc-accent-icon" />
          </div>
          <ol className="ttc-plain-list">
            {activePlan.questions.map((question, index) => (
              <li key={question.id}>
                <strong>{String(index + 1).padStart(2, '0')}</strong> {question.text}
              </li>
            ))}
          </ol>
        </section>
      )}

      {activeSessionId && (
        <VoiceCallPanel
          key={activeSessionId}
          sessionId={activeSessionId}
          maxSeconds={activeSession?.max_seconds ?? maxSeconds}
          initialStatus={activeSession?.status}
          initialReport={reportQuery.data ?? null}
          onReport={(report) => setLatestReport(report)}
        />
      )}

      {!activeSessionId && (
        <section className="ttc-card ttc-card-pad mt-4">
          <div className="ttc-voice-transcript-empty">
            <span className="ttc-voice-transcript-icon">
              <AudioLines size={20} />
            </span>
            <strong>选择岗位和候选人后创建会话</strong>
            <p>
              创建成功后点击「开始通话」才会请求麦克风。浏览器会实时上传 PCM 音频到后端中转，
              并播放 Qwen 返回的语音；页面不会使用模拟音频或伪造转写。
            </p>
          </div>
        </section>
      )}

      {latestReport && (
        <section className="ttc-notice">
          <CheckCircle2 size={16} />
          <span>
            最新报告已生成：{latestReport.quotes.length} 条候选人原话，
            {latestReport.status === 'ready' ? '可用于后续人工复核。' : '请查看报告状态。'}
          </span>
        </section>
      )}

      <section className="ttc-card ttc-card-pad mt-6">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">本机最近创建的会话</h2>
            <p className="ttc-card-sub">
              后端暂未提供「会话列表」接口，这里只保存本浏览器创建过的会话 ID，可重新打开查看状态与报告。
            </p>
          </div>
          <Clock size={18} className="ttc-accent-icon" />
        </div>

        {recent.length === 0 ? (
          <div className="ttc-empty-state ttc-empty-compact">
            <AudioLines size={20} />
            <strong>还没有会话记录</strong>
            <span>创建一次语音会话后会出现在这里。</span>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {recent.map((item) => (
              <button
                type="button"
                className={`flex w-full flex-wrap items-center justify-between gap-3 py-3 text-left text-sm transition-colors hover:bg-sky-50/60 ${
                  item.id === activeSessionId ? 'bg-sky-50/70' : ''
                }`}
                key={item.id}
                onClick={() => openRecent(item)}
              >
                <span className="flex items-center gap-2">
                  <UserRound size={15} />
                  <span>
                    <strong className="block text-slate-700">{item.candidateName}</strong>
                    <small className="block text-xs text-slate-400">{item.jobTitle}</small>
                  </span>
                </span>
                <span className="ttc-muted">{item.id.slice(0, 8)}</span>
                <span className="ttc-muted">
                  {new Date(item.createdAt).toLocaleString('zh-CN')}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
