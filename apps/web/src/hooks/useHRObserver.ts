import { useCallback, useEffect, useRef, useState } from 'react'
import { describeSocketClose, openAuthedSocket } from '../api/ws'
import { MicStreamer, PcmPlayer } from '../lib/audio'

export type HRObserverPhase =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'closed'
  | 'error'

export interface HRObserverLine {
  id: string
  role: 'interviewer' | 'candidate' | 'hr' | 'system'
  text: string
  pending: boolean
}

interface ObserverEvent {
  type?: string
  delta?: string
  transcript?: string
  item_id?: string
  response_id?: string
  message?: string
  error?: { message?: string }
  model?: string
  voice?: string
  max_seconds?: number
  observer?: boolean
  ai_active?: boolean
  hr_control?: boolean
  hr_mic_open?: boolean
  interview_paused?: boolean
  speaker?: 'candidate' | 'hr'
  audio?: string
  role?: 'candidate' | 'hr'
  sample_rate?: number
  reason?: string
}

export function useHRObserver(sessionId: string | undefined) {
  const [phase, setPhase] = useState<HRObserverPhase>('idle')
  const [error, setError] = useState('')
  const [lines, setLines] = useState<HRObserverLine[]>([])
  const [model, setModel] = useState('')
  const [aiActive, setAiActive] = useState(true)
  const [hrControl, setHrControl] = useState(false)
  const [micOpen, setMicOpen] = useState(false)
  const [interviewPaused, setInterviewPaused] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const playerRef = useRef<PcmPlayer | null>(null)
  const micRef = useRef<MicStreamer | null>(null)
  const linesRef = useRef<HRObserverLine[]>([])
  const closingRef = useRef(false)

  const upsertLine = useCallback(
    (id: string, role: HRObserverLine['role'], text: string, pending: boolean) => {
      setLines((current) => {
        const next = [...current]
        const index = next.findIndex((line) => line.id === id)
        if (index >= 0) next[index] = { id, role, text, pending }
        else next.push({ id, role, text, pending })
        linesRef.current = next
        return next
      })
    },
    [],
  )

  const send = useCallback((payload: unknown) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload))
  }, [])

  const start = useCallback(() => {
    if (!sessionId || phase === 'connecting' || phase === 'listening') return
    closingRef.current = false
    setError('')
    setLines([])
    linesRef.current = []
    setInterviewPaused(false)
    setPhase('connecting')
    playerRef.current = new PcmPlayer()

    const socket = openAuthedSocket(`/voice-sessions/${sessionId}/observe`)
    socketRef.current = socket
    socket.onmessage = (event) => {
      let payload: ObserverEvent
      try {
        payload = JSON.parse(String(event.data)) as ObserverEvent
      } catch {
        return
      }
      const type = payload.type ?? ''
      if (type === 'relay.ready') {
        setModel(payload.model ?? '')
        setPhase('listening')
        return
      }
      if (type === 'error') {
        setError(payload.error?.message ?? payload.message ?? 'HR 旁听连接返回错误')
        return
      }
      if (type === 'control.state') {
        setAiActive(payload.ai_active ?? true)
        setHrControl(payload.hr_control ?? false)
        setMicOpen(payload.hr_mic_open ?? false)
        setInterviewPaused(payload.interview_paused ?? false)
        if (payload.ai_active === false || payload.hr_control === true) {
          playerRef.current?.interrupt()
        }
        return
      }
      if (type === 'session.terminated') {
        closingRef.current = true
        return
      }

      switch (type) {
        case 'conversation.item.input_audio_transcription.delta': {
          const role = payload.speaker === 'hr' ? 'hr' : 'candidate'
          const key = `${role}:${payload.item_id ?? 'current'}`
          const existing = linesRef.current.find((line) => line.id === key)
          upsertLine(key, role, (existing?.text ?? '') + (payload.delta ?? ''), true)
          break
        }
        case 'conversation.item.input_audio_transcription.completed': {
          const role = payload.speaker === 'hr' ? 'hr' : 'candidate'
          const key = `${role}:${payload.item_id ?? 'current'}`
          const text = (payload.transcript ?? '').trim()
          if (text) upsertLine(key, role, text, false)
          break
        }
        case 'response.audio_transcript.delta':
        case 'response.text.delta': {
          const key = `interviewer:${payload.item_id ?? payload.response_id ?? 'current'}`
          const existing = linesRef.current.find((line) => line.id === key)
          upsertLine(
            key,
            'interviewer',
            (existing?.text ?? '') + (payload.delta ?? ''),
            true,
          )
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
        case 'participant.audio':
          if (payload.audio && payload.role === 'candidate') {
            playerRef.current?.enqueue(payload.audio, payload.sample_rate ?? 16000)
          }
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
      if (!closingRef.current) setError('HR 旁听连接出错')
    }
    socket.onclose = (event) => {
      socketRef.current = null
      micRef.current?.stop()
      micRef.current = null
      playerRef.current?.close()
      playerRef.current = null
      if (closingRef.current || event.code === 1000) setPhase('closed')
      else {
        setError(describeSocketClose(event.code))
        setPhase('error')
      }
    }
  }, [phase, sessionId, upsertLine])

  const takeControl = useCallback(() => {
    send({ type: 'control.take' })
  }, [send])

  const releaseControl = useCallback(() => {
    micRef.current?.stop()
    micRef.current = null
    setMicOpen(false)
    send({ type: 'hr_audio.commit' })
    send({ type: 'control.release' })
  }, [send])

  const toggleMic = useCallback(async () => {
    if (micOpen) {
      micRef.current?.stop()
      micRef.current = null
      setMicOpen(false)
      send({ type: 'hr_audio.commit' })
      return
    }
    const mic = new MicStreamer()
    try {
      await mic.start((base64) => {
        send({ type: 'hr_audio.append', audio: base64 })
      })
      micRef.current = mic
      setMicOpen(true)
      send({ type: 'hr_audio.start' })
    } catch (err) {
      mic.stop()
      setError(err instanceof Error ? err.message : '无法打开 HR 麦克风')
    }
  }, [micOpen, send])

  const stop = useCallback(() => {
    closingRef.current = true
    micRef.current?.stop()
    micRef.current = null
    send({ type: 'hr_audio.commit' })
    send({ type: 'control.release' })
    socketRef.current?.close(1000)
    socketRef.current = null
    playerRef.current?.close()
    playerRef.current = null
    setMicOpen(false)
    setPhase('closed')
  }, [send])

  useEffect(() => () => {
    closingRef.current = true
    micRef.current?.stop()
    micRef.current = null
    playerRef.current?.close()
    playerRef.current = null
    socketRef.current?.close(1000)
    socketRef.current = null
  }, [])

  return {
    phase,
    error,
    lines,
    model,
    aiActive,
    hrControl,
    micOpen,
    interviewPaused,
    start,
    stop,
    takeControl,
    releaseControl,
    toggleMic,
  }
}
