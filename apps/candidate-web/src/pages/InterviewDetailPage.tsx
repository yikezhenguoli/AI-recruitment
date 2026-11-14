import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  ClipboardList,
  Info,
  Loader2,
  Mic,
  PhoneCall,
  PhoneOff,
  ShieldCheck,
} from 'lucide-react'
import { getInterview, getProfile } from '../api/portal'
import type { InterviewDetail } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { END_REASON, INTERVIEW_STATUS } from '../lib/labels'
import { connectInterview, type LiveSession, type LiveState } from '../lib/realtime'
import { RelayInterview, type RelayInfo, type RelayLine } from '../lib/relay'
import { Badge, ErrorNote, LoadingBlock, PageHeader } from '../components/ui'
import { SoundWave } from '../components/visual/SoundWave'

function formatClock(seconds: number): string {
  const minute = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${String(minute).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

export default function InterviewDetailPage() {
  const { id = '' } = useParams()
  const [detail, setDetail] = useState<InterviewDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hasVoiceConsent, setHasVoiceConsent] = useState<boolean | null>(null)
  const [liveState, setLiveState] = useState<LiveState>('idle')
  const [liveError, setLiveError] = useState<string | null>(null)
  const [terminationMessage, setTerminationMessage] = useState<string | null>(null)
  const [interviewPaused, setInterviewPaused] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [lines, setLines] = useState<RelayLine[]>([])
  const [relayInfo, setRelayInfo] = useState<RelayInfo | null>(null)
  const [muted, setMuted] = useState(false)
  const sessionRef = useRef<LiveSession | null>(null)
  const relayRef = useRef<RelayInterview | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const getLevel = useCallback(() => relayRef.current?.getLevel() ?? 0, [])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([getInterview(id), getProfile()])
      .then(([interviewResult, profileResult]) => {
        if (cancelled) return
        if (interviewResult.status === 'fulfilled') {
          setDetail(interviewResult.value)
          setInterviewPaused(interviewResult.value.is_paused)
          setError(null)
        } else {
          setError(getApiErrorMessage(interviewResult.reason, '面试详情加载失败。'))
        }
        if (profileResult.status === 'fulfilled') {
          setHasVoiceConsent(
            profileResult.value.consents.some(
              (consent) => consent.purpose === 'voice_interview' && consent.status === 'granted',
            ),
          )
        } else {
          setHasVoiceConsent(false)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      sessionRef.current?.close()
      sessionRef.current = null
      void relayRef.current?.stop()
      relayRef.current = null
    }
  }, [id])

  useEffect(() => {
    if (liveState !== 'connected') return
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [liveState])

  const handleStart = async () => {
    if (!detail) return
    setLiveError(null)
    setTerminationMessage(null)
    setInterviewPaused(false)
    setElapsed(0)
    setLines([])
    setRelayInfo(null)
    setMuted(false)

    if (detail.live_transport === 'relay') {
      const relay = new RelayInterview(id, {
        onState: (state, message) => {
          setLiveState(state)
          if (state === 'error' && message) setLiveError(message)
          if (state === 'closed') {
            void getInterview(id).then(setDetail).catch(() => undefined)
          }
        },
        onLine: (line) => {
          setLines((current) => {
            const index = current.findIndex((item) => item.id === line.id)
            if (index >= 0) {
              const next = [...current]
              next[index] = line
              return next
            }
            return [...current, line]
          })
        },
        onRelay: setRelayInfo,
        onTerminated: (info) => {
          setTerminationMessage(info.message)
          void getInterview(id).then(setDetail).catch(() => undefined)
        },
        onControl: (state) => {
          setInterviewPaused(state.interviewPaused)
        },
      })
      relayRef.current = relay
      void relay.start()
      return
    }

    if (!audioRef.current) return
    try {
      const session = await connectInterview(id, audioRef.current, (state, message) => {
        setLiveState(state)
        if (state === 'error' && message) setLiveError(message)
      })
      sessionRef.current = session
    } catch {
      // The state callback already carries the message.
    }
  }

  const handleStop = async () => {
    if (relayRef.current) {
      await relayRef.current.stop()
      relayRef.current = null
      setLiveState('closed')
      void getInterview(id).then(setDetail).catch(() => undefined)
      return
    }
    sessionRef.current?.close()
    sessionRef.current = null
    setLiveState('closed')
    void getInterview(id).then(setDetail).catch(() => undefined)
  }

  const handleMute = () => {
    const next = !muted
    setMuted(next)
    relayRef.current?.setMuted(next)
  }

  if (loading) return <LoadingBlock text="正在加载面试安排…" />
  if (error || !detail) {
    return (
      <div className="mx-auto max-w-2xl">
        <ErrorNote message={error ?? '面试会话不存在。'} />
        <Link to="/interviews" className="btn-ghost mt-4">
          <ArrowLeft size={15} />
          返回我的面试
        </Link>
      </div>
    )
  }

  const meta = INTERVIEW_STATUS[detail.status] ?? { label: detail.status, tone: 'muted' as const }
  const questions = detail.plan?.questions ?? []
  const closed = ['ended', 'failed', 'revoked'].includes(detail.status)
  const connected = liveState === 'connected'
  const negotiating = liveState === 'requesting-mic' || liveState === 'negotiating'

  return (
    <div>
      <Link to="/interviews" className="btn-quiet mb-4 -ml-2">
        <ArrowLeft size={14} />
        返回我的面试
      </Link>

      <PageHeader
        eyebrow="Interview"
        title="AI 初筛沟通"
        description="这是一轮结构化的初步沟通，不是录用决定。系统只按下方问题依次提问，不会要求身份证、住址等敏感信息。"
        actions={<Badge tone={meta.tone} dot>{meta.label}</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-[1.45fr_1fr]">
        <div className="space-y-5">
          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft text-brand-deep">
                <ClipboardList size={16} />
              </span>
              <h2 className="section-title">本轮初始问题</h2>
            </div>
            {questions.length === 0 ? (
              <p className="mt-3 text-xs text-muted">本轮没有初始问题。</p>
            ) : (
              <>
                <ol className="mt-4 space-y-3">
                  {questions.map((question, index) => (
                    <li key={question.id ?? index} className="flex items-start gap-3 rounded-xl bg-white/60 p-3">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[11px] font-bold text-brand-deep">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-xs leading-relaxed text-ink/85">{question.text}</p>
                        {question.focus && <p className="mt-0.5 text-[10px] text-muted">关注点：{question.focus}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mt-3 rounded-xl border border-line/70 bg-white/50 px-3 py-2 text-[10.5px] leading-relaxed text-muted">
                  后续问题会根据你的回答和岗位要求实时生成。回答较为笼统时，面试官可能继续追问具体职责、实现过程、数据依据或关键取舍。
                </p>
              </>
            )}
          </section>

          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-jade-soft text-jade-deep">
                <ShieldCheck size={16} />
              </span>
              <h2 className="section-title">你的权利</h2>
            </div>
            <ul className="mt-3 space-y-2 text-xs leading-relaxed text-muted">
              <li>· 需要你单独授予「AI 语音面试」授权后才能接通，撤回会立即切断通话。</li>
              <li>· 系统默认不保存原始音频，只保留转写文本，供招聘方整理面试记录。</li>
              <li>· 系统会依据回答中的具体职责、做法、取舍和结果评估岗位相关能力证据，不代表通用能力或人格测评。</li>
              <li>· 系统会依据转写审核沟通中的尊重、秩序、作答态度与职业化表达；严重不当言行将如实记录并触发一票否决。</li>
              <li>· 招聘方可以实时旁听本场面试，并在需要时打开麦克风接管沟通；接管期间的双方发言同样会进入面试记录。</li>
              <li>· 你可以随时结束通话，已说过的内容仍会用于本次评估。</li>
              <li>· 沟通中出现不一致或不确定的信息会被标记为「待核实」，不会直接作为负面结论。</li>
            </ul>
          </section>
        </div>

        <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
          <section className="card p-6">
            <h2 className="section-title">通话</h2>
            <div className="mt-3 space-y-2 text-[11px] text-muted">
              <p className="flex items-center gap-1.5">
                <CalendarClock size={12} />
                安排于 {formatDateTime(detail.created_at)}
              </p>
              <p className="flex items-center gap-1.5">
                <PhoneCall size={12} />
                最长 {Math.round(detail.max_seconds / 60)} 分钟
              </p>
            </div>

            <div className="mt-4 rounded-2xl bg-white/60 p-3">
              <p className="text-[11px] leading-relaxed text-muted">
                接通前请允许浏览器使用麦克风，并佩戴耳机以获得更稳定的通话质量。
              </p>
            </div>

            <audio ref={audioRef} autoPlay playsInline className="hidden" />

            <div className="-mx-1 mt-4">
              <SoundWave
                height={connected ? 68 : 46}
                variant="ribbon"
                getLevel={getLevel}
                label={connected ? '通话音量声波' : '待接入声波'}
              />
            </div>

            {connected ? (
              <div className="mt-4">
                <div className="flex items-center justify-between rounded-xl bg-jade-soft px-3 py-2 text-xs text-jade-deep">
                  <span className="inline-flex items-center gap-1.5 font-semibold">
                    <Mic size={14} className={muted ? '' : 'animate-pulse'} />
                    {muted ? '已静音' : '通话进行中'}
                  </span>
                  <span className="font-mono tabular-nums">{formatClock(elapsed)}</span>
                </div>
                {relayInfo && (
                  <p className="mt-2 text-[10px] text-muted">
                    模型 {relayInfo.model}
                    {relayInfo.voice ? ` · 音色 ${relayInfo.voice}` : ''}
                  </p>
                )}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button type="button" className="btn-ghost" onClick={handleMute}>
                    <Mic size={15} />
                    {muted ? '取消静音' : '静音'}
                  </button>
                  <button type="button" className="btn-ghost" onClick={() => void handleStop()}>
                    <PhoneOff size={15} />
                    结束通话
                  </button>
                </div>
              </div>
            ) : closed ? (
              <div className="mt-4 rounded-xl bg-slate-100 px-3 py-3 text-xs text-slate-600">
                <p className="font-semibold">本次通话已结束</p>
                <p className="mt-1 text-[10.5px] leading-relaxed">
                  结束时间 {formatDateTime(detail.ended_at)}
                  {detail.end_reason
                    ? ` · 原因：${END_REASON[detail.end_reason] ?? detail.end_reason}`
                    : ''}
                </p>
              </div>
            ) : !hasVoiceConsent ? (
              <div className="mt-4">
                <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-[11px] leading-relaxed text-amber-800">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <span>还没有「AI 语音面试」授权，接通前需要你先在「我的 → 授权与隐私」中开启。</span>
                </div>
                <Link to="/profile" className="btn-primary mt-3 w-full">
                  去授权
                </Link>
              </div>
            ) : !detail.live_transport ? (
              <div className="mt-4">
                <div className="flex items-start gap-2 rounded-xl border border-line bg-white/70 px-3 py-3 text-[11px] leading-relaxed text-muted">
                  <Info size={14} className="mt-0.5 shrink-0" />
                  <span>
                    当前后端既没有配置实时语音凭证，也没有可用的通义千问密钥，因此暂不能在浏览器内接通。
                    请联系管理员完成语音服务配置。
                  </span>
                </div>
                <button type="button" className="btn-primary mt-3 w-full" disabled>
                  <PhoneCall size={15} />
                  实时语音暂不可用
                </button>
              </div>
            ) : (
              <div className="mt-4">
                <button
                  type="button"
                  className="btn-jade w-full"
                  disabled={negotiating}
                  onClick={() => void handleStart()}
                >
                  {negotiating ? <Loader2 size={15} className="animate-spin" /> : <PhoneCall size={15} />}
                  {negotiating ? '正在接通…' : '开始语音面试'}
                </button>
                <p className="mt-2 text-center text-[10px] text-muted">
                  连接由后端中转，密钥不会下发到浏览器。
                </p>
              </div>
            )}

            {lines.length > 0 && (
              <div className="mt-4 max-h-64 space-y-2 overflow-y-auto rounded-xl bg-white/70 p-3">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
                  实时转写
                </p>
                {lines.map((line) => (
                  <div key={line.id}>
                    <p className="text-[10px] font-bold text-muted">
                      {line.role === 'interviewer'
                        ? 'AI 面试官'
                        : line.role === 'hr'
                          ? 'HR'
                          : '我'}
                      {line.pending ? ' · 识别中…' : ''}
                    </p>
                    <p className="text-[11px] leading-relaxed text-ink/85">{line.text}</p>
                  </div>
                ))}
              </div>
            )}

            {interviewPaused && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-[11px] leading-relaxed text-amber-800">
                <p className="font-semibold">面试流程已被 HR 暂停</p>
                <p className="mt-1">请等待 HR 恢复面试流程后继续交流。</p>
              </div>
            )}

            {liveError && <div className="mt-3"><ErrorNote message={liveError} /></div>}
            {terminationMessage && (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-[11px] leading-relaxed text-red-800">
                <p className="font-semibold">通话已由系统终止</p>
                <p className="mt-1">{terminationMessage}</p>
              </div>
            )}
            {liveState === 'closed' && !closed && (
              <p className="mt-3 text-center text-[10px] text-muted">通话已结束，可刷新页面查看最新状态。</p>
            )}
          </section>

          <section className="card p-6">
            <div className="flex items-start gap-2">
              <Info size={15} className="mt-0.5 shrink-0 text-muted" />
              <p className="text-[10.5px] leading-relaxed text-muted">
                如果麦克风权限被拒绝，请在浏览器地址栏的站点设置中允许麦克风后重新进入本页；
                会议只在 localhost 或 HTTPS 下可用。
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
