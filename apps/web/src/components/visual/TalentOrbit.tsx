import { useEffect, useRef, useState } from 'react'
import type {
  FocusEvent as ReactFocusEvent,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  TouchEvent as ReactTouchEvent,
} from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  FileText,
  Filter,
  Pause,
  Play,
  Search,
  Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface OrbitItem {
  title: string
  description: string
  tag: string
  action: string
  to: string
  icon: LucideIcon
}

const ORBIT_ITEMS: OrbitItem[] = [
  {
    title: '岗位画像与权重',
    description: '管理多版本 JD 与核心维度权重，生成结构化筛选标准。',
    tag: 'JD → 权重维度',
    action: '新建岗位',
    to: '/jobs/new',
    icon: Search,
  },
  {
    title: '简历核验与证据链',
    description: '上传 PDF / DOCX 并追踪 WebSocket 处理进度，分级核验经历声明。',
    tag: '声明 → 证据分级',
    action: '查看候选人',
    to: '/candidates',
    icon: Filter,
  },
  {
    title: '语音初筛与双账本报告',
    description: '实时语音访谈结合证据可信度、岗位匹配分，由人工完成最终复核。',
    tag: '语音初筛 → 人工复核',
    action: '语音初筛',
    to: '/sessions',
    icon: FileText,
  },
]

/** Fixed orbital slots: top, bottom-right, bottom-left (percent of the square stage). */
const NODE_SLOTS = [
  { left: '50%', top: '11%' },
  { left: '82.4%', top: '69.5%' },
  { left: '17.6%', top: '69.5%' },
]

const LINK_ENDS = [
  { x: 50, y: 11 },
  { x: 82.4, y: 69.5 },
  { x: 17.6, y: 69.5 },
]

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia(query).matches,
  )

  useEffect(() => {
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [query])

  return matches
}

function NodeGlyph({ item }: { item: OrbitItem }) {
  const Icon = item.icon
  return (
    <>
      <span className="lg2-orbit2-node-icon">
        <Icon size={17} aria-hidden="true" />
      </span>
      <span className="lg2-orbit2-node-text">
        <strong>{item.title}</strong>
        <span>
          {item.action}
          <ArrowUpRight size={12} aria-hidden="true" />
        </span>
      </span>
    </>
  )
}

/**
 * Talent Signal Orbit 2.0 — homepage-only brand instrument.
 *
 * - Three clickable capability nodes on a multi-ring orbital stage; each links
 *   to its real workflow route. Capability copy only, never live statistics.
 * - Auto-advance every 6s with an explicit pause/play control; pauses on hover,
 *   focus-within, tab hidden and while off-screen.
 * - Slow, independent ring speeds; restrained glow; pointer-driven 3D parallax
 *   (mouse only) disabled for touch and reduced motion.
 * - Keyboard Left/Right and touch swipe; static linked-card fallback on mobile
 *   and under `prefers-reduced-motion: reduce`.
 */
