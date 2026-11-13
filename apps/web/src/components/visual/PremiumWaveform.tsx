import { useEffect, useId, useRef, useState } from 'react'

export interface PremiumWaveformProps {
  className?: string
  height?: number
  tone?: 'hero' | 'subtle'
  label?: string
  /**
   * true  = user explicitly enables motion (overrides reduced-motion for this
   *         decorative band only); false = static; undefined = follow the OS.
   */
  motionOverride?: boolean
}

/**
 * Internal reduced-motion listener. The stylesheet also disables animation via
 * its own media query; this hook keeps the class/state in sync for consumers
 * and for browsers where the query changes at runtime. Cleaned up on unmount.
 */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = (matches: boolean) => setReduced(matches)
    sync(query.matches)

    const onChange = (event: MediaQueryListEvent) => sync(event.matches)

    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', onChange)
      return () => query.removeEventListener('change', onChange)
    }

    // Legacy Safari fallback.
    query.addListener(onChange)
    return () => query.removeListener(onChange)
  }, [])

  return reduced
}

const WAVEFORM_STYLES = `
.pwf-root {
  --pwf-intensity: 1;
  --pwf-glow-opacity: 1;
  position: relative;
  display: block;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
  isolation: isolate;
  border-radius: inherit;
}

.pwf-root--subtle {
  --pwf-intensity: 0.92;
  --pwf-glow-opacity: 0.78;
}

.pwf-svg {
  display: block;
  width: 100%;
  height: 100%;
}

.pwf-scene {
  opacity: var(--pwf-intensity);
}

.pwf-layer,
.pwf-glow {
  transform-box: fill-box;
  transform-origin: center;
  will-change: transform;
}

.pwf-glow {
  opacity: var(--pwf-glow-opacity);
  animation: pwf-drift-glow 12s cubic-bezier(0.42, 0.08, 0.58, 0.92) -6.75s infinite alternate;
}

/* Each layer runs on its own clock: negative delays offset the phases so the
   stack never moves as one rigid block. The vertical travel sits at roughly
   30-38 user units plus a 7.5-13.5% scaleY breath: quick enough to read as
   motion at a glance, still eased so it never snaps or jitters. */
.pwf-layer--back {
  animation: pwf-drift-back 9s cubic-bezier(0.42, 0.08, 0.58, 0.92) -4.5s infinite alternate;
}

.pwf-layer--mid {
  animation: pwf-drift-mid 7s cubic-bezier(0.42, 0.08, 0.58, 0.92) -5.25s infinite alternate;
}

.pwf-layer--front {
  animation: pwf-drift-front 6s cubic-bezier(0.42, 0.08, 0.58, 0.92) -1.75s infinite alternate;
}

.pwf-layer--sheen {
  animation:
    pwf-drift-sheen 6.5s cubic-bezier(0.42, 0.08, 0.58, 0.92) -4.5s infinite alternate,
    pwf-sheen-pulse 5.5s ease-in-out -2s infinite alternate;
}

/* Slow, silky breathing: broad vertical undulation plus a gentle vertical
   stretch. Transform/opacity only, so the band never changes layout height. */
@keyframes pwf-drift-glow {
  0% { transform: translate3d(-28px, 30px, 0) scale(0.97); }
  50% { transform: translate3d(14px, -36px, 0) scale(1.06); }
  100% { transform: translate3d(32px, -10px, 0) scale(1.0); }
}

@keyframes pwf-drift-back {
  0% { transform: translate3d(-38px, 36px, 0) scale(1.01, 1.075); }
  50% { transform: translate3d(26px, -38px, 0) scale(1.02, 1.135); }
  100% { transform: translate3d(44px, 26px, 0) scale(1.015, 1.09); }
}

@keyframes pwf-drift-mid {
  0% { transform: translate3d(32px, -38px, 0) scale(1.012, 1.12); }
  50% { transform: translate3d(-20px, 36px, 0) scale(1.02, 1.08); }
  100% { transform: translate3d(-42px, -24px, 0) scale(1.015, 1.105); }
}

@keyframes pwf-drift-front {
  0% { transform: translate3d(-28px, 30px, 0) scale(1.01, 1.075); }
  50% { transform: translate3d(24px, -36px, 0) scale(1.018, 1.13); }
  100% { transform: translate3d(38px, 36px, 0) scale(1.014, 1.095); }
}

@keyframes pwf-drift-sheen {
  0% { transform: translate3d(30px, 30px, 0); }
  50% { transform: translate3d(-16px, -36px, 0); }
  100% { transform: translate3d(-34px, -8px, 0); }
}

@keyframes pwf-sheen-pulse {
  0% { opacity: 0.52; }
  50% { opacity: 1; }
  100% { opacity: 0.7; }
}

.pwf-visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.pwf-root--static .pwf-layer,
.pwf-root--static .pwf-glow {
  animation: none !important;
  will-change: auto;
}

.pwf-root--paused .pwf-layer,
.pwf-root--paused .pwf-glow {
  animation-play-state: paused;
}

@media (prefers-reduced-motion: reduce) {
  .pwf-root:not(.pwf-root--force-motion) .pwf-layer,
  .pwf-root:not(.pwf-root--force-motion) .pwf-glow {
    animation: none !important;
    will-change: auto;
  }
}

/* The project-wide reduced-motion rule shortens every animation to .01ms and
   one iteration. When the owner explicitly enables this decorative band, keep
   its slow durations and infinite loop so the toggle has a real effect. */
.pwf-root--force-motion .pwf-glow {
  animation-duration: 12s !important;
  animation-iteration-count: infinite !important;
}
.pwf-root--force-motion .pwf-layer--back {
  animation-duration: 9s !important;
  animation-iteration-count: infinite !important;
}
.pwf-root--force-motion .pwf-layer--mid {
  animation-duration: 7s !important;
  animation-iteration-count: infinite !important;
}
.pwf-root--force-motion .pwf-layer--front {
  animation-duration: 6s !important;
  animation-iteration-count: infinite !important;
}
.pwf-root--force-motion .pwf-layer--sheen {
  animation-duration: 6.5s, 5.5s !important;
  animation-iteration-count: infinite, infinite !important;
}
`

