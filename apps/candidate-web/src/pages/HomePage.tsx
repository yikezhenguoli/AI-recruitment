import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BriefcaseBusiness,
  FileText,
  PhoneCall,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { getApplications, getInterviews, getJobs } from '../api/portal'
import type { ApplicationSummary, InterviewSummary, JobCard } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { useAuthStore } from '../store/auth'
import { SoundWave } from '../components/visual/SoundWave'

const STEPS = [
  {
    icon: FileText,
    title: '投递一份简历',
    text: '上传后系统会解析经历与技能，并把每一条结论对应回原文。',
  },
  {
    icon: Sparkles,
    title: '看匹配依据',
    text: '岗位要求逐项对照，匹配分与理由都写在明面上，不是黑箱分数。',
  },
  {
    icon: PhoneCall,
    title: '语音初筛沟通',
    text: '在浏览器里完成一轮结构化问答，转录文本可回看，原始音频默认不留存。',
  },
]

export default function HomePage() {
  const user = useAuthStore((state) => state.user)
  const [jobs, setJobs] = useState<JobCard[]>([])
  const [applications, setApplications] = useState<ApplicationSummary[]>([])
  const [interviews, setInterviews] = useState<InterviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled([getJobs(), getApplications(), getInterviews()])
      .then(([jobsResult, applicationsResult, interviewsResult]) => {
        if (cancelled) return
        if (jobsResult.status === 'fulfilled') setJobs(jobsResult.value)
        else setError(getApiErrorMessage(jobsResult.reason, '岗位数据暂时没有加载出来。'))
        if (applicationsResult.status === 'fulfilled') setApplications(applicationsResult.value)
        if (interviewsResult.status === 'fulfilled') setInterviews(interviewsResult.value)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const activeInterviews = interviews.filter(
    (item) => item.status === 'created' || item.status === 'live',
  ).length
  const appliedJobs = applications.length
  const openJobs = jobs.length

  return (
    <div className="space-y-6">
      <section className="glass-hero px-6 py-8 sm:px-10 sm:py-10">
        <div className="relative grid items-center gap-8 lg:grid-cols-[1.06fr_1fr]">
          <div>
            <p className="eyebrow relative">
              <span className="h-1.5 w-1.5 rounded-full bg-brand" />
              求职者中心 · {user?.display_name ?? '你好'}
            </p>
            <h1 className="page-title-jitter mt-3 text-[30px] font-extrabold leading-[1.16] tracking-tight text-ink sm:text-[38px]">
              把求职，
              <br />
              交给真正会读你的人。
            </h1>
            <p className="mt-4 max-w-lg text-sm leading-relaxed text-muted">
              不是关键词过滤。你的每一段经历都会被理解、被对照到岗位要求上；
              面试前你能看到初始问题，面试中系统会根据回答动态追问，面试后还能回看说了什么。
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/jobs" className="btn-primary">
                浏览在招岗位
                <ArrowRight size={15} />
              </Link>
              <Link to="/applications" className="btn-ghost">
                <FileText size={15} />
                我的投递
              </Link>
            </div>
          </div>

          <div className="relative">
            <div className="sound-stage px-3 pb-2 pt-3 sm:px-5">
              <div className="flex items-center justify-between px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-jade" />
                  AI 语音初筛
                </span>
                <span className="hidden sm:inline">实时声波</span>
              </div>
              <SoundWave height={186} variant="spectrum" label="动态彩色声波示意图" />
              <p className="px-2 pb-2 text-center text-[10.5px] leading-relaxed text-muted">
                麦克风接通后，这段声波会跟着你和面试官的声音一起起伏。
              </p>
            </div>
          </div>
        </div>

        <div className="relative mt-7 grid gap-3 sm:grid-cols-3">
          <Link to="/jobs" className="hero-stat flex items-center gap-3 px-4 py-3.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/12 text-brand-deep">
              <BriefcaseBusiness size={18} />
            </span>
            <span>
              <span className="block text-[22px] font-extrabold leading-none tabular-nums text-ink">
                {loading ? '—' : openJobs}
              </span>
              <span className="mt-1 block text-[10.5px] font-semibold text-muted">在招岗位</span>
            </span>
          </Link>
          <Link to="/applications" className="hero-stat flex items-center gap-3 px-4 py-3.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-jade/12 text-jade-deep">
              <FileText size={18} />
            </span>
            <span>
              <span className="block text-[22px] font-extrabold leading-none tabular-nums text-ink">
                {loading ? '—' : appliedJobs}
              </span>
              <span className="mt-1 block text-[10.5px] font-semibold text-muted">我的投递</span>
            </span>
          </Link>
          <Link to="/interviews" className="hero-stat flex items-center gap-3 px-4 py-3.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/12 text-brand-deep">
              <PhoneCall size={18} />
            </span>
            <span>
              <span className="block text-[22px] font-extrabold leading-none tabular-nums text-ink">
                {loading ? '—' : activeInterviews}
              </span>
              <span className="mt-1 block text-[10.5px] font-semibold text-muted">待进行面试</span>
            </span>
          </Link>
        </div>

        {error && (
          <p className="relative mt-3 text-[11px] text-rose-600">{error}</p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between">
          <div>
            <p className="eyebrow">How it works</p>
            <h2 className="mt-1.5 text-lg font-extrabold tracking-tight text-ink">三步走完初筛</h2>
          </div>
          <Link to="/jobs" className="btn-quiet hidden sm:inline-flex">
            看看岗位
            <ArrowRight size={13} />
          </Link>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <article key={step.title} className="card p-5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand-deep">
                  <step.icon size={17} />
                </span>
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted">
                  Step {index + 1}
                </span>
              </div>
              <h3 className="mt-3 text-sm font-bold text-ink">{step.title}</h3>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="card flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-jade-soft text-jade-deep">
            <ShieldCheck size={17} />
          </span>
          <p className="text-[12px] leading-relaxed text-muted">
            简历处理、语音面试、录音留存都是逐项授权，随时可以在「我的 → 授权与隐私」撤回。
            所有 AI 结论只作参考，最终录用决定由人工做出。
          </p>
        </div>
        <Link to="/profile" className="btn-ghost shrink-0">
          管理授权
        </Link>
      </section>
    </div>
  )
}
