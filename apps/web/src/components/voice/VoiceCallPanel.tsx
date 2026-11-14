import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  AudioLines,
  Bot,
  CheckCircle2,
  Clock,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  Volume2,
  Waves,
} from 'lucide-react'
import { openVoiceRealtimeSocket } from '../../api/websocket'
import { finishVoiceSession, getVoiceReport } from '../../api/voice'
import type { CallReport, VoiceStatus, VoiceTurnInput } from '../../types'
import { VOICE_STATUS_LABEL } from '../../types'
import { usePrefersReducedMotion, VoiceWaveform } from './VoiceWaveform'

interface Props {
  sessionId: string
  maxSeconds: number
  initialStatus?: VoiceStatus
  initialReport?: CallReport | null
  onReport?: (report: CallReport) => void
}

type CallState = 'idle' | 'connecting' | 'live' | 'ending' | 'ended' | 'error'
type MicState = 'idle' | 'requesting' | 'active' | 'denied' | 'unsupported' | 'error'
type TurnPhase = 'idle' | 'listening' | 'waiting' | 'speaking'

interface TranscriptEntry {
  id: string
  role: 'candidate' | 'interviewer' | 'system'
  text: string
  at: string
}

const ROLE_META: Record<
  TranscriptEntry['role'],
  { label: string; icon: typeof UserRound }
> = {
  candidate: { label: '候选人', icon: UserRound },
  interviewer: { label: 'AI 面试官', icon: Bot },
  system: { label: '系统', icon: AudioLines },
}

const CALL_STATE_META: Record<
  CallState,
  { label: string; tone: 'muted' | 'ok' | 'warn' | 'danger' }
> = {
  idle: { label: '未开始', tone: 'muted' },
  connecting: { label: '正在连接 Qwen…', tone: 'warn' },
  live: { label: '通话中', tone: 'ok' },
  ending: { label: '正在挂断…', tone: 'warn' },
  ended: { label: '已结束', tone: 'muted' },
  error: { label: '连接异常', tone: 'danger' },
}

const MIC_META: Record<
  MicState,
  { label: string; tone: 'muted' | 'ok' | 'warn' | 'danger' }
> = {
  idle: { label: '未开启', tone: 'muted' },
  requesting: { label: '等待麦克风授权', tone: 'warn' },
  active: { label: '麦克风采集中', tone: 'ok' },
  denied: { label: '麦克风权限被拒绝', tone: 'danger' },
  unsupported: { label: '浏览器不支持麦克风', tone: 'danger' },
  error: { label: '麦克风采集失败', tone: 'danger' },
}

const INPUT_SAMPLE_RATE = 16_000
const OUTPUT_SAMPLE_RATE = 24_000
const CHUNK_SAMPLES = 1_600 // 100 ms @ 16 kHz
const SPEECH_RMS_THRESHOLD = 0.008
const SPEECH_START_FRAMES = 2
// server_vad 约 800ms 静音断句；客户端兜底稍晚触发，避免与自动断句并发。
const ENDPOINT_SILENCE_MS = 1_100

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunk = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk))
  }
  return window.btoa(binary)
}

function base64ToBytes(value: string): Uint8Array | null {
  try {
    const binary = window.atob(value)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    return bytes
  } catch {
    return null
  }
}

/** Float32 [-1, 1] 线性重采样到 16 kHz，再转 Int16 PCM。 */
function downsampleToPcm16(input: Float32Array, inputRate: number): Int16Array {
  if (!input.length) return new Int16Array(0)
  const ratio = inputRate / INPUT_SAMPLE_RATE
  const outputLength = Math.max(1, Math.floor(input.length / ratio))
  const output = new Int16Array(outputLength)
  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio
    const left = Math.floor(position)
    const right = Math.min(input.length - 1, left + 1)
    const fraction = position - left
    const sample = input[left] * (1 - fraction) + input[right] * fraction
    const clamped = Math.max(-1, Math.min(1, sample))
    output[index] = clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff)
  }
  return output
}

function computeRms(samples: Float32Array): number {
  if (!samples.length) return 0
  let sum = 0
  for (let index = 0; index < samples.length; index += 1) {
    sum += samples[index] * samples[index]
  }
  return Math.sqrt(sum / samples.length)
}

function describeMicrophoneError(error: unknown): { state: MicState; message: string } {
  const name = asString(asRecord(error)?.name)
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return {
        state: 'denied',
        message:
          '麦克风权限被拒绝。请在浏览器地址栏的站点设置中允许麦克风，然后点击“重试麦克风”。',
      }
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return {
        state: 'error',
        message: '未检测到麦克风设备。请连接输入设备并检查系统声音设置后重试。',
      }
    case 'NotReadableError':
    case 'TrackStartError':
      return {
        state: 'error',
        message: '麦克风无法读取，可能被其他应用占用。请关闭占用麦克风的程序后重试。',
      }
    case 'SecurityError':
      return {
        state: 'denied',
        message: '浏览器因安全原因阻止麦克风。请通过 HTTPS 或 localhost 打开本页面。',
      }
    default:
      return {
        state: 'error',
        message: `麦克风启动失败：${error instanceof Error ? error.message : '未知错误'}`,
      }
  }
}

