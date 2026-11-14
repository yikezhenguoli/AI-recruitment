import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
}

/**
 * Lightweight homepage section reveal.
 * Content is visible by default; the hidden state is only applied after the
 * component confirms IntersectionObserver + motion support. No reveal in print
 * or under reduced motion. Observes once and unobserves.
 */
export function Reveal({ children, className = '', delay = 0 }: RevealProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const supportsScrollView =
      typeof CSS !== 'undefined' &&
      typeof CSS.supports === 'function' &&
      CSS.supports('(animation-timeline: view()) and (animation-range: entry)')
    if (supportsScrollView) return

    if (typeof IntersectionObserver === 'undefined') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    if (window.matchMedia('print').matches) return

    setReady(true)
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true)
            observer.unobserve(entry.target)
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={`lg2-reveal ${ready ? 'lg2-reveal--ready' : ''} ${visible ? 'is-visible' : ''} ${className}`.trim()}
      style={delay && ready ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  )
}