export function TalentOrbit() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const narrow = useMediaQuery('(max-width: 767px)')
  const staticMode = reduced || narrow

  const rootRef = useRef<HTMLDivElement | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const touchStartX = useRef<number | null>(null)

  const [active, setActive] = useState(0)
  const [hovered, setHovered] = useState<number | null>(null)
  const [userPaused, setUserPaused] = useState(false)
  const [pointerInside, setPointerInside] = useState(false)
  const [focusWithin, setFocusWithin] = useState(false)
  const [pageHidden, setPageHidden] = useState(
    () => typeof document !== 'undefined' && document.visibilityState === 'hidden',
  )
  const [inView, setInView] = useState(true)

  const paused = userPaused || pointerInside || focusWithin || pageHidden || !inView
  const displayIndex = hovered ?? active
  const displayItem = ORBIT_ITEMS[displayIndex]

  useEffect(() => {
    const onVisibility = () => setPageHidden(document.visibilityState === 'hidden')
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  useEffect(() => {
    const node = rootRef.current
    if (!node || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry) setInView(entry.isIntersecting)
      },
      { threshold: 0.08 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (staticMode || paused) return
    const timer = window.setTimeout(() => {
      setActive((current) => (current + 1) % ORBIT_ITEMS.length)
    }, 6000)
    return () => window.clearTimeout(timer)
  }, [staticMode, paused, active])

  const goTo = (index: number) => {
    setActive(((index % ORBIT_ITEMS.length) + ORBIT_ITEMS.length) % ORBIT_ITEMS.length)
  }

  const move = (direction: number) => goTo(active + direction)

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      move(-1)
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      move(1)
    }
  }

  const onBlurCapture = (event: ReactFocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setFocusWithin(false)
      setHovered(null)
    }
  }

  const onTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    touchStartX.current = event.touches[0]?.clientX ?? null
  }

  const onTouchEnd = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (touchStartX.current == null) return
    const endX = event.changedTouches[0]?.clientX ?? touchStartX.current
    const delta = endX - touchStartX.current
    touchStartX.current = null
    if (Math.abs(delta) < 38) return
    move(delta < 0 ? 1 : -1)
  }

  const onStagePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (reduced || event.pointerType !== 'mouse') return
    const stage = stageRef.current
    if (!stage) return
    const rect = stage.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    const x = (event.clientX - rect.left) / rect.width - 0.5
    const y = (event.clientY - rect.top) / rect.height - 0.5
    stage.style.setProperty('--lg2-rx', `${(-y * 5).toFixed(2)}deg`)
    stage.style.setProperty('--lg2-ry', `${(x * 5).toFixed(2)}deg`)
  }

  const resetStageTilt = () => {
    const stage = stageRef.current
    if (!stage) return
    stage.style.setProperty('--lg2-rx', '0deg')
    stage.style.setProperty('--lg2-ry', '0deg')
  }

  if (staticMode) {
    return (
      <div ref={rootRef} className="lg2-orbit2 lg2-orbit2--static">
        <div className="lg2-orbit2-static-head">
          <span className="lg2-orbit2-static-core" aria-hidden="true">
            <Sparkles size={14} />
            <strong>AI CORE</strong>
          </span>
          <span className="lg2-orbit2-static-line" aria-hidden="true" />
          <span className="lg2-orbit2-note">点击节点进入对应流程</span>
        </div>

        <div className="lg2-orbit2-static" aria-label="AI 招聘工作流示意：三个能力节点">
          {ORBIT_ITEMS.map((item, index) => {
            const Icon = item.icon
            return (
              <Link
                key={item.title}
                to={item.to}
                className="lg2-orbit2-static-card"
                aria-label={`${item.title}：${item.description} ${item.action}`}
              >
                <span className="lg2-orbit2-static-top">
                  <span className="lg2-orbit2-static-index">
                    NODE {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="lg2-orbit2-static-icon">
                    <Icon size={16} aria-hidden="true" />
                  </span>
                </span>
                <strong>{item.title}</strong>
                <span className="lg2-orbit2-static-desc">{item.description}</span>
                <span className="lg2-orbit2-static-action">
                  {item.action}
                  <ArrowRight size={14} aria-hidden="true" />
                </span>
              </Link>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      className={`lg2-orbit2 ${paused ? 'is-paused' : ''} ${inView ? 'is-inview' : 'is-offscreen'}`}
      role="group"
      aria-roledescription="工作流轨道"
      aria-label="AI 招聘工作流示意，三个能力节点"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setPointerInside(true)}
      onMouseLeave={() => {
        setPointerInside(false)
        setHovered(null)
      }}
      onFocusCapture={() => setFocusWithin(true)}
      onBlurCapture={onBlurCapture}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <div className="lg2-orbit2-stagewrap">
        <div
          className="lg2-orbit2-stage"
          ref={stageRef}
          onPointerMove={onStagePointerMove}
          onPointerLeave={resetStageTilt}
        >
          <div className="lg2-orbit2-world">
            <span className="lg2-orbit2-ambient" aria-hidden="true" />

            <svg
              className="lg2-orbit2-paths"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              aria-hidden="true"
              focusable="false"
            >
              <circle
                cx="50"
                cy="50"
                r="44"
                className="lg2-orbit2-path lg2-orbit2-path--outer"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx="50"
                cy="50"
                r="32"
                className="lg2-orbit2-path lg2-orbit2-path--mid"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx="50"
                cy="50"
                r="21"
                className="lg2-orbit2-path lg2-orbit2-path--inner"
                vectorEffect="non-scaling-stroke"
              />
            </svg>

            <span className="lg2-orbit2-arc lg2-orbit2-arc--a" aria-hidden="true" />
            <span className="lg2-orbit2-arc lg2-orbit2-arc--b" aria-hidden="true" />

            <div
              className="lg2-orbit2-rotor"
              style={{ transform: `rotate(${-active * 120}deg)` }}
            >
              <svg
                className="lg2-orbit2-links"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                aria-hidden="true"
                focusable="false"
              >
                {ORBIT_ITEMS.map((item, index) => (
                  <line
                    key={item.title}
                    x1="50"
                    y1="50"
                    x2={LINK_ENDS[index].x}
                    y2={LINK_ENDS[index].y}
                    className={`lg2-orbit2-link ${index === displayIndex ? 'is-active' : ''}`}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              </svg>

              {ORBIT_ITEMS.map((item, index) => (
                <div
                  className="lg2-orbit2-node-slot"
                  key={item.title}
                  style={{
                    left: NODE_SLOTS[index].left,
                    top: NODE_SLOTS[index].top,
                  }}
                >
                  <div
                    className="lg2-orbit2-node-counter"
                    style={{ transform: `rotate(${active * 120}deg)` }}
                  >
                    <Link
                      to={item.to}
                      className={`lg2-orbit2-node ${index === active ? 'is-active' : ''} ${
                        index === displayIndex ? 'is-current' : ''
                      }`}
                      aria-label={`${item.title}：${item.description} ${item.action}`}
                      aria-current={index === active ? 'step' : undefined}
                      onPointerEnter={(event) => {
                        if (event.pointerType === 'mouse') setHovered(index)
                      }}
                      onPointerLeave={() => setHovered(null)}
                      onFocus={() => setHovered(index)}
                    >
                      <NodeGlyph item={item} />
                    </Link>
                  </div>
                </div>
              ))}
            </div>

            <div className="lg2-orbit2-core" aria-hidden="true">
              <span className="lg2-orbit2-core-halo" />
              <span className="lg2-orbit2-core-ring" />
              <span className="lg2-orbit2-core-body">
                <Sparkles size={18} />
                <strong>AI</strong>
                <em>CORE</em>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="lg2-orbit2-readout">
        <span className="lg2-orbit2-readout-index">
          NODE {String(displayIndex + 1).padStart(2, '0')}
        </span>
        <div className="lg2-orbit2-readout-copy">
          <strong>{displayItem.title}</strong>
          <span>{displayItem.description}</span>
        </div>
        <Link to={displayItem.to} className="lg2-orbit2-readout-link">
          {displayItem.action}
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </div>

      <div className="lg2-orbit2-footer">
        <span className="lg2-orbit2-caption">
          <span className="lg2-orbit2-caption-dot" aria-hidden="true" />
          {userPaused ? '已暂停' : '自动轮播 6s'} · 悬停或聚焦暂停
        </span>
        <div className="lg2-orbit2-controls" role="group" aria-label="工作流轨道控制">
          <button
            type="button"
            className="lg2-orbit2-control"
            onClick={() => move(-1)}
            aria-label="上一个工作流节点"
            title="上一个工作流节点"
          >
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`lg2-orbit2-control ${userPaused ? 'is-paused' : ''}`}
            onClick={() => setUserPaused((current) => !current)}
            aria-label={userPaused ? '继续自动轮播' : '暂停自动轮播'}
            title={userPaused ? '继续自动轮播' : '暂停自动轮播'}
          >
            {userPaused ? (
              <Play size={16} aria-hidden="true" />
            ) : (
              <Pause size={16} aria-hidden="true" />
            )}
          </button>
          <button
            type="button"
            className="lg2-orbit2-control"
            onClick={() => move(1)}
            aria-label="下一个工作流节点"
            title="下一个工作流节点"
          >
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}
