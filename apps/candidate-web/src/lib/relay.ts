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
  private lastActivity = 0
  private watchdog: number | null = null
  private responding = false

  /** 上游与浏览器都没有新事件多久之后，主动请面试官接着说。 */
  private static readonly IDLE_MS = 15_000
  /** 回复已经开始但这么久没有任何分片，认为上游卡住，取消后重来。 */
  private static readonly STALL_MS = 20_000

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
      this.lastActivity = Date.now()

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
        this.startWatchdog()
        return
      }

      if (type === 'error') {
        const message = payload.error?.message ?? payload.message ?? ''
        // 兜底重试会和上游的进行中状态撞车，这类拒绝不是通话故障。
        if (/already in progress|not active|no active response/i.test(message)) return
        this.handlers.onState('error', message || '实时语音返回错误')
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
        case 'response.created':
          this.responding = true
          break
        case 'response.done':
          this.responding = false
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
      this.stopWatchdog()
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

  /**
   * 兜底：AI 说完一句后就等着，若上游的 VAD 没再触发（被回声/噪声误判后卡住，
   * 或 response 被取消后没有新的输入），通话会长时间没人说话。这里在双方都
   * 安静超过 15 秒时主动递一条提示，请面试官重述当前问题。
   *
   * 只在连接正常、麦克风没有电平（候选人确实没在说话）时触发，
   * 候选人在思考或回答时不会被打断。
   */
  private startWatchdog(): void {
    this.stopWatchdog()
    this.lastActivity = Date.now()
    this.watchdog = window.setInterval(() => {
      const socket = this.socket
      if (this.closing || !socket || socket.readyState !== WebSocket.OPEN) return
      const idle = Date.now() - this.lastActivity
      if (this.responding) {
        // 回复进行中就别再插一条 response.create（上游会回
        // "response already in progress"）；但长时间没有任何分片时，
        // 取消掉这轮，让下面的空闲逻辑重新把话筒交回给面试官。
        if (idle > RelayInterview.STALL_MS) {
          this.send({ type: 'response.cancel' })
          this.responding = false
          this.lastActivity = Date.now()
        }
        return
      }
      if (idle < RelayInterview.IDLE_MS) return
      if ((this.mic?.getLevel() ?? 0) > 0.05) {
        this.lastActivity = Date.now()
        return
      }
      this.send({
        type: 'conversation.item.create',
        item: {
          type: 'message',
          role: 'user',
          content: [{ type: 'input_text', text: '（候选人这边一直没有声音，请重述当前问题并邀请他回答）' }],
        },
      })
      this.send({ type: 'response.create' })
      this.lastActivity = Date.now()
    }, 3000)
  }

  private stopWatchdog(): void {
    if (this.watchdog !== null) {
      window.clearInterval(this.watchdog)
      this.watchdog = null
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
    this.stopWatchdog()
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
