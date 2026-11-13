import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Bot,
  FileText,
  Mic,
  MicOff,
  PhoneOff,
  PlayCircle,
  RefreshCw,
  UserRound,
} from 'lucide-react'
import { getCandidate } from '../api/candidates'
import { getVoiceReport, getVoiceSession, listVoiceTurns, regenerateVoiceReport } from '../api/voice'
import { useRealtimeInterview } from '../hooks/useRealtimeInterview'
import { getApiErrorMessage, isApiNotFound } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { CallReport, VoiceSessionStatus } from '../types'

const STATUS_LABEL: Record<VoiceSessionStatus, string> = {
  created: '待接通',
  connecting: '连接中',
  live: '进行中',
  ended: '已结束',
  failed: '失败',
  revoked: '授权撤回',
}

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
  const qa = report.summary.qa ?? []
  return (
    <div className="ttc-report-card">
      <div className="ttc-mini-heading">
        <FileText size={14} />
        CALL REPORT
      </div>
      <h2>通话纪要</h2>
      <div className="ttc-report-meta">
        <span>状态：{report.summary.status === 'unassessed' ? '未做能力评分' : report.summary.status}</span>
        <span>轮次：{report.summary.turn_count ?? 0}</span>
        <span>模型：{report.model_version}</span>
      </div>

      {report.summary.overview && (
        <p className="ttc-report-overview">{report.summary.overview}</p>
      )}

      {qa.length > 0 && (
        <>
          <h3 className="ttc-report-subhead">问答要点</h3>
          <ul className="ttc-plain-list">
            {qa.map((item) => (
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
          <h3 className="ttc-report-subhead">建议进一步确认</h3>
          <ul className="ttc-plain-list">
            {report.followups.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {report.summary.limitations && report.summary.limitations.length > 0 && (
        <ul className="ttc-plain-list ttc-report-limits">
          {report.summary.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      {report.quotes.length > 0 && (
        <>
          <h3 className="ttc-report-subhead">候选人原话</h3>
          <ul className="ttc-quote-list">
            {report.quotes.map((quote) => (
              <li key={quote.turn_id}>{quote.text}</li>
            ))}
          </ul>
        </>
      )}

      {report.model_version === 'transcript-v1' && report.summary.turn_count ? (
        <button
          type="button"
          className="ttc-btn ttc-btn-secondary ttc-btn-sm"
          disabled={regenerating}
          onClick={onRegenerate}
        >
          {regenerating ? '生成纪要中…' : '用现有转写生成 AI 纪要'}
        </button>
      ) : null}

      <p className="ttc-report-disclaimer">
        纪要由模型按转写整理，不做录用建议；跨来源核验结果见候选人详情页。
      </p>
    </div>
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
      window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: ['voiceReport', id] }), 600)
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

  if (sessionQuery.isError) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取会话</strong>
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
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            SESSION
            <span className="hero-eyebrow-line" />
            <span>{session?.scenario?.toUpperCase() ?? 'SCREEN'}</span>
          </div>
          <h1>{candidateQuery.data?.display_name ?? '语音会话'}</h1>
          <p>
            {session?.status ? STATUS_LABEL[session.status] : '加载中'} · 创建于{' '}
            {formatDateTime(session?.created_at)}
            {interview.relay ? ` · ${interview.relay.model}` : ''}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/sessions" className="ttc-btn ttc-btn-secondary">
            返回列表
          </Link>
          {session?.status === 'created' && !isLive && (
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
        <div className="ttc-inline-error">
          <AlertCircle size={16} />
          <span>{interview.error}</span>
        </div>
      )}

      {regenerate.isError && (
        <div className="ttc-inline-error">
          <AlertCircle size={16} />
          <span>{getApiErrorMessage(regenerate.error, '纪要生成失败，请稍后重试。')}</span>
        </div>
      )}

      <div className="ttc-session-grid">
        <article className="ttc-card ttc-transcript-card">
          <div className="ttc-voice-panel-head">
            <div>
              <div className="ttc-mini-heading">
                <Mic size={14} />
                LIVE TRANSCRIPT
              </div>
              <h2>实时转写</h2>
            </div>
            <span
              className={`ttc-voice-badge ${
                interview.phase === 'live' ? 'ttc-voice-badge-ok' : 'ttc-voice-badge-muted'
              }`}
            >
              {interview.phase === 'live' ? '实时' : STATUS_LABEL[session?.status ?? 'created']}
            </span>
          </div>

          <div className="ttc-transcript-body" ref={transcriptRef}>
            {!showLiveTranscript && persistedTurns.length === 0 && (
              <div className="ttc-voice-transcript-empty">
                <span className="ttc-voice-transcript-icon">
                  <Bot size={19} />
                </span>
                <strong>
                  {session?.status === 'created' ? '等待开始' : '本次会话没有转写内容'}
                </strong>
                <p>
                  {session?.status === 'created'
                    ? '点击「开始面试」后，AI 面试官会先开口提问，你的回答会实时显示在这里。'
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

            {liveLines.map((line) => (
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

        <div className="ttc-session-side">
          <article className="ttc-card ttc-voice-panel">
            <div className="ttc-voice-panel-head">
              <div>
                <div className="ttc-mini-heading">
                  <Bot size={14} />
                  INTERVIEW PLAN
                </div>
                <h2>面试问题</h2>
              </div>
            </div>
            <ol className="ttc-question-list">
              {(questions.length > 0 ? questions : []).map((question) => (
                <li key={question.id}>
                  <span className="ttc-question-section">{question.section}</span>
                  {question.text}
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
                  SESSION STATE
                </div>
                <h2>会话状态</h2>
              </div>
            </div>
            <div className="ttc-voice-meta">
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <Mic size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>状态</strong>
                  <span>{session?.status ?? '—'}</span>
                </div>
              </div>
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <Bot size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>实时模型</strong>
                  <span>{interview.relay?.model ?? session?.provider ?? '—'}</span>
                </div>
              </div>
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <PlayCircle size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>时长上限</strong>
                  <span>{formatClock(session?.max_seconds ?? 0)}</span>
                </div>
              </div>
            </div>
            {session?.end_reason && (
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
                      CALL REPORT
                    </div>
                    <h2>通话报告</h2>
                  </div>
                </div>
                <p className="ttc-muted">
                  {reportQuery.isError
                    ? isApiNotFound(reportQuery.error)
                      ? '该会话没有生成通话报告：实时语音没有产生转写内容，或尚未结束。'
                      : getApiErrorMessage(reportQuery.error, '报告尚未生成。')
                    : '正在生成报告…'}
                </p>
                {reportQuery.isError && !isApiNotFound(reportQuery.error) && (
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    onClick={() => void reportQuery.refetch()}
                  >
                    重新获取
                  </button>
                )}
              </article>
            )
          )}
        </div>
      </div>
    </div>
  )
}
