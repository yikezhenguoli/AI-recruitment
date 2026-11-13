import { useEffect, useRef, useState } from 'react'

/**
 * Homepage hero atmosphere. Purely decorative: aria-hidden, no pointer events,
 * no data. Layers are CSS gradients; the only per-pointer work is writing two
 * custom properties for the local light (fine pointer + motion allowed only).
 *
 * The whole layer group pauses (CSS animation-play-state) when the hero leaves
 * the viewport, the tab is hidden, or reduced motion is requested.
 */
export function CinematicBackground() {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [idle, setIdle] = useState(false)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    const hero = root.closest('.lg2-hero') as HTMLElement | null
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let reduced = motionQuery.matches
    let inView = true
    let pageVisible = document.visibilityState !== 'hidden'

    const syncIdle = () => setIdle(reduced || !inView || !pageVisible)

    const onPointerMove = (event: PointerEvent) => {
      if (reduced || event.pointerType !== 'mouse') return
      const rect = root.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      root.style.setProperty('--lg2-mx', `${(event.clientX - rect.left).toFixed(1)}px`)
      root.style.setProperty('--lg2-my', `${(event.clientY - rect.top).toFixed(1)}px`)
      root.style.setProperty('--lg2-pointer', '1')
    }

    const onPointerLeave = () => {
      root.style.setProperty('--lg2-pointer', '0')
    }

    const onVisibility = () => {
      pageVisible = document.visibilityState !== 'hidden'
      syncIdle()
    }

    const onMotionChange = () => {
      reduced = motionQuery.matches
      if (reduced) root.style.setProperty('--lg2-pointer', '0')
      syncIdle()
    }

    const observer =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(
            (entries) => {
              inView = entries.some((entry) => entry.isIntersecting)
              syncIdle()
            },
            { threshold: 0.02 },
          )

    observer?.observe(root)
    document.addEventListener('visibilitychange', onVisibility)
    hero?.addEventListener('pointermove', onPointerMove, { passive: true })
    hero?.addEventListener('pointerleave', onPointerLeave, { passive: true })

    if (typeof motionQuery.addEventListener === 'function') {
      motionQuery.addEventListener('change', onMotionChange)
    } else {
      motionQuery.addListener(onMotionChange)
    }

    syncIdle()

    return () => {
      observer?.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      hero?.removeEventListener('pointermove', onPointerMove)
      hero?.removeEventListener('pointerleave', onPointerLeave)
      if (typeof motionQuery.removeEventListener === 'function') {
        motionQuery.removeEventListener('change', onMotionChange)
      } else {
        motionQuery.removeListener(onMotionChange)
      }
    }
  }, [])

  return (
    <div
      ref={rootRef}
      className={`lg2-cinematic ${idle ? 'is-idle' : ''}`}
      aria-hidden="true"
    >
      <span className="lg2-cinematic-aurora" />
      <span className="lg2-cinematic-bands" />
      <span className="lg2-cinematic-spots" />
      <span className="lg2-cinematic-refract" />
      <span className="lg2-cinematic-grid" />
      <span className="lg2-cinematic-pointer" />
    </div>
  )
}
