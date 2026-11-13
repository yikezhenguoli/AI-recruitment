import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
  hue: number
}

/**
 * Very light pointer trail: a few fading blue motes behind a fine-pointer
 * cursor. It is decorative only, never receives pointer events, and is disabled
 * for touch devices and reduced-motion users.
 */
export function CursorTrail() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const finePointer = window.matchMedia('(pointer: fine)').matches
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!finePointer || reducedMotion) return

    const context = canvas.getContext('2d')
    if (!context) return

    let width = 0
    let height = 0
    let frame = 0
    let visible = document.visibilityState !== 'hidden'
    let lastX = 0
    let lastY = 0
    let hasPointer = false
    let lastTime = 0
    const particles: Particle[] = []
    const maxParticles = 34

    const syncSize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = Math.max(1, Math.floor(width * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const draw = (now: number) => {
      frame = 0
      if (!visible) {
        lastTime = 0
        return
      }

      const delta = lastTime ? Math.min(32, now - lastTime) : 16
      lastTime = now
      context.clearRect(0, 0, width, height)

      for (let i = particles.length - 1; i >= 0; i -= 1) {
        const particle = particles[i]
        particle.life += delta
        particle.x += particle.vx * delta * 0.06
        particle.y += particle.vy * delta * 0.06
        particle.vx *= 0.96
        particle.vy = particle.vy * 0.96 - 0.002

        const alpha = Math.max(0, 1 - particle.life / particle.maxLife)
        if (alpha <= 0) {
          particles.splice(i, 1)
          continue
        }

        const radius = particle.size * (0.8 + alpha * 0.65)
        const gradient = context.createRadialGradient(
          particle.x,
          particle.y,
          0,
          particle.x,
          particle.y,
          radius,
        )
        gradient.addColorStop(0, `hsla(${particle.hue}, 92%, 66%, ${0.16 * alpha})`)
        gradient.addColorStop(0.45, `hsla(${particle.hue}, 90%, 58%, ${0.075 * alpha})`)
        gradient.addColorStop(1, `hsla(${particle.hue}, 90%, 58%, 0)`)
        context.fillStyle = gradient
        context.beginPath()
        context.arc(particle.x, particle.y, radius, 0, Math.PI * 2)
        context.fill()
      }

      if (hasPointer) {
        const glow = context.createRadialGradient(lastX, lastY, 0, lastX, lastY, 18)
        glow.addColorStop(0, 'rgba(114, 197, 255, .14)')
        glow.addColorStop(0.55, 'rgba(114, 197, 255, .045)')
        glow.addColorStop(1, 'rgba(114, 197, 255, 0)')
        context.fillStyle = glow
        context.beginPath()
        context.arc(lastX, lastY, 18, 0, Math.PI * 2)
        context.fill()
      }

      if (particles.length > 0) {
        frame = window.requestAnimationFrame(draw)
      } else {
        lastTime = 0
      }
    }

    const start = () => {
      if (!frame && visible) frame = window.requestAnimationFrame(draw)
    }

    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') return
      if (!hasPointer) {
        lastX = event.clientX
        lastY = event.clientY
        hasPointer = true
        return
      }

      const dx = event.clientX - lastX
      const dy = event.clientY - lastY
      const distance = Math.hypot(dx, dy)
      lastX = event.clientX
      lastY = event.clientY
      if (distance < 1.5) return

      const count = Math.min(3, Math.max(1, Math.floor(distance / 18)))
      const baseAngle = Math.atan2(dy, dx)
      for (let i = 0; i < count; i += 1) {
        const angle = baseAngle + (Math.random() - 0.5) * 0.9
        const speed = 0.16 + Math.random() * 0.42
        particles.push({
          x: event.clientX + (Math.random() - 0.5) * 3,
          y: event.clientY + (Math.random() - 0.5) * 3,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 0.08,
          life: 0,
          maxLife: 500 + Math.random() * 300,
          size: 3 + Math.random() * 5,
          hue: 198 + Math.random() * 24,
        })
      }
      if (particles.length > maxParticles) {
        particles.splice(0, particles.length - maxParticles)
      }
      start()
    }

    const onVisibilityChange = () => {
      visible = document.visibilityState !== 'hidden'
      if (visible) start()
      else if (frame) {
        window.cancelAnimationFrame(frame)
        frame = 0
      }
    }

    const onResize = () => {
      syncSize()
      start()
    }

    syncSize()
    window.addEventListener('resize', onResize, { passive: true })
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('pointermove', onPointerMove)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      context.clearRect(0, 0, width, height)
    }
  }, [])

  return <canvas ref={canvasRef} className="ttc-cursor-trail" aria-hidden="true" />
}
