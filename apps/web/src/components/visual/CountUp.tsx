import { useEffect, useRef, useState } from 'react'

interface CountUpProps {
  /** Real numeric value only — never a placeholder metric. */
  value: number
  duration?: number
  className?: string
  ariaLabel?: string
}

function reduceMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Animated numeric display for real values. The final value is always exact.
 * Reduced motion renders the final value immediately.
 */
export function CountUp({
  value,
  duration = 900,
  className = '',
  ariaLabel,
}: CountUpProps) {
  const [display, setDisplay] = useState(() => (reduceMotion() ? value : 0))
  const displayedRef = useRef(reduceMotion() ? value : 0)

  useEffect(() => {
    const from = displayedRef.current
    const to = value

    if (from === to) return

    if (reduceMotion()) {
      displayedRef.current = to
      setDisplay(to)
      return
    }

    let raf = 0
    const started = performance.now()
    const safeDuration = Math.min(1100, Math.max(800, duration))

    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / safeDuration)
      const eased = 1 - Math.pow(1 - progress, 3)
      const next = Math.round(from + (to - from) * eased)
      displayedRef.current = next
      setDisplay(next)

      if (progress < 1) {
        raf = window.requestAnimationFrame(tick)
      } else {
        displayedRef.current = to
        setDisplay(to)
      }
    }

    raf = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(raf)
  }, [value, duration])

  return (
    <span
      className={`lg2-count ${className}`}
      aria-label={ariaLabel ?? String(value)}
    >
      <span aria-hidden="true">{display.toLocaleString('zh-CN')}</span>
    </span>
  )
}
