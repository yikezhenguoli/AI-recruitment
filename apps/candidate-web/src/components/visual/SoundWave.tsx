import { useEffect, useRef } from 'react'

export interface SoundWaveProps {
  className?: string
  height?: number
  /** 'spectrum' 彩条声谱（首页主视觉），'ribbon' 双线流动波（通话中）。 */
  variant?: 'spectrum' | 'ribbon'
  /** 实时音量 0..1 的来源；不传时只做空闲呼吸。 */
  getLevel?: () => number
  /** 屏幕阅读器用的说明；纯装饰时留空。 */
  label?: string
}

const STOPS = ['#38bdf8', '#2f89d8', '#7c6cf0', '#12a39b'] as const

function waveGradient(context: CanvasRenderingContext2D, width: number): CanvasGradient {
  const gradient = context.createLinearGradient(0, 0, width, 0)
  STOPS.forEach((color, index) => gradient.addColorStop(index / (STOPS.length - 1), color))
  return gradient
}

function roundedBar(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  const r = Math.min(radius, Math.abs(height) / 2, width / 2)
  context.beginPath()
  context.moveTo(x + r, y)
  context.lineTo(x + width - r, y)
  context.quadraticCurveTo(x + width, y, x + width, y + r)
  context.lineTo(x + width, y + height - r)
  context.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
  context.lineTo(x + r, y + height)
  context.quadraticCurveTo(x, y + height, x, y + height - r)
  context.lineTo(x, y + r)
  context.quadraticCurveTo(x, y, x + r, y)
  context.closePath()
}

/**
 * 会呼吸的声波图：没有音量输入时缓慢起伏，接上麦克风/播放器电平后
 * 振幅随声音实时变化。纯 canvas，尊重「减少动效」偏好。
 */
export function SoundWave({
  className = '',
  height = 160,
  variant = 'spectrum',
  getLevel,
  label,
}: SoundWaveProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const levelRef = useRef<(() => number) | undefined>(getLevel)

  useEffect(() => {
    levelRef.current = getLevel
  }, [getLevel])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let width = 1
    let frame = 0
    let smooth = 0
    let startedAt = performance.now()

    const syncSize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      width = Math.max(1, canvas.clientWidth)
      canvas.width = Math.max(1, Math.floor(width * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const drawSpectrum = (time: number, drive: number) => {
      const count = Math.max(32, Math.min(110, Math.floor(width / 7)))
      const slot = width / count
      const barWidth = Math.max(2, slot * 0.5)
      const gradient = waveGradient(context, width)
      const mid = height / 2

      for (let i = 0; i < count; i += 1) {
        const position = i / (count - 1)
        const centerBias = 0.55 + 0.45 * Math.cos(Math.PI * (position - 0.5) * 1.7)
        const breath = 0.5 + 0.5 * Math.sin(time * 2.1 + i * 0.52) * Math.cos(time * 1.27 - i * 0.19)
        const seeded = Math.abs((Math.sin(i * 12.9898 + 4.1414) * 43758.5453) % 1)
        const amplitude = Math.min(
          height * 0.92,
          height *
            centerBias *
            (0.1 + drive * 1.15 * (0.3 + 0.7 * breath) * (0.5 + 0.5 * seeded)),
        )
        const x = i * slot + (slot - barWidth) / 2

        context.globalAlpha = 0.14
        context.fillStyle = gradient
        roundedBar(context, x, mid - amplitude * 0.62, barWidth, amplitude * 1.24, barWidth / 2)
        context.fill()

        context.globalAlpha = 0.92
        roundedBar(context, x, mid - amplitude / 2, barWidth, amplitude, barWidth / 2)
        context.fill()
      }
      context.globalAlpha = 1
    }

    const drawRibbon = (time: number, drive: number) => {
      const mid = height / 2
      const gradient = waveGradient(context, width)
      const layers = [
        { alpha: 0.16, scale: 1.9, speed: 1.1, offset: 0 },
        { alpha: 0.24, scale: 1.4, speed: 1.5, offset: 1.8 },
        { alpha: 0.95, scale: 1, speed: 1.9, offset: 3.4 },
      ]

      context.lineCap = 'round'
      context.lineJoin = 'round'

      layers.forEach((layer) => {
        context.beginPath()
        context.strokeStyle = gradient
        context.globalAlpha = layer.alpha
        context.lineWidth = layer.scale * 1.8
        const amplitude = height * 0.24 * layer.scale * (0.3 + drive)
        for (let x = 0; x <= width; x += 3) {
          const p = x / width
          const envelope = Math.sin(Math.PI * p) ** 0.7
          const y =
            mid +
            Math.sin(p * 9 + time * layer.speed + layer.offset) * amplitude * envelope * 0.6 +
            Math.sin(p * 17 - time * layer.speed * 0.7) * amplitude * envelope * 0.25
          if (x === 0) context.moveTo(x, y)
          else context.lineTo(x, y)
        }
        context.stroke()
      })

      // 中心微光
      context.globalAlpha = 0.3
      const glow = context.createRadialGradient(width / 2, mid, 0, width / 2, mid, width * 0.5)
      glow.addColorStop(0, 'rgba(56, 189, 248, 0.22)')
      glow.addColorStop(1, 'rgba(56, 189, 248, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, width, height)
      context.globalAlpha = 1
    }

    const render = (now: number, animate: boolean) => {
      const time = animate ? (now - startedAt) / 1000 : 1.6
      const ambient = 0.18 + 0.07 * Math.sin(time * 0.9) + 0.04 * Math.sin(time * 0.37 + 1.7)
      let level = 0
      try {
        level = levelRef.current?.() ?? 0
      } catch {
        level = 0
      }
      const baseline = variant === 'ribbon' ? 0.3 : 0.55
      const target = Math.min(1, Math.max(level, ambient * baseline))
      smooth += (target - smooth) * (animate ? 0.12 : 1)

      context.clearRect(0, 0, width, height)
      if (variant === 'ribbon') drawRibbon(time, 0.18 + smooth * 1.25)
      else drawSpectrum(time, 0.3 + smooth * 1.05)
    }

    const loop = (now: number) => {
      render(now, true)
      frame = window.requestAnimationFrame(loop)
    }

    const start = () => {
      if (frame || reduced) return
      frame = window.requestAnimationFrame(loop)
    }

    const stop = () => {
      if (frame) window.cancelAnimationFrame(frame)
      frame = 0
    }

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') stop()
      else start()
    }

    syncSize()
    if (reduced) {
      render(startedAt, false)
    } else {
      start()
    }

    const observer = new ResizeObserver(() => {
      syncSize()
      if (reduced) render(startedAt, false)
    })
    observer.observe(canvas)
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      stop()
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      context.clearRect(0, 0, width, height)
      startedAt = performance.now()
    }
  }, [height, variant])

  return (
    <canvas
      ref={canvasRef}
      className={`block w-full ${className}`}
      style={{ height }}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  )
}
