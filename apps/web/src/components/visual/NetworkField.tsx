import { useEffect, useRef, useState } from 'react'

interface NetworkNode {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  tone: number
}

/**
 * Decorative light-network canvas for the homepage hero only.
 * Cleanup: rAF, ResizeObserver, IntersectionObserver, visibility + pointer listeners.
 * Reduced motion draws one static frame and stops.
 */
export function NetworkField({ className = '' }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement
    if (!canvas || !host) return

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      setFailed(true)
      return
    }

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let reduced = motionQuery.matches
    let width = 0
    let height = 0
    let dpr = 1
    let nodes: NetworkNode[] = []
    let raf = 0
    let running = true
    let inView = true
    let pageVisible = document.visibilityState !== 'hidden'
    let lastFrame = 0
    let pointerX = 0.5
    let pointerY = 0.5

    const styles = getComputedStyle(canvas)
    const primary = styles.getPropertyValue('--lg2-primary').trim() || '#0e63c4'
    const cyan = styles.getPropertyValue('--lg2-cyan').trim() || '#38bdf8'
    const lineColor = styles.getPropertyValue('--lg2-line').trim() || 'rgba(63, 124, 177, .16)'

    const buildNodes = () => {
      const broad = Math.min(56, Math.max(14, Math.floor(width / 28)))
      const count = width < 768 ? Math.max(12, Math.floor(broad / 2)) : broad
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.24,
        vy: (Math.random() - 0.5) * 0.24,
        r: 1 + Math.random(),
        tone: Math.random() > 0.78 ? 1 : 0,
      }))
    }

    const resize = () => {
      width = host.clientWidth
      height = host.clientHeight
      if (!width || !height) return
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      buildNodes()
      // Cancel any pending chain first; otherwise resize can create a second
      // untracked rAF chain that stop() cannot clean up.
      if (raf) {
        window.cancelAnimationFrame(raf)
        raf = 0
      }
      lastFrame = 0
      if (reduced) drawStatic()
      else draw(performance.now())
    }

    const paintNodes = (elapsed: number) => {
      ctx.clearRect(0, 0, width, height)
      const ox = (pointerX - 0.5) * 6
      const oy = (pointerY - 0.5) * 6

      for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j += 1) {
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distance = Math.hypot(dx, dy)
          if (distance > 140) continue
          ctx.globalAlpha = (1 - distance / 140) * 0.55
          ctx.strokeStyle = lineColor
          ctx.lineWidth = 0.7
          ctx.beginPath()
          ctx.moveTo(a.x + ox, a.y + oy)
          ctx.lineTo(b.x + ox, b.y + oy)
          ctx.stroke()
        }
      }

      for (const node of nodes) {
        ctx.globalAlpha = node.tone === 1 ? 0.5 : 0.38
        ctx.fillStyle = node.tone === 1 ? cyan : primary
        ctx.beginPath()
        ctx.arc(node.x + ox, node.y + oy, node.r, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.globalAlpha = 1
      // Keep elapsed meaningful for callers / debugging without visual noise.
      void elapsed
    }

    const draw = (now: number) => {
      raf = 0
      // Do not continue the loop while hidden, off-screen, or reduced-motion.
      if (!running || reduced || !inView || !pageVisible) return
      if (now - lastFrame >= 32) {
        lastFrame = now
        for (const node of nodes) {
          node.x += node.vx
          node.y += node.vy
          if (node.x < -12) node.x = width + 12
          if (node.x > width + 12) node.x = -12
          if (node.y < -12) node.y = height + 12
          if (node.y > height + 12) node.y = -12
        }
        paintNodes(now)
      }
      raf = window.requestAnimationFrame(draw)
    }

    const drawStatic = () => {
      paintNodes(0)
    }

    const stop = () => {
      if (raf) {
        window.cancelAnimationFrame(raf)
        raf = 0
      }
    }

    const start = () => {
      if (reduced || !running || raf || !inView || !pageVisible) return
      lastFrame = 0
      raf = window.requestAnimationFrame(draw)
    }

    const onVisibility = () => {
      pageVisible = document.visibilityState !== 'hidden'
      if (pageVisible) start()
      else stop()
    }

    const onMotionChange = () => {
      reduced = motionQuery.matches
      if (reduced) {
        stop()
        drawStatic()
      } else {
        start()
      }
    }

    const hero = canvas.closest('.lg2-hero') as HTMLElement | null
    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' || reduced) return
      const rect = canvas.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      pointerX = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
      pointerY = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
    }
    const onPointerLeave = () => {
      pointerX = 0.5
      pointerY = 0.5
    }

    const resizeObserver = new ResizeObserver(resize)
    const intersectionObserver = new IntersectionObserver(
      (entries) => {
        inView = entries.some((entry) => entry.isIntersecting)
        if (inView) start()
        else stop()
      },
      { threshold: 0.05 },
    )

    resizeObserver.observe(host)
    intersectionObserver.observe(canvas)
    document.addEventListener('visibilitychange', onVisibility)
    hero?.addEventListener('pointermove', onPointerMove)
    hero?.addEventListener('pointerleave', onPointerLeave)
    if (motionQuery.addEventListener) {
      motionQuery.addEventListener('change', onMotionChange)
    } else {
      motionQuery.addListener(onMotionChange)
    }

    resize()
    if (!reduced) start()

    return () => {
      running = false
      stop()
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      hero?.removeEventListener('pointermove', onPointerMove)
      hero?.removeEventListener('pointerleave', onPointerLeave)
      if (motionQuery.removeEventListener) {
        motionQuery.removeEventListener('change', onMotionChange)
      } else {
        motionQuery.removeListener(onMotionChange)
      }
    }
  }, [])

  if (failed) {
    return (
      <svg
        className={`lg2-network-fallback ${className}`}
        viewBox="0 0 640 420"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
        focusable="false"
      >
        <g fill="none" stroke="var(--lg2-line-strong)" strokeWidth="1">
          <path d="M38 320 L150 210 L264 286 L392 152 L534 236 L604 120" />
          <path d="M92 120 L214 168 L310 88 L438 196 L560 76" />
          <path d="M150 210 L214 168 M264 286 L310 88 M392 152 L438 196 M534 236 L560 76" />
        </g>
        <g fill="var(--lg2-primary)" opacity=".42">
          <circle cx="38" cy="320" r="2.5" />
          <circle cx="150" cy="210" r="2.5" />
          <circle cx="264" cy="286" r="2.5" />
          <circle cx="392" cy="152" r="2.5" />
          <circle cx="534" cy="236" r="2.5" />
          <circle cx="214" cy="168" r="2" />
          <circle cx="310" cy="88" r="2" />
          <circle cx="438" cy="196" r="2" />
        </g>
        <g fill="var(--lg2-cyan)" opacity=".55">
          <circle cx="604" cy="120" r="2" />
          <circle cx="560" cy="76" r="2" />
          <circle cx="92" cy="120" r="2" />
        </g>
      </svg>
    )
  }

  return <canvas ref={canvasRef} className={`lg2-network-field ${className}`} aria-hidden="true" />
}
