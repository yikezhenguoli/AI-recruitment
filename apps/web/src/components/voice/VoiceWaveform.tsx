import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Local microphone preview.
 *
 * The microphone is only requested after an explicit user action. Audio never
 * leaves the browser: there is no MediaRecorder, no upload and no persistence.
 */

export type MicrophoneStatus =
  | 'idle'
  | 'requesting'
  | 'active'
  | 'stopped'
  | 'unsupported'
  | 'denied'
  | 'no-device'
  | 'busy'
  | 'error'

export interface MicrophoneController {
  status: MicrophoneStatus
  error: string | null
  analyser: AnalyserNode | null
  isActive: boolean
  isSupported: boolean
  start: () => void
  stop: () => void
}

function getReducedMotionQuery(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return null
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)')
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => getReducedMotionQuery()?.matches ?? false)

  useEffect(() => {
    const query = getReducedMotionQuery()
    if (!query) return
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduced
}

function describeMicrophoneError(error: unknown): { status: MicrophoneStatus; message: string } {
  const name =
    typeof error === 'object' && error !== null && 'name' in error
      ? String((error as { name?: unknown }).name ?? '')
      : ''

  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return {
        status: 'denied',
        message: '麦克风权限被拒绝。请在浏览器地址栏的站点设置中允许麦克风，然后重新点击“开启麦克风”。',
      }
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return {
        status: 'no-device',
        message: '未检测到可用的麦克风设备。请连接麦克风或检查系统的输入设备设置后重试。',
      }
    case 'NotReadableError':
    case 'TrackStartError':
      return {
        status: 'busy',
        message: '麦克风无法读取，可能正被其他应用占用。请关闭占用麦克风的程序后重试。',
      }
    case 'SecurityError':
      return {
        status: 'denied',
        message: '浏览器以安全原因为由阻止了麦克风访问。请通过 HTTPS 或 localhost 打开本页面。',
      }
    case 'AbortError':
      return {
        status: 'error',
        message: '麦克风启动被中断，请重新尝试。',
      }
    default: {
      const detail = error instanceof Error && error.message ? error.message : '未知错误'
      return { status: 'error', message: `麦克风启动失败：${detail}` }
    }
  }
}

/**
 * Owns the getUserMedia / AudioContext lifecycle. Never starts on mount.
 */
export function useMicrophone(): MicrophoneController {
  const [status, setStatus] = useState<MicrophoneStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)

  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const startingRef = useRef(false)
  const mountedRef = useRef(true)

  const isSupported =
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function'

  const teardown = useCallback(() => {
    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect()
      } catch {
        // already disconnected
      }
      sourceRef.current = null
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }

    if (contextRef.current) {
      const context = contextRef.current
      contextRef.current = null
      if (context.state !== 'closed') {
        void context.close().catch(() => {
          // closing an already-closed context is harmless
        })
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      teardown()
    }
  }, [teardown])

  const start = useCallback(() => {
    if (startingRef.current || streamRef.current) return
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('unsupported')
      setError(
        '当前浏览器不支持麦克风采集（navigator.mediaDevices 不可用）。请使用最新版 Chrome / Edge，并通过 localhost 或 HTTPS 访问。',
      )
      return
    }

    startingRef.current = true
    setStatus('requesting')
    setError(null)

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        if (!mountedRef.current) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        const AudioContextConstructor:
          | (new () => AudioContext)
          | undefined =
          window.AudioContext ??
          (window as typeof window & { webkitAudioContext?: new () => AudioContext })
            .webkitAudioContext

        if (!AudioContextConstructor) {
          stream.getTracks().forEach((track) => track.stop())
          if (mountedRef.current) {
            setStatus('unsupported')
            setError('当前浏览器不支持 Web Audio API，无法绘制麦克风波形。')
          }
          return
        }

        try {
          const context = new AudioContextConstructor()
          const source = context.createMediaStreamSource(stream)
          const node = context.createAnalyser()
          node.fftSize = 2048
          node.smoothingTimeConstant = 0.82
          source.connect(node)

          streamRef.current = stream
          contextRef.current = context
          sourceRef.current = source
          setAnalyser(node)
          setStatus('active')
          void context.resume().catch(() => {
            // Some browsers still allow analysis while suspended; the UI stays honest.
          })
        } catch {
          stream.getTracks().forEach((track) => track.stop())
          if (mountedRef.current) {
            setStatus('error')
            setError('音频分析初始化失败，请刷新页面后重试。')
          }
        }
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return
        const info = describeMicrophoneError(err)
        setStatus(info.status)
        setError(info.message)
      })
      .finally(() => {
        startingRef.current = false
      })
  }, [])

  const stop = useCallback(() => {
    teardown()
    setAnalyser(null)
    setStatus('stopped')
    setError(null)
  }, [teardown])

  return {
    status,
    error,
    analyser,
    isActive: status === 'active' && analyser !== null,
    isSupported,
    start,
    stop,
  }
}

