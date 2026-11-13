import type { ReactNode } from 'react'
import { BadgeCheck, FileSearch, MessagesSquare, ShieldCheck } from 'lucide-react'

const POINTS = [
  {
    icon: FileSearch,
    title: 'AI 帮你读懂岗位',
    text: '投递前先看到岗位要求的重点，以及你的简历与它的匹配维度。',
  },
  {
    icon: BadgeCheck,
    title: '进度透明',
    text: '简历解析、匹配评估、面试安排，每一步都能在「我的投递」里看到。',
  },
  {
    icon: MessagesSquare,
    title: 'AI 初筛沟通',
    text: '无需奔波，在浏览器里完成一轮结构化语音沟通，节省双方时间。',
  },
  {
    icon: ShieldCheck,
    title: '授权在你手里',
    text: '简历处理、语音面试、录音留存逐项授权，随时可撤回。',
  },
]

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-[#0f2740] px-12 py-14 text-white lg:flex lg:flex-col">
        <div className="pointer-events-none absolute -left-24 top-10 h-72 w-72 animate-breathe rounded-full bg-brand/30 blur-3xl" />
        <div className="pointer-events-none absolute -right-16 bottom-0 h-80 w-80 animate-breathe rounded-full bg-jade/25 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <img src="/ttc-mark.svg" alt="" className="h-11 w-11 rounded-2xl shadow-lg" />
          <div>
            <div className="brand-jitter text-lg font-extrabold tracking-tight">
              TTC <span className="text-sky-200">才多对</span>
            </div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-200/60">
              Talent Trust &amp; Connect
            </div>
          </div>
        </div>

        <div className="relative mt-16 max-w-lg">
          <p className="text-[11px] font-bold uppercase tracking-[0.26em] text-sky-200/70">
            求职者中心
          </p>
          <h1 className="page-title-jitter mt-3 text-[34px] font-extrabold leading-[1.18] tracking-tight text-balance">
            把简历交给
            <br />
            真正会读它的人。
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-sky-100/75">
            不是关键词过滤，而是理解你的经历与岗位要求之间的关系。你可以看到每一次评估的依据，
            也可以随时收回授权。
          </p>
        </div>

        <ul className="relative mt-10 grid gap-4 sm:grid-cols-2">
          {POINTS.map((point) => (
            <li key={point.title} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <point.icon size={18} className="text-sky-200" />
              <p className="mt-2 text-sm font-bold">{point.title}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-sky-100/60">{point.text}</p>
            </li>
          ))}
        </ul>

        <p className="relative mt-auto pt-10 text-[11px] text-sky-100/40">
          © 2026 TTC · AI 辅助决策，人工最终复核
        </p>
      </aside>

      <section className="flex min-h-screen items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-[460px]">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <img src="/ttc-mark.svg" alt="" className="h-11 w-11 rounded-2xl shadow-soft" />
            <div>
              <div className="text-[17px] font-extrabold tracking-tight text-ink">
                TTC <span className="text-brand-deep">才多对</span>
              </div>
              <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted">
                求职者中心
              </div>
            </div>
          </div>
          {children}
        </div>
      </section>
    </div>
  )
}
