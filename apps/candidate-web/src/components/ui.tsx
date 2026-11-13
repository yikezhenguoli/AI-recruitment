import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'

type Tone = 'ok' | 'warn' | 'danger' | 'muted' | 'brand'

const TONE_CLASSES: Record<Tone, string> = {
  ok: 'border-jade/30 bg-jade-soft text-jade-deep',
  warn: 'border-amber-300/60 bg-amber-50 text-amber-700',
  danger: 'border-rose-300/60 bg-rose-50 text-rose-700',
  muted: 'border-line bg-white/80 text-muted',
  brand: 'border-brand/30 bg-brand-soft text-brand-deep',
}

export function Badge({
  children,
  tone = 'muted',
  dot = false,
}: {
  children: ReactNode
  tone?: Tone
  dot?: boolean
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${TONE_CLASSES[tone]}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
      {children}
    </span>
  )
}

export function ScoreRing({
  score,
  size = 108,
  label = 'AI 匹配度',
}: {
  score: number | null | undefined
  size?: number
  label?: string
}) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = score === null || score === undefined ? 0 : Math.max(0, Math.min(100, score))
  const stroke = score === null || score === undefined ? '#cbd5e1' : clamped >= 70 ? '#12a39b' : clamped >= 45 ? '#2f89d8' : '#e0872f'

  return (
    <div className="flex flex-col items-center gap-1.5" style={{ width: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e6eef6" strokeWidth={9} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={stroke}
            strokeWidth={9}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - clamped / 100)}
            style={{ transition: 'stroke-dashoffset .6s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-extrabold tabular-nums text-ink">
            {score === null || score === undefined ? '—' : clamped.toFixed(1)}
          </span>
          <span className="text-[10px] font-semibold text-muted">/ 100</span>
        </div>
      </div>
      <span className="text-[11px] font-semibold text-muted">{label}</span>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string
  description: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-line bg-white/50 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-brand-deep">
        {icon ?? <Inbox size={22} />}
      </div>
      <div>
        <p className="text-sm font-bold text-ink">{title}</p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function LoadingBlock({ text = '正在加载…' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted">
      <Loader2 size={16} className="animate-spin" />
      {text}
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-2xl border border-rose-200/70 bg-rose-50/80 px-4 py-3 text-xs leading-relaxed text-rose-700">
      <AlertTriangle size={15} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="page-title-jitter mt-2 text-[26px] font-extrabold tracking-tight text-ink sm:text-[30px]">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
