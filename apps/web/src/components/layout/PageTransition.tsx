import { useEffect, useRef, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { useLocation } from 'react-router-dom'

interface PageTransitionProps {
  children: ReactNode
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => { finished: Promise<void> }
}

/**
 * Wrap discrete React view updates (filter switches, view mode changes) in a
 * Same-Document View Transition while cleaning up temporary transition names
 * once finished so at most one snapshot claims a given name.
 */
export function runViewTransition(update: () => void, target?: HTMLElement | null) {
  const doc = typeof document !== 'undefined' ? (document as ViewTransitionDocument) : null
  const reduced =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (!doc || typeof doc.startViewTransition !== 'function' || reduced) {
    update()
    return
  }

  if (target) {
    target.style.viewTransitionName = 'page-canvas'
  }

  const transition = doc.startViewTransition(() => {
    flushSync(update)
  })

  void transition.finished.finally(() => {
    if (target) {
      target.style.viewTransitionName = ''
    }
  })
}

export function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation()
  const containerRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(false)

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true
      return
    }
    const frame = window.requestAnimationFrame(() => {
      const root = containerRef.current
      if (!root) return
      const heading = root.querySelector<HTMLElement>('h1')
      const target = heading ?? root
      if (!target.hasAttribute('tabindex')) {
        target.setAttribute('tabindex', '-1')
      }
      target.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname])

  return (
    <div ref={containerRef} className="ttc-page-transition" key={location.pathname}>
      {children}
    </div>
  )
}
