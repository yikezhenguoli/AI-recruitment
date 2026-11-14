import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Bot,
  Clock,
  FileText,
  Hand,
  Headphones,
  Mic,
  MicOff,
  PauseCircle,
  PlayCircle,
  Radio,
  RefreshCw,
  UserRound,
} from 'lucide-react'
import { getCandidate } from '../api/candidates'
import {
  controlVoiceInterview,
  getVoiceReport,
  getVoiceSession,
  listVoiceTurns,
  regenerateVoiceReport,
} from '../api/voice'
import { PremiumWaveform } from '../components/visual/PremiumWaveform'
import { CapabilityAssessmentPanel } from '../components/voice/CapabilityAssessmentPanel'
import { ConductAssessmentPanel } from '../components/voice/ConductAssessmentPanel'
import { useHRObserver } from '../hooks/useHRObserver'
import { useVoiceSessionStatus } from '../hooks/useVoiceSessionStatus'
import { getApiErrorMessage, isApiNotFound } from '../lib/apiError'
import { formatDateTime, VOICE_STATUS_LABELS } from '../lib/format'
import type { CallReport } from '../types'

function ReportPanel({
  report,
  onRegenerate,
  regenerating,
}: {
  report: CallReport
  onRegenerate?: () => void
  regenerating?: boolean
}) {
  return (
    <article className="ttc-card ttc-report-card">
      <div className="ttc-card-head">
        <div>
          <div className="ttc-mini-heading">
            <FileText size={14} />
            <span>CALL SUMMARY</span>
          </div>
          <h2>沟通纪要</h2>
        </div>
        {onRegenerate && (
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary ttc-btn-sm"
            disabled={regenerating}
            onClick={onRegenerate}
          >
            <RefreshCw size={14} />
            {regenerating ? '生成中…' : '重新整理'}
          </button>
        )}
      </div>

      <div className="ttc-report-meta">
        <span>共 {report.summary.turn_count ?? 0} 轮发言</span>
        <span>模型 {report.model_version}</span>
      </div>

      <CapabilityAssessmentPanel assessment={report.capability} />
      <ConductAssessmentPanel assessment={report.conduct} />

      {report.summary.overview && <p className="ttc-report-overview">{report.summary.overview}</p>}

      {report.summary.qa && report.summary.qa.length > 0 && (
        <>
          <h3 className="ttc-report-subhead">问答整理</h3>
          <ul className="ttc-plain-list">
            {report.summary.qa.map((item) => (
              <li key={item.question}>
                <strong>{item.question}</strong>
                <br />
                {item.answer_summary}
              </li>
            ))}
          </ul>
        </>
      )}

      {report.followups.length > 0 && (
        <>
          <h3 className="ttc-report-subhead">建议后续面试官确认</h3>
          <ul className="ttc-plain-list">
            {report.followups.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {report.summary.limitations && report.summary.limitations.length > 0 && (
        <>
          <h3 className="ttc-report-subhead">记录边界</h3>
          <ul className="ttc-plain-list ttc-report-limits">
            {report.summary.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </article>
  )
}

export default function SessionDetailPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const observer = useHRObserver(id)
  useVoiceSessionStatus(id)
  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const [flowPaused, setFlowPaused] = useState(false)

  const sessionQuery = useQuery({
    queryKey: ['voiceSession', id],
    queryFn: () => getVoiceSession(id),
    enabled: Boolean(id),
    // Keep a low-frequency fallback for environments where WebSockets are blocked.
    refetchInterval: (query) =>
      query.state.data?.status === 'created' ? 5_000 : false,
  })
  const candidateQuery = useQuery({
    queryKey: ['candidate', sessionQuery.data?.candidate_id],
    queryFn: () => getCandidate(sessionQuery.data!.candidate_id),
    enabled: Boolean(sessionQuery.data?.candidate_id),
  })
  const turnsQuery = useQuery({
    queryKey: ['voiceTurns', id],
    queryFn: () => listVoiceTurns(id),
    enabled: Boolean(id),
  })
  const reportQuery = useQuery({
    queryKey: ['voiceReport', id],
    queryFn: () => getVoiceReport(id),
    enabled: Boolean(id),
    retry: false,
  })

  const session = sessionQuery.data
  const isEnded = session?.status === 'ended' || session?.status === 'failed' || session?.status === 'revoked'
  const isObserving = observer.phase === 'listening' || observer.phase === 'connecting'

  useEffect(() => {
    if (session) setFlowPaused(session.is_paused)
  }, [session?.is_paused])

  useEffect(() => {
    if (observer.phase === 'listening') setFlowPaused(observer.interviewPaused)
  }, [observer.interviewPaused, observer.phase])

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [observer.lines.length])

  const regenerate = useMutation({
    mutationFn: () => regenerateVoiceReport(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voiceReport', id] })
    },
  })

  const flowControl = useMutation({
    mutationFn: (action: 'pause' | 'resume') => controlVoiceInterview(id, action),
    onSuccess: (result) => {
      setFlowPaused(result.interview_paused)
      void queryClient.invalidateQueries({ queryKey: ['voiceSession', id] })
      void queryClient.invalidateQueries({ queryKey: ['voiceSessions'] })
    },
  })

  const liveLines = observer.lines
  const persistedTurns = turnsQuery.data ?? []
  const showLiveTranscript = liveLines.length > 0
  const questions = session?.plan_json?.questions ?? []
  const customQuestionCount = questions.filter((question) => question.source === 'hr').length
  const hasAcousticMotion = observer.phase === 'listening'

  if (sessionQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-skeleton-card" />
      </div>
    )
  }

  if (sessionQuery.isError || !session) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法打开语音会话</strong>
            <span>{getApiErrorMessage(sessionQuery.error)}</span>
          </div>
          <Link to="/sessions" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回列表
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="ttc-mini-heading">
            <Radio size={14} />
            <span>{session.scenario?.toUpperCase() ?? 'SCREEN'} · VOICE STAGE</span>
          </div>
          <h1>{candidateQuery.data?.display_name ?? '语音会话'}</h1>
          <p>
            {VOICE_STATUS_LABELS[session.status] ?? session.status} · 创建于{' '}
            {formatDateTime(session.created_at)}
            {observer.model ? ` · ${observer.model}` : ''}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/sessions" className="ttc-btn ttc-btn-secondary">
            返回列表
          </Link>
          {session.status === 'created' && (
            <span className="ttc-badge ttc-badge-amber">等待候选人接通</span>
          )}
          {session.status === 'live' && !isObserving && (
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary"
              onClick={observer.start}
            >
              <Headphones size={16} />
              实时旁听 / 接管
            </button>
          )}
          {session.status === 'live' && (
            <button
              type="button"
              className={`ttc-btn ${flowPaused ? 'ttc-btn-primary' : 'ttc-btn-secondary'}`}
              disabled={flowControl.isPending}
              onClick={() => flowControl.mutate(flowPaused ? 'resume' : 'pause')}
            >
              {flowPaused ? <PlayCircle size={16} /> : <PauseCircle size={16} />}
              {flowControl.isPending
                ? flowPaused
                  ? '恢复中…'
                  : '暂停中…'
                : flowPaused
                  ? '恢复面试'
                  : '暂停面试'}
            </button>
          )}
        </div>
      </section>

      {observer.error && (
        <div className="ttc-inline-error" role="alert">
          <AlertCircle size={16} />
          <span>{observer.error}</span>
        </div>
      )}

      {flowControl.isError && (
        <div className="ttc-inline-error" role="alert">
          <AlertCircle size={16} />
          <span>{getApiErrorMessage(flowControl.error, '暂停或恢复面试失败。')}</span>
        </div>
      )}

      {regenerate.isError && (
        <div className="ttc-inline-error" role="alert">
          <AlertCircle size={16} />
          <span>{getApiErrorMessage(regenerate.error, '沟通纪要生成失败。')}</span>
        </div>
      )}

      <div className="ttc-session-grid">
        <article className="ttc-card ttc-transcript-card">
          <div className="ttc-card-head">
            <div>
              <div className="ttc-mini-heading">
                <Mic size={14} />
                <span>LIVE TRANSCRIPT</span>
              </div>
              <h2>实时声学舞台与对话转写</h2>
            </div>
            <span
              className={`ttc-voice-badge ${
                observer.phase === 'listening'
                  ? 'ttc-voice-badge-ok'
                  : 'ttc-voice-badge-muted'
              }`}
            >
              {flowPaused
                ? 'HR 已暂停面试'
                : observer.phase === 'listening'
                ? observer.hrControl
                  ? 'HR 接管 · 同步记录中'
                  : 'HR 旁听 · AI 主持中'
                : VOICE_STATUS_LABELS[session.status] ?? session.status}
            </span>
          </div>

          <div className={`ttc-acoustic-stage ${hasAcousticMotion ? 'is-active' : ''}`}>
            <div className="ttc-acoustic-stage-meta">
              <span className="ttc-acoustic-pill">
                <Radio size={13} aria-hidden="true" />
                {flowPaused
                  ? '面试流程已暂停 · 等待 HR 恢复'
                  : hasAcousticMotion
                  ? observer.hrControl
                    ? 'HR 接管中 · 候选人可听到 HR 发言'
                    : 'HR 正在同步收听候选人与 AI 对话'
                  : isEnded
                    ? '会话已结束 · 保留完整转写回放'
                    : session.status === 'live'
                      ? '候选人通话中 · 可点击实时旁听'
                      : '等待候选人接通 AI 面试'}
              </span>
              <span className="ttc-muted">
                {observer.model || session.provider} · 上限{' '}
                {Math.round(session.max_seconds / 60)} 分钟
              </span>
            </div>
            <PremiumWaveform
              tone="subtle"
              height={88}
              motionOverride={hasAcousticMotion}
              label="实时语音面接声学信号波形"
            />
          </div>

          <div className="ttc-transcript-body" ref={transcriptRef}>
            {!showLiveTranscript && persistedTurns.length === 0 && (
              <div className="ttc-transcript-empty">
                <p>
                  {session.status === 'created'
                    ? '等待候选人进入求职门户并接通 AI 面试。企业端不会由 HR 建立候选人通话，也不会自动开启 HR 麦克风。'
                    : observer.phase === 'listening'
                      ? 'HR 正在旁听，等待候选人或 AI 的首句转写…'
                      : '实时语音服务没有返回任何转写文本。'}
                </p>
              </div>
            )}

            {!showLiveTranscript &&
              persistedTurns.map((turn) => (
                <div key={turn.id} className={`ttc-transcript-line is-${turn.role}`}>
                  <span className="ttc-transcript-who">
                    {turn.role === 'interviewer' ? <Bot size={14} /> : <UserRound size={14} />}
                    {turn.role === 'interviewer'
                      ? 'AI 面试官'
                      : turn.role === 'candidate'
                        ? '候选人'
                        : turn.role === 'hr'
                          ? 'HR'
                          : '系统'}
                  </span>
                  <p>{turn.text}</p>
                </div>
              ))}

            {showLiveTranscript &&
              liveLines.map((line) => (
                <div key={line.id} className={`ttc-transcript-line is-${line.role}`}>
                  <span className="ttc-transcript-who">
                    {line.role === 'interviewer' ? <Bot size={14} /> : <UserRound size={14} />}
                    {line.role === 'interviewer'
                      ? 'AI 面试官'
                      : line.role === 'candidate'
                        ? '候选人'
                        : line.role === 'hr'
                          ? 'HR'
                          : '系统'}
                  </span>
                  <p className={line.pending ? 'is-pending' : ''}>{line.text}</p>
                </div>
              ))}
          </div>
        </article>

        <aside className="ttc-session-side">
          <article className="ttc-card ttc-voice-panel">
            <div className="ttc-voice-panel-head">
              <div>
                <div className="ttc-mini-heading">
                  <Bot size={14} />
                  <span>INTERVIEW PLAN</span>
                </div>
                <h2>初始问题与追问方向</h2>
              </div>
              {questions.length > 0 && (
                <span className="ttc-badge ttc-badge-blue">
                  {customQuestionCount > 0
                    ? `${customQuestionCount} 个 HR 指定 · 共 ${questions.length} 个`
                    : `${questions.length} 个初始问题`}
                </span>
              )}
            </div>
            <ol className="ttc-question-list">
              {questions.map((question, index) => (
                <li key={question.id} className="ttc-question-item">
                  <span className="ttc-question-num">{String(index + 1).padStart(2, '0')}</span>
                  <div className="ttc-question-copy">
                    <span className="ttc-question-section">
                      {question.source === 'hr'
                        ? 'HR 指定必问'
                        : `AI · ${question.section}`}
                    </span>
                    <p>{question.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            {questions.length === 0 && <p className="ttc-muted">该会话没有绑定初始问题。</p>}
            {questions.length > 0 && (
              <p className="ttc-muted">
                以下仅是本轮开场切入点；实时面试官会根据候选人的回答和岗位相关性继续追问。
              </p>
            )}
          </article>

          {(session.status === 'live' || isObserving) && (
            <article className="ttc-card ttc-voice-panel">
              <div className="ttc-voice-panel-head">
                <div>
                  <div className="ttc-mini-heading">
                    <Headphones size={14} />
                    <span>HR LIVE CONTROL</span>
                  </div>
                  <h2>实时旁听与接管</h2>
                </div>
                <span
                  className={`ttc-badge ${
                    observer.phase === 'listening'
                      ? 'ttc-badge-green'
                      : observer.phase === 'error'
                        ? 'ttc-badge-red'
                        : 'ttc-badge-amber'
                  }`}
                >
                  {observer.phase === 'listening'
                    ? flowPaused
                      ? '面试流程已暂停'
                      : observer.hrControl
                      ? 'HR 接管中'
                      : 'AI 主持中'
                    : observer.phase === 'connecting'
                      ? '连接中'
                      : observer.phase === 'error'
                        ? '连接异常'
                        : '未旁听'}
                </span>
              </div>

              {!isObserving ? (
                <>
                  <p className="ttc-muted">
                    旁听后可以实时听到候选人的回答；接管时会暂停 AI 自动提问，
                    打开麦克风即可直接与候选人沟通。
                  </p>
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-primary ttc-btn-sm"
                    onClick={observer.start}
                  >
                    <Headphones size={14} />
                    开始实时旁听
                  </button>
                </>
              ) : (
                <>
                  <div className="ttc-voice-meta-list">
                    <div className="ttc-voice-meta-row">
                      <span className="ttc-voice-meta-icon"><Bot size={15} /></span>
                      <div className="ttc-voice-meta-copy">
                        <strong>AI 自动提问</strong>
                        <span>
                          {flowPaused
                            ? '面试流程已暂停，等待 HR 恢复'
                            : observer.aiActive
                              ? '开启'
                              : '已暂停，持续记录上下文'}
                        </span>
                      </div>
                    </div>
                    <div className="ttc-voice-meta-row">
                      <span className="ttc-voice-meta-icon"><Mic size={15} /></span>
                      <div className="ttc-voice-meta-copy">
                        <strong>HR 麦克风</strong>
                        <span>{observer.micOpen ? '已打开，候选人可实时听到' : '关闭'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="ttc-heading-actions">
                    {!observer.hrControl && (
                      <button
                        type="button"
                        className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        onClick={observer.takeControl}
                      >
                        <Hand size={14} />
                        打断 AI 并接管
                      </button>
                    )}
                    <button
                      type="button"
                      className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                      onClick={() => void observer.toggleMic()}
                    >
                      {observer.micOpen ? <MicOff size={14} /> : <Mic size={14} />}
                      {observer.micOpen ? '关闭麦克风' : '打开麦克风'}
                    </button>
                    {observer.hrControl && (
                      <button
                        type="button"
                        className="ttc-btn ttc-btn-primary ttc-btn-sm"
                        onClick={observer.releaseControl}
                      >
                        <Bot size={14} />
                        交回 AI
                      </button>
                    )}
                    <button
                      type="button"
                      className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                      onClick={observer.stop}
                    >
                      退出旁听
                    </button>
                  </div>
                  <p className="ttc-muted">
                    HR 接管期间，双方语音仍进入同一转录链路；交回 AI 后，
                    系统会基于完整上下文继续追问，而不是重新开始问题清单。
                  </p>
                </>
              )}
            </article>
          )}

          <article className="ttc-card ttc-voice-panel">
            <div className="ttc-voice-panel-head">
              <div>
                <div className="ttc-mini-heading">
                  <RefreshCw size={14} />
                  <span>SESSION STATE</span>
                </div>
                <h2>实时连接信息</h2>
              </div>
            </div>
            <div className="ttc-voice-meta-list">
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <Bot size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>实时模型</strong>
                  <span>{observer.model || session.provider || '—'}</span>
                </div>
              </div>
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <Clock size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>最长通话时长</strong>
                  <span>{Math.round(session.max_seconds / 60)} 分钟</span>
                </div>
              </div>
            </div>
            {session.end_reason && (
              <p className="ttc-muted">
                结束原因：
                {session.end_reason === 'conduct_violation'
                  ? '严重言行触发自动结束'
                  : session.end_reason}
              </p>
            )}
          </article>

          {reportQuery.data ? (
            <ReportPanel
              report={reportQuery.data}
              onRegenerate={() => regenerate.mutate()}
              regenerating={regenerate.isPending}
            />
          ) : (
            isEnded && (
              <article className="ttc-card ttc-voice-panel">
                <div className="ttc-voice-panel-head">
                  <div>
                    <div className="ttc-mini-heading">
                      <FileText size={14} />
                      <span>CALL SUMMARY</span>
                    </div>
                    <h2>沟通纪要</h2>
                  </div>
                </div>
                <p className="ttc-muted">
                  {reportQuery.isError && !isApiNotFound(reportQuery.error)
                    ? getApiErrorMessage(reportQuery.error, '沟通纪要暂时无法读取。')
                    : '对话已完成，正在生成或尚未整理结构化纪要。'}
                </p>
                <button
                  type="button"
                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                  disabled={regenerate.isPending}
                  onClick={() => regenerate.mutate()}
                >
                  <RefreshCw size={14} />
                  {regenerate.isPending ? '整理中…' : '刷新 / 生成纪要'}
                </button>
              </article>
            )
          )}
        </aside>
      </div>
    </div>
  )
}