/**
 * PremiumWaveform
 *
 * Purely decorative, self-contained ambient waveform for the workbench
 * homepage. Four layered SVG wave paths drift slowly behind a horizontal
 * edge mask so the graphic dissolves into the surrounding page.
 *
 * - No data, labels, axes, tooltips or live metrics.
 * - Static when `prefers-reduced-motion: reduce`.
 * - Transform/opacity-only CSS animation; no canvas, rAF or scroll listeners.
 * - The root is `aria-hidden` because the graphic is atmospheric only.
 */
export function PremiumWaveform({
  className = '',
  height,
  tone = 'hero',
  label = 'Ambient signal',
  motionOverride,
}: PremiumWaveformProps) {
  const reducedMotion = usePrefersReducedMotion()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [paused, setPaused] = useState(false)
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const scope = `pwf-${uid}`
  const resolvedHeight = height ?? (tone === 'hero' ? 240 : 148)
  const staticMotion =
    motionOverride === false || (motionOverride !== true && reducedMotion)
  const rootClassName = [
    'pwf-root',
    tone === 'hero' ? 'pwf-root--hero' : 'pwf-root--subtle',
    staticMotion ? 'pwf-root--static' : '',
    motionOverride === true ? 'pwf-root--force-motion' : '',
    paused ? 'pwf-root--paused' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  // Pause the slow drift while the band is off-screen or the tab is hidden.
  useEffect(() => {
    const node = rootRef.current
    if (!node) return

    let inView = true
    let pageVisible = document.visibilityState !== 'hidden'
    const sync = () => setPaused(!inView || !pageVisible)

    const onVisibility = () => {
      pageVisible = document.visibilityState !== 'hidden'
      sync()
    }

    const observer =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(
            (entries) => {
              inView = entries.some((entry) => entry.isIntersecting)
              sync()
            },
            { threshold: 0.02 },
          )

    observer?.observe(node)
    document.addEventListener('visibilitychange', onVisibility)
    sync()

    return () => {
      observer?.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <div
      ref={rootRef}
      className={rootClassName}
      style={{ height: resolvedHeight, pointerEvents: 'none' }}
      aria-hidden="true"
      data-tone={tone}
    >
      <style>{WAVEFORM_STYLES}</style>
      <span className="pwf-visually-hidden">{label}</span>

      <svg
        className="pwf-svg"
        viewBox="0 0 1200 320"
        preserveAspectRatio="none"
        focusable="false"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`${scope}-edge-fade`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#000000" />
            <stop offset="0.07" stopColor="#737373" />
            <stop offset="0.16" stopColor="#ffffff" />
            <stop offset="0.84" stopColor="#ffffff" />
            <stop offset="0.93" stopColor="#737373" />
            <stop offset="1" stopColor="#000000" />
          </linearGradient>

          <mask
            id={`${scope}-edge-mask`}
            maskUnits="userSpaceOnUse"
            x="0"
            y="0"
            width="1200"
            height="320"
          >
            <rect width="1200" height="320" fill={`url(#${scope}-edge-fade)`} />
          </mask>

          <radialGradient id={`${scope}-glow`} cx="50%" cy="62%" r="58%">
            <stop offset="0" stopColor="#BFE4FA" stopOpacity="0.5" />
            <stop offset="0.6" stopColor="#BFE4FA" stopOpacity="0.14" />
            <stop offset="1" stopColor="#BFE4FA" stopOpacity="0" />
          </radialGradient>

          <linearGradient
            id={`${scope}-fill-back`}
            gradientUnits="userSpaceOnUse"
            x1="0"
            y1="128"
            x2="0"
            y2="320"
          >
            <stop offset="0" stopColor="#D9EFFC" stopOpacity="0.8" />
            <stop offset="0.48" stopColor="#A6D9F4" stopOpacity="0.3" />
            <stop offset="1" stopColor="#E7F5FE" stopOpacity="0" />
          </linearGradient>

          <linearGradient
            id={`${scope}-fill-mid`}
            gradientUnits="userSpaceOnUse"
            x1="0"
            y1="168"
            x2="0"
            y2="320"
          >
            <stop offset="0" stopColor="#8CCFF1" stopOpacity="0.58" />
            <stop offset="0.5" stopColor="#58B0E4" stopOpacity="0.22" />
            <stop offset="1" stopColor="#BFE4FA" stopOpacity="0" />
          </linearGradient>

          <linearGradient
            id={`${scope}-fill-front`}
            gradientUnits="userSpaceOnUse"
            x1="0"
            y1="218"
            x2="0"
            y2="320"
          >
            <stop offset="0" stopColor="#3E9AD6" stopOpacity="0.42" />
            <stop offset="0.55" stopColor="#1573B8" stopOpacity="0.16" />
            <stop offset="1" stopColor="#7FC4E8" stopOpacity="0" />
          </linearGradient>

          <linearGradient
            id={`${scope}-sheen`}
            gradientUnits="userSpaceOnUse"
            x1="60"
            y1="0"
            x2="1140"
            y2="0"
          >
            <stop offset="0" stopColor="#9ADCF5" stopOpacity="0" />
            <stop offset="0.18" stopColor="#9ADCF5" stopOpacity="0.44" />
            <stop offset="0.5" stopColor="#F4FCFF" stopOpacity="0.88" />
            <stop offset="0.82" stopColor="#7FD6F2" stopOpacity="0.44" />
            <stop offset="1" stopColor="#9ADCF5" stopOpacity="0" />
          </linearGradient>
        </defs>

        <g mask={`url(#${scope}-edge-mask)`}>
          <g className="pwf-scene">
            <g className="pwf-glow">
              <ellipse cx="600" cy="200" rx="560" ry="150" fill={`url(#${scope}-glow)`} />
            </g>

            <g className="pwf-layer pwf-layer--back">
              <path
                d="M -160 204 C -30 168 86 238 220 214 C 352 190 468 126 616 150 C 762 174 862 236 998 214 C 1116 195 1248 150 1360 172 L 1360 360 L -160 360 Z"
                fill={`url(#${scope}-fill-back)`}
              />
            </g>

            <g className="pwf-layer pwf-layer--mid">
              <path
                d="M -160 246 C -24 214 108 268 244 246 C 386 223 500 170 646 192 C 788 214 900 270 1038 248 C 1160 229 1260 192 1360 210 L 1360 360 L -160 360 Z"
                fill={`url(#${scope}-fill-mid)`}
              />
            </g>

            <g className="pwf-layer pwf-layer--front">
              <path
                d="M -160 288 C -40 266 108 300 252 284 C 396 268 534 232 682 248 C 828 264 954 302 1094 286 C 1212 272 1298 250 1360 258 L 1360 360 L -160 360 Z"
                fill={`url(#${scope}-fill-front)`}
              />
            </g>

            <g className="pwf-layer pwf-layer--sheen">
              <path
                d="M -160 228 C -24 196 108 250 244 228 C 386 205 500 152 646 174 C 788 196 900 252 1038 230 C 1160 211 1260 174 1360 192"
                fill="none"
                stroke={`url(#${scope}-sheen)`}
                strokeWidth="1.4"
                strokeLinecap="round"
                opacity="0.72"
                vectorEffect="non-scaling-stroke"
              />
            </g>
          </g>
        </g>
      </svg>
    </div>
  )
}
