const INPUT_RATE = 16_000
const OUTPUT_RATE = 24_000

function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return out
}

function pcm16ToFloat(bytes: Uint8Array): Float32Array {
  const samples = Math.floor(bytes.length / 2)
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i += 1) {
    const value = (bytes[i * 2] | (bytes[i * 2 + 1] << 8)) << 16 >> 16
    out[i] = value / 0x8000
  }
  return out
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

function resampleLinear(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input
  const ratio = from / to
  const length = Math.max(1, Math.round(input.length / ratio))
  const out = new Float32Array(length)
  for (let i = 0; i < length; i += 1) {
    const position = i * ratio
    const left = Math.floor(position)
    const right = Math.min(input.length - 1, left + 1)
    const weight = position - left
    out[i] = input[left] * (1 - weight) + input[right] * weight
  }
  return out
}

type AudioContextCtor = typeof AudioContext

function audioContextCtor(): AudioContextCtor {
  const ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext
  if (!ctor) throw new Error('当前浏览器不支持 Web Audio')
  return ctor
}

/** 麦克风采集：把浏览器输入降采样到 16 kHz PCM16，按块回调 base64。 */
export class MicStreamer {
  private context: AudioContext | null = null
  private stream: MediaStream | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private processor: ScriptProcessorNode | null = null
  private sink: GainNode | null = null
  private analyser: AnalyserNode | null = null
  private levelData: Uint8Array<ArrayBuffer> | null = null
  private muted = false

  /**
   * 在用户点击的同一个任务里先建好 AudioContext。
   * iOS 只允许在用户手势中启动音频上下文，而 getUserMedia 的权限弹窗会把
   * 手势链打断，等它返回再创建的上下文会一直是 suspended（表现为录不到声音）。
   */
  prepare(): void {
    if (this.context) return
    const Ctor = audioContextCtor()
    try {
      this.context = new Ctor({ sampleRate: INPUT_RATE })
    } catch {
      this.context = new Ctor()
    }
    void this.context.resume()
  }

  async start(onChunk: (base64: string) => void): Promise<void> {
    if (!window.isSecureContext) {
      throw new Error('浏览器只在 localhost 或 HTTPS 下允许录音，请改用 https:// 打开本页。')
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持麦克风采集，请升级浏览器后重试。')
    }
    // 先于权限弹窗建上下文，保证还处在用户手势里。
    this.prepare()
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    const context = this.context as AudioContext
    await context.resume()
    if (context.state !== 'running') {
      throw new Error('浏览器拦截了音频启动，请点击页面后重试。')
    }

    this.source = context.createMediaStreamSource(this.stream)
    const processor = context.createScriptProcessor(2048, 1, 1)
    this.processor = processor
    processor.onaudioprocess = (event) => {
      if (this.muted) return
      const channel = event.inputBuffer.getChannelData(0)
      const pcm = resampleLinear(channel, context.sampleRate, INPUT_RATE)
      onChunk(bytesToBase64(new Uint8Array(floatToPcm16(pcm).buffer)))
    }
    // ScriptProcessor 必须接到输出才会触发，用 0 增益避免把麦克风回放出来。
    const sink = context.createGain()
    sink.gain.value = 0
    this.sink = sink
    this.source.connect(processor)
    processor.connect(sink)
    sink.connect(context.destination)

    // 给可视化用的电平表：接在同一路输入上，不额外采集一次麦克风。
    const analyser = context.createAnalyser()
    analyser.fftSize = 1024
    analyser.smoothingTimeConstant = 0.55
    this.analyser = analyser
    this.levelData = new Uint8Array(analyser.fftSize)
    this.source.connect(analyser)
    analyser.connect(sink)
  }

  /** 当前输入音量 0..1（RMS 归一化），供声波图逐帧读取。 */
  getLevel(): number {
    const analyser = this.analyser
    const data = this.levelData
    if (!analyser || !data) return 0
    analyser.getByteTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i += 1) {
      const value = (data[i] - 128) / 128
      sum += value * value
    }
    const rms = Math.sqrt(sum / data.length)
    return Math.min(1, rms * 4.2)
  }

  setMuted(muted: boolean): void {
    this.muted = muted
    if (this.stream) {
      this.stream.getAudioTracks().forEach((track) => {
        track.enabled = !muted
      })
    }
  }

  stop(): void {
    this.processor?.disconnect()
    this.analyser?.disconnect()
    this.sink?.disconnect()
    this.source?.disconnect()
    this.stream?.getTracks().forEach((track) => track.stop())
    void this.context?.close()
    this.processor = null
    this.analyser = null
    this.levelData = null
    this.sink = null
    this.source = null
    this.stream = null
    this.context = null
  }
}

/** 播放后端回传的 24 kHz PCM16 分片，按时间轴排队，支持打断。 */
export class PcmPlayer {
  private context: AudioContext
  private playhead = 0
  private sources = new Set<AudioBufferSourceNode>()
  private analyser: AnalyserNode
  private levelData: Uint8Array<ArrayBuffer>

  constructor() {
    this.context = new (audioContextCtor())()
    void this.context.resume()
    this.analyser = this.context.createAnalyser()
    this.analyser.fftSize = 1024
    this.analyser.smoothingTimeConstant = 0.55
    this.analyser.connect(this.context.destination)
    this.levelData = new Uint8Array(this.analyser.fftSize)
  }

  /** 当前播报音量 0..1，供声波图逐帧读取。 */
  getLevel(): number {
    this.analyser.getByteTimeDomainData(this.levelData)
    let sum = 0
    for (let i = 0; i < this.levelData.length; i += 1) {
      const value = (this.levelData[i] - 128) / 128
      sum += value * value
    }
    const rms = Math.sqrt(sum / this.levelData.length)
    return Math.min(1, rms * 4.2)
  }

  get running(): boolean {
    return this.context.state === 'running'
  }

  enqueue(base64: string, sampleRate = OUTPUT_RATE): void {
    if (!base64) return
    const samples = pcm16ToFloat(base64ToBytes(base64))
    if (samples.length === 0) return
    const buffer = this.context.createBuffer(1, samples.length, sampleRate)
    buffer.getChannelData(0).set(samples)
    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.connect(this.analyser)
    const start = Math.max(this.playhead, this.context.currentTime + 0.05)
    source.start(start)
    this.playhead = start + buffer.duration
    this.sources.add(source)
    source.onended = () => this.sources.delete(source)
  }

  /** 候选人开口时打断当前播报（barge-in）。 */
  interrupt(): void {
    for (const source of this.sources) {
      try {
        source.stop()
      } catch {
        // 已经结束的节点停止会抛错，忽略即可。
      }
    }
    this.sources.clear()
    this.playhead = this.context.currentTime
  }

  close(): void {
    this.interrupt()
    void this.context.close()
  }
}

export { INPUT_RATE, OUTPUT_RATE }
