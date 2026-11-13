import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { getSessionResults } from '../../api/candidates'
import { createWebSocket } from '../../api/websocket'
import { getApiErrorMessage } from '../../lib/apiError'
import type {
  CandidateProgress,
  CandidateResult,
  SessionResultsResponse,
  Stage,
  WSMessage,
} from '../../types'

interface Props {
  sessionId: string
  totalFiles: number
  jobRoleTitle?: string
  onComplete: (results: SessionResultsResponse) => void
}

const STAGE_LABEL: Record<Stage, string> = {
  queued: '排队中',
  parsing: '解析文件',
  extracting: '提取信息',
  screening: '条件筛选',
  evaluating: 'AI 评分',
  done: '已完成',
  error: '处理失败',
  skipped: '重复/跳过',
  filtered: '已过滤',
  review: '待人工复核',
}

const STAGE_ORDER: Stage[] = ['queued', 'parsing', 'extracting', 'screening', 'evaluating', 'done']
const FINAL_STAGES: Stage[] = ['done', 'error', 'skipped', 'filtered', 'review']
const STAGE_PERCENT: Record<Stage, number> = {
  queued: 0,
  parsing: 20,
  extracting: 40,
  screening: 60,
  evaluating: 80,
  done: 100,
  error: 100,
  skipped: 100,
  filtered: 100,
  review: 100,
}

type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'failed'

function toProgress(candidate: CandidateResult): CandidateProgress {
  return {
    candidateId: candidate.candidate_id,
    fileName: candidate.file_name,
    name: candidate.name,
    email: candidate.email,
    phone: candidate.phone,
    score: candidate.score,
    explanation: candidate.explanation,
    dimensionScores: candidate.dimension_scores,
    stage: candidate.stage,
    error: candidate.error,
    parseMethod: candidate.parse_method,
    screeningOutcome: candidate.screening_outcome,
    screeningReason: candidate.screening_reason,
    graduationYearInfo: candidate.graduation_year_info || { source: 'not_applicable' },
    previewAvailable: Boolean(candidate.preview_available),
  }
}

function StageBar({ stage }: { stage: Stage }) {
  const idx = STAGE_ORDER.indexOf(stage)
  const isIssue = stage === 'error' || stage === 'skipped'
  return (
    <div className="ttc-stage-bar" aria-hidden="true">
      {STAGE_ORDER.slice(0, 5).map((item, index) => {
        const filled = !isIssue && idx >= index + 1
        const active = !isIssue && STAGE_ORDER[idx] === item
        return (
          <i
            key={item}
            className={`${filled ? 'is-filled' : ''} ${active ? 'is-active' : ''} ${
              isIssue ? 'is-error' : ''
            }`}
          />
        )
      })}
    </div>
  )
}

function StatusIcon({ stage }: { stage: Stage }) {
  if (stage === 'done') return <CheckCircle2 size={18} className="ttc-icon-ok" />
  if (stage === 'error') return <AlertCircle size={18} className="ttc-icon-danger" />
  if (FINAL_STAGES.includes(stage)) return <AlertCircle size={18} className="ttc-icon-warn" />
  return <Loader2 size={18} className="animate-spin ttc-icon-spin" />
}

