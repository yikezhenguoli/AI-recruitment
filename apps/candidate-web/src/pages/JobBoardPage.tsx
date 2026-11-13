import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  PhoneCall,
  Search,
  Sparkles,
  Users,
} from 'lucide-react'
import { getApplications, getInterviews, getJobs } from '../api/portal'
import type { ApplicationSummary, InterviewSummary, JobCard } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDate } from '../lib/format'
import { useAuthStore } from '../store/auth'
import { Badge, EmptyState, ErrorNote, LoadingBlock, PageHeader } from '../components/ui'

export default function JobBoardPage() {
  const user = useAuthStore((state) => state.user)
  const [jobs, setJobs] = useState<JobCard[]>([])
  const [applications, setApplications] = useState<ApplicationSummary[]>([])
  const [interviews, setInterviews] = useState<InterviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [department, setDepartment] = useState<string>('全部')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled([getJobs(), getApplications(), getInterviews()])
      .then(([jobsResult, applicationsResult, interviewsResult]) => {
        if (cancelled) return
        if (jobsResult.status === 'fulfilled') {
          setJobs(jobsResult.value)
          setError(null)
        } else {
          setError(getApiErrorMessage(jobsResult.reason, '岗位列表加载失败。'))
        }
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

  const departments = useMemo(() => {
    const set = new Set<string>()
    jobs.forEach((job) => job.department && set.add(job.department))
    return ['全部', ...Array.from(set)]
  }, [jobs])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return jobs.filter((job) => {
      if (department !== '全部' && job.department !== department) return false
      if (!needle) return true
      return (
        job.title.toLowerCase().includes(needle) ||
        job.summary.toLowerCase().includes(needle) ||
        job.skills.some((skill) => skill.toLowerCase().includes(needle))
      )
    })
  }, [jobs, query, department])

  const activeInterviews = interviews.filter(
    (item) => item.status === 'created' || item.status === 'live',
  ).length

  return (
    <div>
      <PageHeader
        eyebrow="Job Board"
        title={`你好，${user?.display_name ?? '求职者'}`}
        description="浏览当前开放的岗位，上传一次简历即可投递多个职位。匹配结果是辅助信息，不替代人工判断。"
        actions={
          <Link to="/applications" className="btn-ghost">
            <CheckCircle2 size={15} />
            查看我的投递
          </Link>
        }
      />

      <section className="mb-8 grid gap-3 sm:grid-cols-3">
        <StatCard icon={<BriefcaseBusiness size={17} />} label="在招岗位" value={jobs.length} tone="brand" />
        <StatCard icon={<CheckCircle2 size={17} />} label="我的投递" value={applications.length} tone="jade" />
        <StatCard icon={<PhoneCall size={17} />} label="待进行面试" value={activeInterviews} tone="amber" />
      </section>

      <section className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="input pl-10"
            placeholder="搜索岗位名称、技能或职责关键词"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {departments.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setDepartment(item)}
              className={`chip transition ${department === item ? 'chip-active' : 'hover:border-brand/30'}`}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div className="mb-4">
          <ErrorNote message={error} />
        </div>
      )}

      {loading ? (
        <LoadingBlock text="正在加载开放岗位…" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<BriefcaseBusiness size={22} />}
          title={jobs.length === 0 ? '当前没有开放岗位' : '没有匹配的岗位'}
          description={
            jobs.length === 0
              ? '企业还没有发布岗位。稍后再来看看，或联系招聘方确认。'
              : '试试更换部门筛选，或清空搜索关键词。'
          }
          action={
            jobs.length > 0 ? (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setQuery('')
                  setDepartment('全部')
                }}
              >
                清空筛选
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((job) => (
            <Link
              key={job.id}
              to={`/jobs/${job.id}`}
              className="group card-tight flex flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-card"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-[15px] font-extrabold leading-snug text-ink group-hover:text-brand-deep">
                    {job.title}
                  </h2>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    {job.department && (
                      <span className="inline-flex items-center gap-1">
                        <Building2 size={12} />
                        {job.department}
                      </span>
                    )}
                    {job.headcount ? (
                      <span className="inline-flex items-center gap-1">
                        <Users size={12} />
                        招 {job.headcount} 人
                      </span>
                    ) : null}
                  </div>
                </div>
                {job.applied ? (
                  <Badge tone="ok" dot>已投递</Badge>
                ) : (
                  <ArrowUpRight size={17} className="shrink-0 text-muted/60 transition group-hover:text-brand-deep" />
                )}
              </div>

              <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-muted">{job.summary || '暂无岗位描述'}</p>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {job.skills.slice(0, 4).map((skill) => (
                  <span key={skill} className="chip">{skill}</span>
                ))}
              </div>

              <div className="mt-auto flex items-center justify-between pt-4 text-[11px] text-muted">
                <span>发布于 {formatDate(job.published_at)}</span>
                <span className="inline-flex items-center gap-1 font-semibold text-brand-deep">
                  查看详情 <ArrowUpRight size={12} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <section className="card mt-8 flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-jade-soft text-jade-deep">
            <Sparkles size={18} />
          </span>
          <div>
            <p className="text-sm font-bold text-ink">匹配分是怎么来的？</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
              系统用小模型读取你的简历与岗位描述，给出 0–100 的相似度，并列出优势、缺口与待核实项。
              它只做初筛参考，最终判断由招聘人员完成。
            </p>
          </div>
        </div>
        <Link to="/profile" className="btn-ghost shrink-0">
          管理我的授权
        </Link>
      </section>
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode
  label: string
  value: number
  tone: 'brand' | 'jade' | 'amber'
}) {
  const toneClass =
    tone === 'brand'
      ? 'bg-brand-soft text-brand-deep'
      : tone === 'jade'
        ? 'bg-jade-soft text-jade-deep'
        : 'bg-amber-50 text-amber-700'
  return (
    <div className="card-tight flex items-center gap-3 p-4">
      <span className={`flex h-10 w-10 items-center justify-center rounded-2xl ${toneClass}`}>{icon}</span>
      <div>
        <div className="text-xl font-extrabold tabular-nums text-ink">{value}</div>
        <div className="text-[11px] font-semibold text-muted">{label}</div>
      </div>
    </div>
  )
}