function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(
    seconds % 60,
  ).padStart(2, '0')}`
}

export function VoiceCallPanel({
  sessionId,
  maxSeconds,
  initialStatus = 'created',
  initialReport = null,
  onReport,
}: Props) {
  const reducedMotion = usePrefersReducedMotion()

  const [callState, setCallState] = useState<CallState>(
    initialStatus === 'created' ? 'idle' : 'ended',
  )
  const [micState, setMicState] = useState<MicState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [model, setModel] = useState<string | null>(null)
  const [voice, setVoice] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [inputLevel, setInputLevel] = useState(0)
  const [outputLevel, setOutputLevel] = useState(0)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)
  const [turns, setTurns] = useState<TranscriptEntry[]>([])
  const [userPartial, setUserPartial] = useState('')
  const [assistantPartial, setAssistantPartial] = useState('')
  const [assistantSpeaking, setAssistantSpeaking] = useState(false)
  const [turnPhase, setTurnPhase] = useState<TurnPhase>('idle')
  const [hasSpeech, setHasSpeech] = useState(false)
  const [report, setReport] = useState<CallReport | null>(initialReport)

  const socketRef = useRef<WebSocket | null>(null)
  const callStateRef = useRef<CallState>(callState)
  const relayReadyRef = useRef(false)
  const streamRef = useRef<MediaStream | null>(null)
  const micStartingRef = useRef(false)
  const captureContextRef = useRef<AudioContext | null>(null)
  const captureSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const muteGainRef = useRef<GainNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const playbackContextRef = useRef<AudioContext | null>(null)
  const nextPlayTimeRef = useRef(0)
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set())
  const pendingSamplesRef = useRef<number[]>([])
  const lastInputLevelRef = useRef(0)
  const lastOutputLevelRef = useRef(0)
  const turnsRef = useRef<TranscriptEntry[]>([])
  const turnSeqRef = useRef(0)
  const userPartialRef = useRef('')
  const assistantDraftRef = useRef('')
  const startedAtRef = useRef<number | null>(null)
  const responseActiveRef = useRef(false)
  const hasSpeechRef = useRef(false)
  const speechFramesRef = useRef(0)
  const silenceSinceRef = useRef(0)
  const waitingResponseRef = useRef(false)
  const lastCommitAtRef = useRef(0)
  const responseWatchdogRef = useRef<number | undefined>(undefined)
  const hangupReasonRef = useRef<'candidate_end' | 'timeout'>('candidate_end')
  const hangUpRef = useRef<() => void>(() => {})
  const unmountedRef = useRef(false)

  const setCallStateSafe = useCallback((next: CallState) => {
    callStateRef.current = next
    setCallState(next)
  }, [])

  const pushTurn = useCallback((role: TranscriptEntry['role'], text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    turnSeqRef.current += 1
    const entry: TranscriptEntry = {
      id: `${role}-${Date.now()}-${turnSeqRef.current}`,
      role,
      text: trimmed,
      at: new Date().toISOString(),
    }
    turnsRef.current = [...turnsRef.current, entry]
    setTurns(turnsRef.current)
  }, [])

  const clearPartial = useCallback(() => {
    userPartialRef.current = ''
    setUserPartial('')
  }, [])

  const flushAssistantDraft = useCallback(
    (finalText?: string) => {
      const text = (finalText ?? assistantDraftRef.current).trim()
      if (text) pushTurn('interviewer', text)
      assistantDraftRef.current = ''
      setAssistantPartial('')
    },
    [pushTurn],
  )

  const sendJson = useCallback((payload: Record<string, unknown>): boolean => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    try {
      socket.send(JSON.stringify(payload))
      return true
    } catch {
      return false
    }
  }, [])

  const clearResponseWatchdog = useCallback(() => {
    if (responseWatchdogRef.current !== undefined) {
      window.clearTimeout(responseWatchdogRef.current)
      responseWatchdogRef.current = undefined
    }
  }, [])

  const armResponseWatchdog = useCallback(() => {
    clearResponseWatchdog()
    responseWatchdogRef.current = window.setTimeout(() => {
      responseWatchdogRef.current = undefined
      if (
        callStateRef.current === 'live' &&
        waitingResponseRef.current &&
        !responseActiveRef.current
      ) {
        // 服务端已完成断句但未自动创建 response 时的兜底。
        sendJson({ type: 'response.create' })
      }
    }, 2_500)
  }, [clearResponseWatchdog, sendJson])

  const commitAndRespond = useCallback(
    (origin: 'auto' | 'manual') => {
      if (callStateRef.current !== 'live') return
      if (responseActiveRef.current || waitingResponseRef.current) return
      if (!hasSpeechRef.current) {
        if (origin === 'manual') {
          setNotice('还没有检测到语音，请先说话再点击“结束发言并发送”。')
        }
        return
      }
      const now = Date.now()
      if (now - lastCommitAtRef.current < 600) return
      lastCommitAtRef.current = now
      if (!sendJson({ type: 'input_audio_buffer.commit' })) return
      sendJson({ type: 'response.create' })
      hasSpeechRef.current = false
      setHasSpeech(false)
      speechFramesRef.current = 0
      silenceSinceRef.current = 0
      waitingResponseRef.current = true
      setTurnPhase('waiting')
      armResponseWatchdog()
    },
    [armResponseWatchdog, sendJson],
  )

  const stopPlayback = useCallback(() => {
    for (const source of activeSourcesRef.current) {
      try {
        source.stop()
      } catch {
        // already stopped
      }
    }
    activeSourcesRef.current.clear()
    nextPlayTimeRef.current = 0
    setOutputLevel(0)
    lastOutputLevelRef.current = 0
    setAssistantSpeaking(false)
  }, [])

  const playPcm = useCallback(
    (base64: string) => {
      const bytes = base64ToBytes(base64)
      if (!bytes || bytes.length < 2) return
      const usable = bytes.length - (bytes.length % 2)
      const view = new DataView(bytes.buffer, bytes.byteOffset, usable)
      const sampleCount = usable / 2
      const floats = new Float32Array(sampleCount)
      let sum = 0
      for (let index = 0; index < sampleCount; index += 1) {
        const value = view.getInt16(index * 2, true) / 0x8000
        floats[index] = value
        sum += value * value
      }

      const now = performance.now()
      if (now - lastOutputLevelRef.current > 80) {
        lastOutputLevelRef.current = now
        setOutputLevel(Math.min(1, Math.sqrt(sum / Math.max(1, sampleCount)) * 4))
      }

      let context = playbackContextRef.current
      if (!context) {
        try {
          context = new AudioContext()
          playbackContextRef.current = context
          nextPlayTimeRef.current = 0
        } catch {
          return
        }
      }
      if (context.state === 'suspended') void context.resume().catch(() => undefined)

      const buffer = context.createBuffer(1, sampleCount, OUTPUT_SAMPLE_RATE)
      buffer.copyToChannel(floats, 0)
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(context.destination)
      const startAt = Math.max(context.currentTime + 0.02, nextPlayTimeRef.current)
      nextPlayTimeRef.current = startAt + buffer.duration
      activeSourcesRef.current.add(source)
      source.onended = () => {
        activeSourcesRef.current.delete(source)
        if (!activeSourcesRef.current.size) setAssistantSpeaking(false)
      }
      setAssistantSpeaking(true)
      try {
        source.start(startAt)
      } catch {
        activeSourcesRef.current.delete(source)
      }
    },
    [],
  )

  const stopMicrophone = useCallback(() => {
    const processor = processorRef.current
    if (processor) {
      processor.onaudioprocess = null
      try {
        processor.disconnect()
      } catch {
        // already disconnected
      }
      processorRef.current = null
    }
    if (muteGainRef.current) {
      try {
        muteGainRef.current.disconnect()
      } catch {
        // already disconnected
      }
      muteGainRef.current = null
    }
    if (captureSourceRef.current) {
      try {
        captureSourceRef.current.disconnect()
      } catch {
        // already disconnected
      }
      captureSourceRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (captureContextRef.current) {
      const context = captureContextRef.current
      captureContextRef.current = null
      if (context.state !== 'closed') void context.close().catch(() => undefined)
    }
    analyserRef.current = null
    setAnalyser(null)
    pendingSamplesRef.current = []
    setInputLevel(0)
    lastInputLevelRef.current = 0
    setMicState((current) => (current === 'active' ? 'idle' : current))
  }, [])

  const handleAudioProcess = useCallback((event: AudioProcessingEvent) => {
    if (unmountedRef.current) return
    const input = event.inputBuffer.getChannelData(0)
    const rms = computeRms(input)
    const now = performance.now()
    if (now - lastInputLevelRef.current > 80) {
      lastInputLevelRef.current = now
      setInputLevel(Math.min(1, rms * 8))
    }
    if (!relayReadyRef.current) return
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    const context = captureContextRef.current
    if (!context) return
    const pcm = downsampleToPcm16(input, context.sampleRate)
    const pending = pendingSamplesRef.current
    for (let index = 0; index < pcm.length; index += 1) pending.push(pcm[index])
    while (pending.length >= CHUNK_SAMPLES) {
      const chunk = Int16Array.from(pending.splice(0, CHUNK_SAMPLES))
      const bytes = new Uint8Array(chunk.buffer)
      sendJson({ type: 'input_audio_buffer.append', audio: bytesToBase64(bytes) })
    }

    // 客户端兜底断句。模型默认 server_vad 正常时会在 ~800ms 静音后自行
    // commit + response；这里晚 300ms 才动作，避免和自动断句并发。
    if (responseActiveRef.current || waitingResponseRef.current) {
      speechFramesRef.current = 0
      silenceSinceRef.current = 0
      return
    }
    if (rms >= SPEECH_RMS_THRESHOLD) {
      speechFramesRef.current += 1
      silenceSinceRef.current = 0
      if (speechFramesRef.current >= SPEECH_START_FRAMES && !hasSpeechRef.current) {
        hasSpeechRef.current = true
        setHasSpeech(true)
        setTurnPhase('listening')
      }
    } else {
      speechFramesRef.current = 0
      if (hasSpeechRef.current) {
        if (!silenceSinceRef.current) {
          silenceSinceRef.current = now
        } else if (now - silenceSinceRef.current >= ENDPOINT_SILENCE_MS) {
          commitAndRespond('auto')
        }
      }
    }
  }, [commitAndRespond, sendJson])

  const startMicrophone = useCallback(async () => {
    if (streamRef.current || micStartingRef.current) return
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicState('unsupported')
      setError('当前浏览器不支持麦克风采集。请使用最新版 Chrome / Edge，并通过 localhost 或 HTTPS 访问。')
      return
    }
    micStartingRef.current = true
    setMicState('requesting')
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      if (
        unmountedRef.current ||
        (callStateRef.current !== 'connecting' && callStateRef.current !== 'live')
      ) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      const context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const node = context.createAnalyser()
      node.fftSize = 2048
      node.smoothingTimeConstant = 0.82
      source.connect(node)

      const processor = context.createScriptProcessor(4096, 1, 1)
      processor.onaudioprocess = handleAudioProcess
      const mute = context.createGain()
      mute.gain.value = 0
      source.connect(processor)
      processor.connect(mute)
      mute.connect(context.destination)

      streamRef.current = stream
      captureContextRef.current = context
      captureSourceRef.current = source
      processorRef.current = processor
      muteGainRef.current = mute
      analyserRef.current = node
      setAnalyser(node)
      setMicState('active')
      await context.resume().catch(() => undefined)
    } catch (micError) {
      const info = describeMicrophoneError(micError)
      setMicState(info.state)
      setError(info.message)
    } finally {
      micStartingRef.current = false
    }
  }, [handleAudioProcess])

  const handleUpstreamError = useCallback((message: string) => {
    setError(message)
  }, [])

  const handleMessage = useCallback(
    (raw: string) => {
      let event: Record<string, unknown>
      try {
        event = JSON.parse(raw) as Record<string, unknown>
      } catch {
        setError('收到无法解析的实时语音消息。')
        return
      }
      const type = asString(event.type)

      if (type === 'relay.ready') {
        if (callStateRef.current !== 'connecting') return
        relayReadyRef.current = true
        setModel(asString(event.model) || null)
        setVoice(asString(event.voice) || null)
        setCallStateSafe('live')
        setTurnPhase('listening')
        startedAtRef.current = Date.now()
        setElapsed(0)
        void startMicrophone()
        return
      }

      if (type === 'session.created' || type === 'session.updated') {
        const session = asRecord(event.session)
        if (session) {
          setModel(asString(session.model) || null)
          setVoice(asString(session.voice) || null)
        }
        return
      }

      if (type === 'response.created') {
        if (assistantDraftRef.current.trim()) flushAssistantDraft()
        responseActiveRef.current = true
        waitingResponseRef.current = false
        clearResponseWatchdog()
        setTurnPhase('speaking')
        setAssistantSpeaking(true)
        return
      }

      if (type === 'response.audio.delta') {
        const delta = asString(event.delta)
        if (delta) playPcm(delta)
        return
      }

      if (type === 'response.audio_transcript.delta') {
        const delta = asString(event.delta)
        if (delta) {
          assistantDraftRef.current += delta
          setAssistantPartial(assistantDraftRef.current)
        }
        return
      }

      if (type === 'response.audio_transcript.done') {
        flushAssistantDraft(asString(event.transcript))
        return
      }

      if (type === 'response.audio.done') {
        setAssistantSpeaking(false)
        return
      }

      if (type === 'response.done') {
        responseActiveRef.current = false
        waitingResponseRef.current = false
        clearResponseWatchdog()
        // transcript.done 通常在 response.done 之前到达；这里只作为兜底，
        // 避免同一条助手回复被记录两次。
        flushAssistantDraft()
        setAssistantSpeaking(false)
        setTurnPhase('listening')
        speechFramesRef.current = 0
        silenceSinceRef.current = 0
        return
      }

      if (type === 'conversation.item.input_audio_transcription.delta') {
        // DashScope 的回包把稳定前缀放在 text、临时后缀放在 stash，
        // 不是 OpenAI 的纯增量 delta。
        const stable = asString(event.text)
        const stash = asString(event.stash)
        const combined = `${stable}${stash}`
        if (combined) {
          userPartialRef.current = combined
          setUserPartial(combined)
        }
        return
      }

      if (type === 'conversation.item.input_audio_transcription.completed') {
        const transcript = asString(event.transcript) || userPartialRef.current
        pushTurn('candidate', transcript)
        clearPartial()
        if (!responseActiveRef.current) setTurnPhase('waiting')
        return
      }

      if (type === 'conversation.item.input_audio_transcription.failed') {
        setError('候选人语音转写失败，请继续说或重新开始会话。')
        clearPartial()
        return
      }

      if (type === 'input_audio_buffer.speech_started') {
        // 服务端 VAD 检测到用户开口。若是插话，停止并取消助手回复。
        // 不从客户端 clear 缓冲区：这里已经包含用户刚开始说的话，
        // 清掉会丢掉插话开头；由服务端把新语音切成新的 item。
        hasSpeechRef.current = true
        setHasSpeech(true)
        waitingResponseRef.current = false
        clearResponseWatchdog()
        speechFramesRef.current = 0
        silenceSinceRef.current = 0
        stopPlayback()
        if (responseActiveRef.current) {
          sendJson({ type: 'response.cancel' })
          // 清掉可能混入助手回声的未提交音频，再让服务端从新的 item 继续识别。
          sendJson({ type: 'input_audio_buffer.clear' })
          responseActiveRef.current = false
        }
        setTurnPhase('listening')
        return
      }

      if (type === 'input_audio_buffer.speech_stopped') {
        silenceSinceRef.current = performance.now()
        return
      }

      if (type === 'input_audio_buffer.committed') {
        // 服务端已自动断句；不再由客户端 commit，避免重复请求。
        if (responseActiveRef.current) return
        hasSpeechRef.current = false
        setHasSpeech(false)
        speechFramesRef.current = 0
        silenceSinceRef.current = 0
        waitingResponseRef.current = true
        setTurnPhase('waiting')
        armResponseWatchdog()
        return
      }

      if (type === 'error') {
        const detail = asRecord(event.error)
        const message =
          asString(detail?.message) || asString(event.message) || '实时语音上游返回错误。'
        if (
          /no active response|cannot cancel|does not have an active response|buffer too small|no audio|already committed/i.test(
            message,
          )
        ) {
          // commit/response 竞态属于可恢复噪音：回到聆听态，继续下一轮。
          waitingResponseRef.current = false
          clearResponseWatchdog()
          if (callStateRef.current === 'live') setTurnPhase('listening')
          return
        }
        waitingResponseRef.current = false
        clearResponseWatchdog()
        handleUpstreamError(message)
        return
      }

      if (type === 'relay.ready') return
      if (type.startsWith('relay.')) return
    },
    [
      armResponseWatchdog,
      clearPartial,
      clearResponseWatchdog,
      flushAssistantDraft,
      handleUpstreamError,
      playPcm,
      pushTurn,
      sendJson,
      setCallStateSafe,
      startMicrophone,
      stopPlayback,
    ],
  )

  const connect = useCallback(() => {
    if (socketRef.current) return
    setError(null)
    setNotice(null)
    setReport(null)
    hangupReasonRef.current = 'candidate_end'
    clearResponseWatchdog()
    relayReadyRef.current = false
    responseActiveRef.current = false
    setModel(null)
    setVoice(null)
    setAssistantSpeaking(false)
    setTurnPhase('idle')
    setHasSpeech(false)
    hasSpeechRef.current = false
    waitingResponseRef.current = false
    speechFramesRef.current = 0
    silenceSinceRef.current = 0
    lastCommitAtRef.current = 0
    setInputLevel(0)
    setOutputLevel(0)
    setTurns([])
    turnsRef.current = []
    turnSeqRef.current = 0
    clearPartial()
    assistantDraftRef.current = ''
    setAssistantPartial('')
    setCallStateSafe('connecting')
    startedAtRef.current = null
    setElapsed(0)

    // 在点击手势内创建播放上下文，尽量满足浏览器自动播放策略。
    try {
      if (!playbackContextRef.current) {
        playbackContextRef.current = new AudioContext()
      }
      void playbackContextRef.current.resume().catch(() => undefined)
    } catch {
      setError('浏览器无法初始化音频播放，请检查站点声音权限。')
    }

    // 麦克风在 relay.ready 后再启动：避免握手期间采集的语音被丢弃，
    // 也让用户在页面显示“通话中/正在聆听”后才知道可以开口。
    const socket = openVoiceRealtimeSocket(sessionId)
    socketRef.current = socket
    socket.onmessage = (message) => {
      if (typeof message.data === 'string') handleMessage(message.data)
    }
    socket.onerror = () => {
      waitingResponseRef.current = false
      setTurnPhase('idle')
      setError('实时语音连接失败。请确认 Vite 的 /api 代理已开启 ws，或网络可访问后端。')
      setCallStateSafe('error')
    }
    socket.onclose = (event) => {
      socketRef.current = null
      relayReadyRef.current = false
      waitingResponseRef.current = false
      clearResponseWatchdog()
      setTurnPhase('idle')
      stopMicrophone()
      stopPlayback()
      if (callStateRef.current === 'ending' || callStateRef.current === 'ended') {
        return
      }
      if (event.code === 4401 || event.code === 4403 || event.code === 4404) {
        setError(`实时语音鉴权失败（WS ${event.code}）。请重新登录后再试。`)
      } else if (event.code === 4409) {
        setError('该会话已被使用或已结束，请新建一个语音会话。')
      } else {
        setError(`实时语音连接已断开（WS ${event.code || 'closed'}）。`)
      }
      setCallStateSafe('error')
    }
  }, [
    clearPartial,
    clearResponseWatchdog,
    handleMessage,
    sessionId,
    setCallStateSafe,
    startMicrophone,
    stopMicrophone,
    stopPlayback,
  ])

  const hangUp = useCallback(() => {
    if (callStateRef.current !== 'live' && callStateRef.current !== 'connecting') return
    setCallStateSafe('ending')
    setTurnPhase('idle')
    clearResponseWatchdog()
    hasSpeechRef.current = false
    waitingResponseRef.current = false
    stopMicrophone()
    stopPlayback()
    relayReadyRef.current = false

    const finalTurns = [...turnsRef.current]
    if (userPartialRef.current.trim()) {
      finalTurns.push({
        id: `candidate-final-${Date.now()}`,
        role: 'candidate',
        text: userPartialRef.current.trim(),
        at: new Date().toISOString(),
      })
    }
    if (assistantDraftRef.current.trim()) {
      finalTurns.push({
        id: `interviewer-final-${Date.now()}`,
        role: 'interviewer',
        text: assistantDraftRef.current.trim(),
        at: new Date().toISOString(),
      })
    }
    const payloadTurns: VoiceTurnInput[] = finalTurns.map((turn, index) => ({
      index,
      role: turn.role,
      text: turn.text,
    }))

    const socket = socketRef.current
    socketRef.current = null
    if (socket) {
      try {
        socket.close(1000, 'candidate_end')
      } catch {
        // already closed
      }
    }

    void (async () => {
      try {
        const result = await finishVoiceSession(sessionId, {
          reason: hangupReasonRef.current,
          turns: payloadTurns,
        })
        const nextReport = await getVoiceReport(sessionId)
        if (unmountedRef.current) return
        setReport(nextReport)
        setNotice(`通话报告已生成（${result.status}）。`)
        onReport?.(nextReport)
      } catch (finishError) {
        if (unmountedRef.current) return
        setError(
          `挂断成功，但生成报告失败：${
            finishError instanceof Error ? finishError.message : '未知错误'
          }`,
        )
      } finally {
        if (!unmountedRef.current) setCallStateSafe('ended')
      }
    })()
  }, [
    clearResponseWatchdog,
    onReport,
    sessionId,
    setCallStateSafe,
    stopMicrophone,
    stopPlayback,
  ])
  hangUpRef.current = hangUp

  useEffect(() => {
    if (initialReport) {
      setReport((current) => current ?? initialReport)
    }
  }, [initialReport])

  useEffect(() => {
    unmountedRef.current = false
    return () => {
      unmountedRef.current = true
      relayReadyRef.current = false
      clearResponseWatchdog()
      if (socketRef.current) {
        try {
          socketRef.current.close(1000, 'unmount')
        } catch {
          // already closed
        }
        socketRef.current = null
      }
      stopMicrophone()
      stopPlayback()
      if (playbackContextRef.current) {
        const context = playbackContextRef.current
        playbackContextRef.current = null
        if (context.state !== 'closed') void context.close().catch(() => undefined)
      }
    }
  }, [clearResponseWatchdog, stopMicrophone, stopPlayback])

  useEffect(() => {
    if (callState !== 'live') return
    const timer = window.setInterval(() => {
      if (!startedAtRef.current) return
      const seconds = (Date.now() - startedAtRef.current) / 1000
      setElapsed(seconds)
      if (seconds >= maxSeconds) {
        setNotice('已达到本次会话的最长时长，正在自动挂断并生成报告。')
        hangupReasonRef.current = 'timeout'
        hangUpRef.current()
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [callState, maxSeconds])

  const transcriptRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [turns, userPartial, assistantPartial])

  const stateMeta = CALL_STATE_META[callState]
  const micMeta = MIC_META[micState]
  const canStart = callState === 'idle' || callState === 'error'
  const canHangUp = callState === 'live' || callState === 'connecting'
  const phaseLabel =
    assistantSpeaking || turnPhase === 'speaking'
      ? '模型正在回复'
      : turnPhase === 'waiting'
        ? '已发送 · 等待模型回复'
        : hasSpeech
          ? '检测到语音 · 停顿后自动发送'
          : turnPhase === 'listening'
            ? '正在聆听'
            : '未开始'

  const reportSummary = asRecord(report?.summary)
  const reportLimitations = Array.isArray(reportSummary?.limitations)
    ? reportSummary.limitations.filter((item): item is string => typeof item === 'string')
    : []
  const reportTurnCount =
    asNumber(reportSummary?.turn_count) ?? (report?.quotes?.length ?? turns.length)

  return (
    <section className="ttc-voice-grid">
      <div className="ttc-card ttc-voice-panel">
        <div className="ttc-voice-panel-head">
          <div>
            <div className="ttc-mini-heading">
              <RadioIcon />
              QWEN REALTIME · LIVE CALL
            </div>
            <h2>与 AI 面试官实时对话</h2>
            <p className="ttc-muted">
              浏览器麦克风 → TTC 后端 WebSocket 中转 → 通义千问 Realtime。音频不落盘，挂断后只保留文字转写与报告。
            </p>
          </div>
          <span className={`ttc-voice-badge ttc-voice-badge-${stateMeta.tone}`}>
            {stateMeta.label}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>
            <Clock size={13} />
            {formatClock(elapsed)} / {formatClock(maxSeconds)}
          </span>
          <span>
            <Sparkles size={13} />
            模型：{model || '等待上游握手'}
          </span>
          <span>
            <Volume2 size={13} />
            音色：{voice || '—'}
          </span>
          <span>
            <Mic size={13} />
            {micMeta.label}
          </span>
          <span>
            <Waves size={13} />
            {phaseLabel}
          </span>
        </div>

        {error && (
          <div className="ttc-inline-error ttc-voice-error" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>实时语音提示</strong>
              <span>{error}</span>
            </div>
          </div>
        )}

        {notice && (
          <div className="ttc-notice">
            <CheckCircle2 size={15} />
            <span>{notice}</span>
          </div>
        )}

        <div className={`ttc-voice-stage ${callState === 'live' ? 'is-live' : ''}`}>
          <VoiceWaveform
            analyser={analyser}
            active={callState === 'live' && micState === 'active'}
            reducedMotion={reducedMotion}
          />
          {callState !== 'live' && (
            <div className="ttc-voice-idle">
              <span className="ttc-voice-idle-icon">
                {callState === 'connecting' || callState === 'ending' ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : callState === 'ended' ? (
                  <PhoneOff size={18} />
                ) : (
                  <MicOff size={18} />
                )}
              </span>
              <strong>
                {callState === 'connecting'
                  ? '正在建立 Qwen 实时语音会话'
                  : callState === 'ending'
                    ? '正在结束会话并生成报告'
                    : callState === 'ended'
                      ? '本次语音会话已结束'
                      : '点击“开始通话”后才会请求麦克风'}
              </strong>
              <span>
                {callState === 'idle'
                  ? '连接后可直接说话，AI 会实时用语音回应。'
                  : callState === 'error'
                    ? '请检查上方错误后重试；若会话已被使用，请新建会话。'
                    : '请稍候…'}
              </span>
            </div>
          )}
          {callState === 'live' && (
            <span className="ttc-voice-live-tag">
              <i />
              {phaseLabel}
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-col gap-2" aria-hidden="true">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="w-6 shrink-0">你</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
              <i
                className="block h-full rounded-full bg-sky-500 transition-[width] duration-100"
                style={{ width: `${Math.round(inputLevel * 100)}%` }}
              />
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="w-6 shrink-0">AI</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
              <i
                className="block h-full rounded-full bg-emerald-500 transition-[width] duration-100"
                style={{ width: `${Math.round(outputLevel * 100)}%` }}
              />
            </div>
          </div>
        </div>

        <div className="ttc-voice-controls">
          <div className="ttc-voice-actions">
            {canStart && (
              <button type="button" className="ttc-btn ttc-btn-primary" onClick={connect}>
                <Phone size={16} />
                {callState === 'error' ? '重新连接' : '开始通话'}
              </button>
            )}
            {callState === 'live' && (
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                onClick={() => commitAndRespond('manual')}
                disabled={
                  !hasSpeech || turnPhase === 'waiting' || turnPhase === 'speaking'
                }
                title="客户端断句兜底：把当前语音提交给模型并请求回复"
              >
                <Send size={15} />
                结束发言并发送
              </button>
            )}
            {canHangUp && (
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                onClick={() => hangUpRef.current()}
              >
                <PhoneOff size={15} />
                挂断并生成报告
              </button>
            )}
            {(micState === 'denied' || micState === 'error') && callState === 'live' && (
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                onClick={() => void startMicrophone()}
              >
                <RefreshCw size={14} />
                重试麦克风
              </button>
            )}
            {callState === 'ended' && (
              <span className="ttc-muted">
                请在上方重新创建会话后再次通话；同一会话不能重复连接。
              </span>
            )}
          </div>
          <p className="ttc-voice-permission">
            <ShieldCheck size={13} />
            仅在点击“开始通话”后请求麦克风；音频只用于本次实时对话，不写入数据库。
            建议佩戴耳机，避免 AI 的语音被麦克风再次采集而触发自打断。
          </p>
        </div>
      </div>

      <div className="ttc-voice-side">
        <div className="ttc-card ttc-voice-panel ttc-voice-transcript">
          <div className="ttc-voice-panel-head">
            <div>
              <div className="ttc-mini-heading">
                <MessageSquare size={14} />
                LIVE TRANSCRIPT
              </div>
              <h2>实时转写</h2>
            </div>
            <span className="ttc-voice-badge ttc-voice-badge-ok">
              {callState === 'live' ? '实时' : '等待'}
            </span>
          </div>

          <div
            className="mt-3 max-h-[420px] space-y-2 overflow-y-auto pr-1"
            ref={transcriptRef}
          >
            {turns.length === 0 && !userPartial && !assistantPartial && (
              <div className="ttc-voice-transcript-empty">
                <span className="ttc-voice-transcript-icon">
                  <AudioLines size={19} />
                </span>
                <strong>开始通话后显示真实转写</strong>
                <p>转写来自 Qwen 实时语音事件，不生成模拟对话。</p>
              </div>
            )}
            {turns.map((turn) => {
              const meta = ROLE_META[turn.role]
              const Icon = meta.icon
              return (
                <div
                  className={`rounded-xl border px-3 py-2 ${
                    turn.role === 'interviewer'
                      ? 'border-emerald-100 bg-emerald-50/60'
                      : 'border-sky-100 bg-sky-50/60'
                  }`}
                  key={turn.id}
                >
                  <span className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
                    <Icon size={13} />
                    {meta.label}
                  </span>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {turn.text}
                  </p>
                </div>
              )
            })}
            {userPartial && (
              <div className="rounded-xl border border-sky-100 bg-sky-50/60 px-3 py-2 opacity-80">
                <span className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
                  <UserRound size={13} />
                  候选人 · 正在识别
                </span>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                  {userPartial}
                </p>
              </div>
            )}
            {assistantPartial && (
              <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2 opacity-80">
                <span className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
                  <Bot size={13} />
                  AI 面试官 · 正在说话
                </span>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                  {assistantPartial}
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="ttc-card ttc-voice-panel">
          <div className="ttc-voice-panel-head">
            <div>
              <div className="ttc-mini-heading">
                <Waves size={14} />
                CALL REPORT
              </div>
              <h2>通话报告</h2>
            </div>
            <span className="ttc-voice-badge ttc-voice-badge-muted">
              {report ? '已生成' : '挂断后生成'}
            </span>
          </div>

          {!report && (
            <div className="ttc-empty-state ttc-empty-compact">
              <MessageSquare size={20} />
              <strong>尚未生成报告</strong>
              <span>挂断后由后端根据已提交的文字轮次生成转写报告。</span>
            </div>
          )}

          {report && (
            <div className="mt-3 space-y-3">
              <div className="ttc-detail-rows">
                <div className="ttc-detail-row">
                  <span>报告状态</span>
                  <strong>{report.status}</strong>
                </div>
                <div className="ttc-detail-row">
                  <span>会话状态</span>
                  <strong>{VOICE_STATUS_LABEL[report.session.status]}</strong>
                </div>
                <div className="ttc-detail-row">
                  <span>轮次数</span>
                  <strong>{reportTurnCount}</strong>
                </div>
                <div className="ttc-detail-row">
                  <span>模型版本</span>
                  <strong>{report.model_version}</strong>
                </div>
              </div>

              {reportLimitations.length > 0 && (
                <ul className="ttc-plain-list">
                  {reportLimitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}

              {report.quotes.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold text-slate-700">候选人原话</h3>
                  {report.quotes.slice(0, 8).map((quote) => (
                    <blockquote
                      className="rounded-lg border-l-2 border-sky-300 bg-sky-50/60 px-3 py-2 text-sm text-slate-600"
                      key={quote.turn_id}
                    >
                      {quote.text}
                    </blockquote>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function RadioIcon() {
  return <Waves size={14} />
}