export function ProcessingPanel({ sessionId, totalFiles, jobRoleTitle, onComplete }: Props) {
  const [candidates, setCandidates] = useState<Map<string, CandidateProgress>>(new Map())
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    let disposed = false
    let completed = false
    let ws: WebSocket | null = null
    let reconnectTimer: number | undefined
    let pollTimer: number | undefined
    let retry = 0
    let errorShown = false
    let finishing = false

    const clearReconnectTimer = () => {
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      reconnectTimer = undefined
    }

    const clearTimers = () => {
      clearReconnectTimer()
      if (pollTimer) window.clearInterval(pollTimer)
      pollTimer = undefined
    }

    const closeSocket = () => {
      if (ws) {
        ws.onopen = null
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        try {
          ws.close()
        } catch {
          // ignore close errors
        }
        ws = null
      }
    }

    const finish = async (knownResults?: SessionResultsResponse) => {
      if (completed || disposed || finishing) return
      finishing = true
      clearReconnectTimer()
      closeSocket()
      setDone(true)
      try {
        const finalResults = knownResults ?? (await getSessionResults(sessionId))
        if (disposed) return
        completed = true
        setError(null)
        if (pollTimer) {
          window.clearInterval(pollTimer)
          pollTimer = undefined
        }
        const mapped = new Map<string, CandidateProgress>()
        finalResults.results.forEach((candidate) => {
          mapped.set(candidate.candidate_id, toProgress(candidate))
        })
        setCandidates(mapped)
        onCompleteRef.current(finalResults)
      } catch (err: unknown) {
        // Keep the polling interval alive so a transient result-read failure
        // can retry instead of leaving the panel permanently complete-but-empty.
        if (!disposed) {
          setError(getApiErrorMessage(err, '处理已完成，但读取最终结果失败。正在重试。'))
        }
      } finally {
        finishing = false
      }
    }

    const poll = async () => {
      if (disposed || completed) return
      try {
        const results = await getSessionResults(sessionId)
        if (disposed || completed) return
        // Merge final records into the live map instead of replacing it, so
        // WS-only progress entries are not wiped out by a poll between stages.
        setCandidates((prev) => {
          const next = new Map(prev)
          results.results.forEach((candidate) => {
            next.set(candidate.candidate_id, toProgress(candidate))
          })
          return next
        })
        if (results.status === 'done') {
          await finish(results)
        }
      } catch (err: unknown) {
        if (!disposed && !completed && !errorShown) {
          errorShown = true
          setError(getApiErrorMessage(err, '无法读取处理进度，请检查后端服务。'))
        }
      }
    }

    const scheduleReconnect = () => {
      if (disposed || completed) return
      if (retry >= 5) {
        setConnection('failed')
        if (!errorShown) {
          errorShown = true
          setError('实时连接中断，已切换到后端结果轮询；处理仍会在后端继续。')
        }
        return
      }
      const delay = Math.min(1000 * 2 ** retry, 8000)
      retry += 1
      setConnection('reconnecting')
      reconnectTimer = window.setTimeout(connect, delay)
    }

    const handleProgress = (message: Extract<WSMessage, { type: 'progress' }>) => {
      setCandidates((prev) => {
        const next = new Map(prev)
        const existing = next.get(message.candidate_id) ?? {
          candidateId: message.candidate_id,
          fileName: message.candidate_id.slice(0, 8),
          stage: 'queued' as Stage,
          screeningOutcome: 'ranked' as const,
          graduationYearInfo: { source: 'not_applicable' as const },
          previewAvailable: false,
        }
        next.set(message.candidate_id, { ...existing, stage: message.stage })
        return next
      })
    }

    const handleResult = (message: Extract<WSMessage, { type: 'result' }>) => {
      const result = message.result
      setCandidates((prev) => {
        const next = new Map(prev)
        const existing = next.get(message.candidate_id)
        next.set(message.candidate_id, {
          candidateId: result.candidate_id,
          fileName: result.file_name,
          name: result.name,
          email: result.email,
          phone: result.phone,
          score: result.score,
          explanation: result.explanation,
          dimensionScores: result.dimension_scores,
          stage: result.stage,
          error: result.error,
          parseMethod: result.parse_method,
          screeningOutcome: result.screening_outcome,
          screeningReason: result.screening_reason,
          graduationYearInfo:
            result.graduation_year_info ?? existing?.graduationYearInfo ?? { source: 'not_applicable' },
          previewAvailable: Boolean(result.preview_available),
        })
        return next
      })
    }

    const connect = () => {
      if (disposed || completed) return
      setConnection(retry === 0 ? 'connecting' : 'reconnecting')
      try {
        ws = createWebSocket(sessionId)
      } catch {
        scheduleReconnect()
        return
      }

      ws.onopen = () => {
        if (disposed || completed) return
        setConnection('open')
        setError(null)
        void poll()
      }

      ws.onmessage = (event) => {
        if (disposed || completed) return
        try {
          const message = JSON.parse(event.data) as WSMessage
          // A real event proves the connection is useful; reset backoff here
          // rather than on open so a server that accepts then closes cannot
          // cause an endless reconnect loop with a reset retry counter.
          retry = 0
          setConnection('open')
          if (message.type === 'progress') handleProgress(message)
          else if (message.type === 'result') handleResult(message)
          else if (message.type === 'complete') void finish()
        } catch {
          setError('收到无法解析的实时进度消息。')
        }
      }

      ws.onerror = () => {
        if (disposed || completed) return
        setConnection('reconnecting')
      }

      ws.onclose = () => {
        if (disposed || completed) return
        scheduleReconnect()
      }
    }

    connect()
    pollTimer = window.setInterval(() => {
      void poll()
    }, 3000)
    void poll()

    return () => {
      disposed = true
      clearTimers()
      closeSocket()
    }
  }, [sessionId])

  const all = Array.from(candidates.values())
  const ranked = all.filter((candidate) => candidate.stage === 'done').length
  const issues = all.filter(
    (candidate) => FINAL_STAGES.includes(candidate.stage) && candidate.stage !== 'done',
  ).length
  const resolved = all.filter((candidate) => FINAL_STAGES.includes(candidate.stage)).length
  const total = totalFiles || all.length
  const resolvedProgress = total > 0 ? Math.round((resolved / total) * 100) : 0
  const stageProgress =
    total > 0
      ? Math.round(
          all.reduce((sum, candidate) => sum + STAGE_PERCENT[candidate.stage], 0) / (total * 100) * 100,
        )
      : 0
  const progress = done ? 100 : Math.max(resolvedProgress, Math.min(100, stageProgress))

  const connectionMeta = {
    connecting: { label: '正在连接实时进度…', tone: 'neutral', icon: Wifi },
    open: { label: '实时连接中', tone: 'ok', icon: Wifi },
    reconnecting: { label: '连接中断，正在重连', tone: 'warn', icon: WifiOff },
    failed: { label: '实时连接失败 · 使用结果轮询', tone: 'danger', icon: WifiOff },
  }[connection]
  const ConnectionIcon = connectionMeta.icon

  return (
    <section className="ttc-progress-panel">
      <div className="ttc-progress-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            AI SCREENING
            <span className="hero-eyebrow-line" />
            <span>LIVE PIPELINE</span>
          </div>
          <h2>{done ? '处理完成，正在加载结果…' : 'AI 正在处理简历'}</h2>
          <p>{jobRoleTitle ? `当前岗位：${jobRoleTitle}` : '简历解析、信息提取与评分正在后端执行。'}</p>
        </div>
        <span className={`ttc-connection-pill ttc-connection-${connectionMeta.tone}`}>
          <ConnectionIcon size={14} />
          {connectionMeta.label}
        </span>
      </div>

      <div className="ttc-progress-card">
        <div className="ttc-progress-top">
          <strong>{progress}%</strong>
          <span>
            {resolved} / {total} 已返回
          </span>
        </div>
        <div className="ttc-progress-bar">
          <i style={{ width: `${progress}%` }} />
        </div>
        <div className="ttc-progress-stats">
          <span>
            <b>{ranked}</b> 已排名
          </span>
          <span>
            <b>{issues}</b> 异常 / 待复核
          </span>
          <span>
            <b>{Math.max(total - resolved, 0)}</b> 处理中
          </span>
        </div>
      </div>

      {error && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <div className="ttc-live-list">
        {all.map((candidate) => (
          <article key={candidate.candidateId} className={`ttc-live-row ttc-live-${candidate.stage}`}>
            <StatusIcon stage={candidate.stage} />
            <div className="ttc-live-main">
              <div className="ttc-live-top">
                <div className="ttc-live-meta">
                  <strong>{candidate.name || candidate.fileName}</strong>
                  <span>
                    <FileText size={12} />
                    {candidate.fileName}
                  </span>
                </div>
                <div className="ttc-live-right">
                  {candidate.score != null && <span className="ttc-live-score">{candidate.score}</span>}
                  <span className={`ttc-stage-pill ttc-stage-${candidate.stage}`}>
                    {STAGE_LABEL[candidate.stage]}
                  </span>
                </div>
              </div>
              <StageBar stage={candidate.stage} />
              {(candidate.error || candidate.screeningReason) && (
                <p className="ttc-live-error">{candidate.error || candidate.screeningReason}</p>
              )}
              {candidate.stage === 'done' && candidate.explanation && candidate.explanation.length > 0 && (
                <ul className="ttc-live-explanations">
                  {candidate.explanation.slice(0, 2).map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          </article>
        ))}

        {all.length === 0 && (
          <div className="ttc-empty-state">
            <Loader2 size={22} className="animate-spin" />
            <strong>等待后端返回真实进度…</strong>
            <span>连接建立后，简历解析和 AI 评分事件会实时显示在这里。</span>
          </div>
        )}
      </div>
    </section>
  )
}
