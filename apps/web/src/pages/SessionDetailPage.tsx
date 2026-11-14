import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Bot,
  Clock,
  FileText,
  Mic,
  MicOff,
  PhoneOff,
  PlayCircle,
  Radio,
  RefreshCw,
  UserRound,
} from 'lucide-react'
import { getCandidate } from '../api/candidates'
import { getVoiceReport, getVoiceSession, listVoiceTurns, regenerateVoiceReport } from '../api/voice'
import { PremiumWaveform } from '../components/visual/PremiumWaveform'
import { useRealtimeInterview } from '../hooks/useRealtimeInterview'
import { getApiErrorMessage, isApiNotFound } from '../lib/apiError'
import { formatDateTime, VOICE_STATUS_LABELS } from '../lib/format'
import type { CallReport } from '../types'

function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const rest = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${rest}`
}

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
  const interview = useRealtimeInterview(id)
  const transcriptRef = useRef<HTMLDivElement | null>(null)

  const sessionQuery = useQuery({
    queryKey: ['voiceSession', id],
    queryFn: () => getVoiceSession(id),
    enabled: Boolean(id),
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
  const isLive = interview.phase === 'live' || interview.phase === 'connecting'
  const isEnded = session?.status === 'ended' || session?.status === 'failed' || session?.status === 'revoked'

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [interview.lines.length])

  const finish = useMutation({
    mutationFn: () => interview.stop('completed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voiceSession', id] })
      void queryClient.invalidateQueries({ queryKey: ['voiceTurns', id] })
      void queryClient.invalidateQueries({ queryKey: ['voiceSessions'] })
      void queryClient.invalidateQueries({ queryKey: ['voiceReport', id] })
    },
  })

  const regenerate = useMutation({
    mutationFn: () => regenerateVoiceReport(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voiceReport', id] })
    },
  })

  const liveLines = interview.lines
  const persistedTurns = turnsQuery.data ?? []
  const showLiveTranscript = liveLines.length > 0
  const questions = session?.plan_json?.questions ?? []
  const hasAcousticMotion = isLive && !interview.muted

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
            {interview.relay ? ` · ${interview.relay.model}` : ''}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/sessions" className="ttc-btn ttc-btn-secondary">
            返回列表
          </Link>
          {session.status === 'created' && !isLive && (
            <button type="button" className="ttc-btn ttc-btn-primary" onClick={interview.start}>
              <PlayCircle size={16} />
              开始面试
            </button>
          )}
          {isLive && (
            <>
              <span className="ttc-live-clock">
                <i />
                {formatClock(interview.elapsed)}
              </span>
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                onClick={() => interview.setMuted(!interview.muted)}
              >
                {interview.muted ? <MicOff size={16} /> : <Mic size={16} />}
                {interview.muted ? '取消静音' : '静音'}
              </button>
              <button
                type="button"
                className="ttc-btn ttc-btn-primary"
                disabled={finish.isPending}
                onClick={() => finish.mutate()}
              >
                <PhoneOff size={16} />
                {finish.isPending ? '收尾中…' : '结束面试'}
              </button>
            </>
          )}
        </div>
      </section>

      {interview.error && (
        <div className="ttc-inline-error" role="alert">
          <AlertCircle size={16} />
          <span>{interview.error}</span>
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
                interview.phase === 'live' ? 'ttc-voice-badge-ok' : 'ttc-voice-badge-muted'
              }`}
            >
              {interview.phase === 'live'
                ? interview.muted
                  ? '已静音'
                  : '实时收音中'
                : VOICE_STATUS_LABELS[session.status] ?? session.status}
            </span>
          </div>

          <div className={`ttc-acoustic-stage ${hasAcousticMotion ? 'is-active' : ''}`}>
            <div className="ttc-acoustic-stage-meta">
              <span className="ttc-acoustic-pill">
                <Radio size={13} aria-hidden="true" />
                {hasAcousticMotion
                  ? '声学波形实时响应'
                  : interview.muted
                    ? '麦克风已静音 · 波形暂停'
                    : isEnded
                      ? '会话已结束 · 保留完整转写回放'
                      : '待开启实时语音会话'}
              </span>
              <span className="ttc-muted">
                {interview.relay?.model ?? session.provider} · 上限 {Math.round(session.max_seconds / 60)} 分钟
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
                    ? '点击右上角「开始面试」，浏览器会请求麦克风权限并接入实时语音模型，AI 面试官会先开场白。'
                    : isLive
                      ? '正在等待双方首句语音转写…'
                      : '实时语音服务没有返回任何转写文本。'}
                </p>
              </div>
            )}

            {!showLiveTranscript &&
              persistedTurns.map((turn) => (
                <div key={turn.id} className={`ttc-transcript-line is-${turn.role}`}>
                  <span className="ttc-transcript-who">
                    {turn.role === 'interviewer' ? <Bot size={14} /> : <UserRound size={14} />}
                    {turn.role === 'interviewer' ? 'AI 面试官' : turn.role === 'candidate' ? '候选人' : '系统'}
                  </span>
                  <p>{turn.text}</p>
                </div>
              ))}

            {showLiveTranscript &&
              liveLines.map((line) => (
                <div key={line.id} className={`ttc-transcript-line is-${line.role}`}>
                  <span className="ttc-transcript-who">
                    {line.role === 'interviewer' ? <Bot size={14} /> : <UserRound size={14} />}
                    {line.role === 'interviewer' ? 'AI 面试官' : line.role === 'candidate' ? '候选人' : '系统'}
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
                <h2>面试提问计划</h2>
              </div>
              {questions.length > 0 && <span className="ttc-badge ttc-badge-blue">{questions.length} 题</span>}
            </div>
            <ol className="ttc-question-list">
              {questions.map((question, index) => (
                <li key={question.id} className="ttc-question-item">
                  <span className="ttc-question-num">{String(index + 1).padStart(2, '0')}</span>
                  <div className="ttc-question-copy">
                    <span className="ttc-question-section">{question.section}</span>
                    <p>{question.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            {questions.length === 0 && <p className="ttc-muted">该会话没有绑定问题清单。</p>}
          </article>

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
                  <span>{interview.relay?.model ?? session.provider ?? '—'}</span>
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
              <p className="ttc-muted">结束原因：{session.end_reason}</p>
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
