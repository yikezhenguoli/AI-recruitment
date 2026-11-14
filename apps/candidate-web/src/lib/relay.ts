import { finishInterview } from '../api/portal'
import { MicStreamer, PcmPlayer } from './audio'
import type { LiveState } from './realtime'
import { describeSocketClose, openAuthedSocket } from './ws'

export interface RelayLine {
  id: string
  role: 'interviewer' | 'candidate' | 'system'
  text: string
  pending: boolean
}

export interface RelayInfo {
  model: string
  voice: string
  maxSeconds: number
}

export interface RelayHandlers {
  onState: (state: LiveState, detail?: string) => void
  onLine: (line: RelayLine) => void
  onRelay: (info: RelayInfo) => void
}

interface UpstreamEvent {
  type?: string
  delta?: string
  transcript?: string
  item_id?: string
  response_id?: string
  message?: string
  error?: { message?: string }
  model?: string
  voice?: string
  maxSeconds?: number
}

/**
 * 通义千问实时语音：浏览器把麦克风 PCM 经 WebSocket 发给后端中转，
 * 后端再连 DashScope。密钥留在服务端，撤回授权时后端会主动断开。
 */
export class RelayInterview {
  private socket: WebSocket | null = null
  private mic: MicStreamer | null = null
  private player: PcmPlayer | null = null
  private lines = new Map<string, RelayLine>()
  private closing = false
  private started = false
  private opened = false
  private cancelled = false

  constructor(
    private readonly sessionId: string,
    private readonly handlers: RelayHandlers,
  ) {}

  /**
   * 顺序是「先取麦克风，再连服务端」：后端一收到连接就把会话置为 live，
   * 断开即记一次「候选人结束」且无法重连。麦克风拿不到就不要连，
   * 这样候选人换个浏览器或改用 HTTPS 后还能重来。
   */
  async start(): Promise<void> {
    if (this.socket || this.started) return
    this.started = true
    this.closing = false
    this.lines.clear()
    this.handlers.onState('requesting-mic')

    // 必须在用户点击的同一个任务里创建，否则浏览器会拦下自动播放。
    this.player = new PcmPlayer()

    const mic = new MicStreamer()
    try {
      await mic.start((base64) => this.send({ type: 'input_audio_buffer.append', audio: base64 }))
    } catch (error) {
      mic.stop()
      this.player?.close()
      this.player = null
      this.started = false
      this.handlers.onState(
        'error',
        error instanceof Error ? error.message : '无法开启麦克风',
      )
      return
    }
    if (this.cancelled) {
      mic.stop()
      this.player?.close()
      this.player = null
      return
    }
    this.mic = mic
    this.opened = true

    const socket = openAuthedSocket(`/voice-sessions/${this.sessionId}/realtime`)
    this.socket = socket

    socket.onmessage = (event) => {
      let payload: UpstreamEvent
      try {
        payload = JSON.parse(String(event.data)) as UpstreamEvent
      } catch {
        return
      }
      const type = payload.type ?? ''

      if (type === 'relay.ready') {
        this.handlers.onRelay({
          model: payload.model ?? '',
          voice: payload.voice ?? '',
          maxSeconds: payload.maxSeconds ?? 0,
        })
        this.handlers.onState('connected')
        // 上游不接受「没有输入条目」的 response.create，先放一条开场条目再触发；
        // 这条是纯文本、没有音频，不会出现在候选人转写里。
        this.send({
          type: 'conversation.item.create',
          item: {
            type: 'message',
            role: 'user',
            content: [{ type: 'input_text', text: '（候选人已进入通话，请开始提问）' }],
          },
        })
        this.send({ type: 'response.create' })
        return
      }

      if (type === 'error') {
        this.handlers.onState('error', payload.error?.message ?? payload.message ?? '实时语音返回错误')
        return
      }

      switch (type) {
        case 'input_audio_buffer.speech_started':
          this.player?.interrupt()
          break
        case 'conversation.item.input_audio_transcription.delta': {
          const key = `candidate:${payload.item_id ?? 'current'}`
          const existing = this.lines.get(key)
          this.upsert(key, 'candidate', (existing?.text ?? '') + (payload.delta ?? ''), true)
          break
        }
        case 'conversation.item.input_audio_transcription.completed': {
          const key = `candidate:${payload.item_id ?? 'current'}`
          const text = (payload.transcript ?? '').trim()
          if (text) this.upsert(key, 'candidate', text, false)
          break
        }
        case 'response.audio_transcript.delta':
        case 'response.text.delta': {
          const key = `interviewer:${payload.item_id ?? payload.response_id ?? 'current'}`
          const existing = this.lines.get(key)
          this.upsert(key, 'interviewer', (existing?.text ?? '') + (payload.delta ?? ''), true)
          break
        }
        case 'response.audio_transcript.done':
        case 'response.text.done': {
          const key = `interviewer:${payload.item_id ?? payload.response_id ?? 'current'}`
          const text = (payload.transcript ?? '').trim()
          if (text) this.upsert(key, 'interviewer', text, false)
          break
        }
        case 'response.audio.delta':
          if (payload.delta) this.player?.enqueue(payload.delta)
          break
        case 'response.done':
          for (const line of this.lines.values()) {
            if (line.role === 'interviewer' && line.pending) {
              this.upsert(line.id, line.role, line.text, false)
            }
          }
          break
        default:
          break
      }
    }

    socket.onerror = () => {
      if (!this.closing) this.handlers.onState('error', '实时语音连接出错')
    }

    socket.onclose = (event) => {
      this.teardownAudio()
      this.socket = null
      if (this.closing) {
        this.handlers.onState('closed')
        return
      }
      if (event.code === 1000) {
        this.handlers.onState('closed')
      } else {
        this.handlers.onState('error', describeSocketClose(event.code))
      }
    }
  }

  private send(payload: unknown): void {
    const socket = this.socket
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
    }
  }

  private upsert(
    id: string,
    role: RelayLine['role'],
    text: string,
    pending: boolean,
  ): void {
    const line = { id, role, text, pending }
    this.lines.set(id, line)
    this.handlers.onLine(line)
  }

  setMuted(muted: boolean): void {
    this.mic?.setMuted(muted)
  }

  /** 双方声音的最大电平 0..1：麦克风与面试官播报取较大值。 */
  getLevel(): number {
    return Math.max(this.mic?.getLevel() ?? 0, this.player?.getLevel() ?? 0)
  }

  async stop(): Promise<void> {
    if (!this.started) return
    this.closing = true
    this.cancelled = true
    this.started = false
    const opened = this.opened
    this.opened = false
    const turns = [...this.lines.values()]
      .filter((line) => line.role !== 'system' && line.text.trim().length > 0)
      .map((line, index) => ({
        index,
        role: line.role,
        text: line.text.trim(),
      }))
    if (opened) {
      try {
        await finishInterview(this.sessionId, turns)
      } catch {
        // 会话可能已被后端按超时或撤回结束，轮次落盘失败不影响关闭连接。
      }
    }
    this.socket?.close(1000)
    this.socket = null
    this.teardownAudio()
    this.handlers.onState('closed')
  }

  private teardownAudio(): void {
    this.mic?.stop()
    this.mic = null
    this.player?.close()
    this.player = null
  }
}
