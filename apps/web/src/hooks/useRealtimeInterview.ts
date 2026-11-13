import { useCallback, useEffect, useRef, useState } from 'react'
import {
  finishVoiceSession,
  openRealtimeRelay,
} from '../api/voice'
import { describeSocketClose } from '../api/ws'
import { MicStreamer, PcmPlayer } from '../lib/audio'

export type InterviewPhase =
  | 'idle'
  | 'connecting'
  | 'live'
  | 'ending'
  | 'ended'
  | 'error'

export interface TranscriptLine {
  id: string
  role: 'interviewer' | 'candidate' | 'system'
  text: string
  pending: boolean
}

interface RelayInfo {
  model: string
  voice: string
  max_seconds: number
}

interface UpstreamEvent {
  type?: string
  delta?: string
  transcript?: string
  item_id?: string
  response_id?: string
  message?: string
  error?: { message?: string }
  session?: { id?: string }
}

interface TurnPayload {
  index: number
  role: 'interviewer' | 'candidate' | 'system'
  text: string
}

/**
 * 通义千问实时语音会话：麦克风上行、AI 面试官播报下行、
 * 双方转写都从同一个 WebSocket 事件流里解析。
 */
export function useRealtimeInterview(sessionId: string | undefined) {
  const [phase, setPhase] = useState<InterviewPhase>('idle')
  const [error, setError] = useState('')
  const [lines, setLines] = useState<TranscriptLine[]>([])
  const [relay, setRelay] = useState<RelayInfo | null>(null)
  const [muted, setMutedState] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const socketRef = useRef<WebSocket | null>(null)
  const micRef = useRef<MicStreamer | null>(null)
  const playerRef = useRef<PcmPlayer | null>(null)
  const linesRef = useRef<TranscriptLine[]>([])
  const phaseRef = useRef<InterviewPhase>('idle')
  const timerRef = useRef<number | null>(null)

  const setPhaseSafe = useCallback((next: InterviewPhase) => {
    phaseRef.current = next
    setPhase(next)
  }, [])

  const upsertLine = useCallback(
    (id: string, role: TranscriptLine['role'], text: string, pending: boolean) => {
      setLines((current) => {
        const next = [...current]
        const index = next.findIndex((line) => line.id === id)
        if (index >= 0) {
          next[index] = { ...next[index], text, pending }
        } else {
          next.push({ id, role, text, pending })
        }
        linesRef.current = next
        return next
      })
    },
    [],
  )

  const send = useCallback((payload: unknown) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
    }
  }, [])

  const teardownAudio = useCallback(() => {
    micRef.current?.stop()
    micRef.current = null
    playerRef.current?.close()
    playerRef.current = null
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const start = useCallback(() => {
    if (!sessionId || phaseRef.current === 'connecting' || phaseRef.current === 'live') return
    setError('')
    setLines([])
    linesRef.current = []
    setElapsed(0)
    setRelay(null)
    setPhaseSafe('connecting')

    // 必须在用户点击的同一个任务里创建，否则浏览器会拦下自动播放。
    playerRef.current = new PcmPlayer()

    const socket = openRealtimeRelay(sessionId)
    socketRef.current = socket
    let mediaStarted = false

    socket.onmessage = (event) => {
      let payload: UpstreamEvent
      try {
        payload = JSON.parse(String(event.data)) as UpstreamEvent
      } catch {
        return
      }
      const type = payload.type ?? ''

      if (type === 'relay.ready') {
        const info = payload as unknown as RelayInfo & { type: string }
        setRelay({ model: info.model, voice: info.voice, max_seconds: info.max_seconds })
        setPhaseSafe('live')
        timerRef.current = window.setInterval(() => setElapsed((value) => value + 1), 1000)
        if (!mediaStarted) {
          mediaStarted = true
          const mic = new MicStreamer()
          micRef.current = mic
          mic
            .start((base64) => {
              send({ type: 'input_audio_buffer.append', audio: base64 })
            })
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : '无法开启麦克风')
            })
        }
        // 让面试官先开口。上游没有自动开场，必须显式触发一次回复。
        send({ type: 'response.create' })
        return
      }

      if (type === 'error') {
        setError(payload.error?.message ?? payload.message ?? '实时语音返回错误')
        return
      }

      switch (type) {
        case 'input_audio_buffer.speech_started':
          // 候选人插话：停掉正在播的面试官音频。
          playerRef.current?.interrupt()
          break
        case 'conversation.item.input_audio_transcription.delta': {
          const key = `candidate:${payload.item_id ?? 'current'}`
          const existing = linesRef.current.find((line) => line.id === key)
          upsertLine(key, 'candidate', (existing?.text ?? '') + (payload.delta ?? ''), true)
          break
        }
        case 'conversation.item.input_audio_transcription.completed': {
          const key = `candidate:${payload.item_id ?? 'current'}`
          const text = (payload.transcript ?? '').trim()
          if (text) upsertLine(key, 'candidate', text, false)
          break
        }
        case 'response.audio_transcript.delta':
        case 'response.text.delta': {
          const key = `interviewer:${payload.item_id ?? payload.response_id ?? 'current'}`
          const existing = linesRef.current.find((line) => line.id === key)
          upsertLine(key, 'interviewer', (existing?.text ?? '') + (payload.delta ?? ''), true)
          break
        }
        case 'response.audio_transcript.done':
        case 'response.text.done': {
          const key = `interviewer:${payload.item_id ?? payload.response_id ?? 'current'}`
          const text = (payload.transcript ?? '').trim()
          if (text) upsertLine(key, 'interviewer', text, false)
          break
        }
        case 'response.audio.delta':
          if (payload.delta) playerRef.current?.enqueue(payload.delta)
          break
        case 'response.done':
          setLines((current) => {
            const next = current.map((line) =>
              line.role === 'interviewer' && line.pending
                ? { ...line, pending: false }
                : line,
            )
            linesRef.current = next
            return next
          })
          break
        default:
          break
      }
    }

    socket.onerror = () => {
      if (phaseRef.current !== 'ended') setError('实时语音连接出错')
    }

    socket.onclose = (event) => {
      teardownAudio()
      socketRef.current = null
      if (phaseRef.current === 'ending' || phaseRef.current === 'ended') {
        setPhaseSafe('ended')
        return
      }
      if (event.code === 1000) {
        setPhaseSafe('ended')
      } else {
        setError(describeSocketClose(event.code))
        setPhaseSafe('error')
      }
    }
  }, [sessionId, send, setPhaseSafe, teardownAudio, upsertLine])

  const setMuted = useCallback((next: boolean) => {
    setMutedState(next)
    micRef.current?.setMuted(next)
  }, [])

  const stop = useCallback(
    async (reason: 'completed' | 'timeout' | 'candidate_end' = 'completed') => {
      if (!sessionId || phaseRef.current === 'ending' || phaseRef.current === 'ended') return
      setPhaseSafe('ending')
      micRef.current?.stop()
      micRef.current = null
      playerRef.current?.interrupt()
      const turns: TurnPayload[] = linesRef.current
        .filter((line) => line.role !== 'system' && line.text.trim().length > 0)
        .map((line, index) => ({ index, role: line.role, text: line.text.trim() }))
      try {
        await finishVoiceSession(sessionId, { reason, turns })
      } catch (err) {
        setError(err instanceof Error ? err.message : '结束会话失败')
      }
      socketRef.current?.close(1000)
      socketRef.current = null
      teardownAudio()
      setPhaseSafe('ended')
    },
    [sessionId, setPhaseSafe, teardownAudio],
  )

  useEffect(() => {
    return () => {
      teardownAudio()
      socketRef.current?.close(1000)
      socketRef.current = null
    }
  }, [teardownAudio])

  return { phase, error, lines, relay, muted, elapsed, start, stop, setMuted }
}