export interface VoiceWaveformProps {
  analyser: AnalyserNode | null
  active: boolean
  reducedMotion?: boolean
  className?: string
}

/**
 * Canvas waveform driven by requestAnimationFrame. Draws the real time-domain
 * signal when the mic is active, a static decorative wave otherwise. Honours
 * prefers-reduced-motion and pauses when the tab is hidden.
 */
export function VoiceWaveform({
  analyser,
  active,
  reducedMotion = false,
  className,
}: VoiceWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    const ctx = context

    const live = Boolean(active && analyser && !reducedMotion)
    // Explicit ArrayBuffer keeps the type compatible with getFloatTimeDomainData
    // under TypeScript's generic typed-array definitions.
    const timeData = analyser
      ? new Float32Array(new ArrayBuffer(analyser.fftSize * Float32Array.BYTES_PER_ELEMENT))
      : null
    const frequencyData = analyser
      ? new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount))
      : null
    let smoothedLevel = 0.08

    let frameId = 0
    let disposed = false
    let isVisible = document.visibilityState !== 'hidden'

    const syncSize = () => {
      const width = Math.max(1, canvas.clientWidth)
      const height = Math.max(1, canvas.clientHeight)
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const pixelWidth = Math.round(width * dpr)
      const pixelHeight = Math.round(height * dpr)
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth
        canvas.height = pixelHeight
      }
      return { width, height, dpr }
    }

    const drawSoundField = (
      width: number,
      height: number,
      level: number,
      phase: number,
      frequencyData: Uint8Array<ArrayBuffer> | null,
      animate: boolean,
    ) => {
      const mid = height / 2
      const center = width / 2
      // The active sound field spans 75% of the canvas: 12.5% → 87.5%.
      const halfWidth = width * 0.47
      const maxBarHeight = height * 0.5

      // Soft central halo: the voice feels like it radiates from the middle.
      const glowRadius = Math.max(36, height * (0.16 + level * 0.28))
      const glow = ctx.createRadialGradient(center, mid, 0, center, mid, glowRadius)
      glow.addColorStop(0, `rgba(86, 190, 240, ${0.08 + level * 0.16})`)
      glow.addColorStop(0.55, `rgba(120, 190, 245, ${0.05 + level * 0.08})`)
      glow.addColorStop(1, 'rgba(120, 190, 245, 0)')
      ctx.fillStyle = glow
      ctx.fillRect(0, 0, width, height)

      // A very soft baseline; no hard oscilloscope trace.
      ctx.save()
      ctx.strokeStyle = 'rgba(120, 175, 220, 0.10)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(width * 0.08, mid)
      ctx.lineTo(width * 0.92, mid)
      ctx.stroke()
      ctx.restore()

      const bars = Math.min(220, Math.max(110, Math.floor(width / 5)))
      const gradient = ctx.createLinearGradient(0, 0, width, 0)
      gradient.addColorStop(0, 'rgba(143, 210, 255, 0.34)')
      gradient.addColorStop(0.24, 'rgba(98, 179, 238, 0.68)')
      gradient.addColorStop(0.5, 'rgba(47, 137, 216, 0.90)')
      gradient.addColorStop(0.76, 'rgba(98, 179, 238, 0.68)')
      gradient.addColorStop(1, 'rgba(143, 210, 255, 0.34)')

      ctx.save()
      ctx.strokeStyle = gradient
      ctx.lineCap = 'round'
      ctx.shadowColor = 'rgba(62, 148, 230, 0.30)'
      ctx.shadowBlur = 5 + level * 16

      for (let i = 0; i < bars; i += 1) {
        const t = bars === 1 ? 0.5 : i / (bars - 1)
        const u = t * 2 - 1
        const absU = Math.abs(u)

        // Non-linear spacing: many stripes near the center, few and thin at the sides.
        const offset = u * halfWidth * (0.22 + 0.78 * Math.pow(absU, 1.3))
        const shimmer = animate ? Math.sin(phase * 0.001 + i * 0.37) * 0.45 * level : 0
        const x = center + offset + shimmer

        const centerEnvelope = Math.exp(-Math.pow(u / 1.05, 2))
        const sideTaper = Math.pow(1 - absU, 0.45)

        let spectral = 0.34
        if (frequencyData && frequencyData.length > 0) {
          const index = Math.min(
            frequencyData.length - 1,
            Math.floor(Math.pow(absU, 0.82) * (frequencyData.length - 1) * 0.72),
          )
          spectral = frequencyData[index] / 255
        } else {
          spectral = 0.28 + 0.16 * Math.sin(i * 0.71) + 0.07 * Math.sin(i * 1.93)
        }

        const variation = 0.4 + 0.6 * Math.max(0, Math.min(1, spectral))
        const stripeVariation = animate
          ? 0.84 + 0.26 * Math.sin(i * 1.37 + phase * 0.002)
          : 0.88 + 0.18 * Math.sin(i * 1.37)
        const baseHeight = height * 0.032
        const dynamicHeight = height * 0.7 * level * centerEnvelope * variation * stripeVariation
        // Hard vertical cap: no bar may exceed 50% of the canvas height.
        const barHeight = Math.min(maxBarHeight, Math.max(2, baseHeight + dynamicHeight * sideTaper))
        const lineWidth = Math.max(1, 2.6 - absU * 1.65)

        ctx.lineWidth = lineWidth
        ctx.beginPath()
        ctx.moveTo(x, mid - barHeight / 2)
        ctx.lineTo(x, mid + barHeight / 2)
        ctx.stroke()
      }

      ctx.restore()
    }

    const drawStatic = () => {
      const { width, height, dpr } = syncSize()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      drawSoundField(width, height, 0.18, 0, null, false)
    }

    const drawLive = (
      node: AnalyserNode,
      data: Float32Array<ArrayBuffer>,
      frequencyData: Uint8Array<ArrayBuffer> | null,
    ) => {
      const { width, height, dpr } = syncSize()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      node.getFloatTimeDomainData(data)
      if (frequencyData) node.getByteFrequencyData(frequencyData)

      let sumSquares = 0
      for (let i = 0; i < data.length; i += 1) {
        sumSquares += data[i] * data[i]
      }
      const rms = Math.sqrt(sumSquares / Math.max(1, data.length))

      // Combine time-domain loudness with voice-band spectral energy so quiet
      // speech still produces a visible response. Faster attack, slower release.
      let spectralLevel = 0
      if (frequencyData && frequencyData.length > 0) {
        const usableBins = Math.max(1, Math.floor(frequencyData.length * 0.55))
        let spectralSum = 0
        for (let i = 0; i < usableBins; i += 1) {
          spectralSum += frequencyData[i]
        }
        spectralLevel = spectralSum / (usableBins * 255)
      }
      const rmsTarget = rms > 0.0025 ? Math.min(1, rms * 12) : 0
      const spectralTarget = spectralLevel > 0.018 ? Math.min(1, spectralLevel * 2.4) : 0
      const target = Math.max(rmsTarget, spectralTarget)
      smoothedLevel += (target - smoothedLevel) * (target > smoothedLevel ? 0.28 : 0.12)
      const level = Math.max(smoothedLevel, rms > 0.0025 ? 0.07 : 0.03)

      drawSoundField(width, height, level, performance.now(), frequencyData, true)
    }

    const drawFrame = () => {
      if (live && analyser && timeData) drawLive(analyser, timeData, frequencyData)
      else drawStatic()
    }

    const tick = () => {
      frameId = 0
      if (disposed || !isVisible || !live || !analyser || !timeData) return
      drawLive(analyser, timeData, frequencyData)
      frameId = window.requestAnimationFrame(tick)
    }

    const startLoop = () => {
      if (!live || !isVisible || disposed || frameId) return
      frameId = window.requestAnimationFrame(tick)
    }

    const onVisibilityChange = () => {
      isVisible = document.visibilityState === 'visible'
      if (!isVisible) {
        if (frameId) {
          window.cancelAnimationFrame(frameId)
          frameId = 0
        }
        return
      }
      drawFrame()
      startLoop()
    }

    const resizeObserver = new ResizeObserver(() => {
      drawFrame()
      startLoop()
    })

    resizeObserver.observe(canvas)
    document.addEventListener('visibilitychange', onVisibilityChange)

    drawFrame()
    startLoop()

    return () => {
      disposed = true
      if (frameId) window.cancelAnimationFrame(frameId)
      resizeObserver.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [analyser, active, reducedMotion])

  return (
    <canvas
      ref={canvasRef}
      className={['ttc-voice-canvas', className].filter(Boolean).join(' ')}
      role="img"
      aria-label={active ? '实时麦克风输入波形' : '麦克风波形占位，尚未开始采集'}
    >
      当前浏览器不支持 Canvas，无法绘制波形。
    </canvas>
  )
}
