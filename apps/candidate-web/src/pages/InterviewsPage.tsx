import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CalendarClock, ListChecks, PhoneCall } from 'lucide-react'
import { getInterviews } from '../api/portal'
import type { InterviewSummary } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { INTERVIEW_STATUS, SCENARIO_LABEL } from '../lib/labels'
import { Badge, EmptyState, ErrorNote, LoadingBlock, PageHeader } from '../components/ui'

export default function InterviewsPage() {
  const [items, setItems] = useState<InterviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getInterviews()
      .then((data) => {
        if (!cancelled) {
          setItems(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getApiErrorMessage(err, '面试安排加载失败。'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <PageHeader
        eyebrow="Interviews"
        title="我的面试"
        description="AI 初筛沟通由招聘方发起。开始前需要你单独授予语音面试授权，可以随时撤回。"
        actions={
          <Link to="/applications" className="btn-ghost">
            查看投递
            <ArrowRight size={15} />
          </Link>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {loading ? (
        <LoadingBlock text="正在加载面试安排…" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<PhoneCall size={22} />}
          title="暂无面试安排"
          description="招聘人员在复核简历与匹配评估后，可能会为你安排一轮 AI 初筛沟通。安排出现时会显示在这里，并附上需要你确认的授权项。"
          action={
            <Link to="/applications" className="btn-primary">
              关注我的投递
              <ArrowRight size={15} />
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((item) => {
            const meta = INTERVIEW_STATUS[item.status] ?? { label: item.status, tone: 'muted' as const }
            return (
              <Link
                key={item.id}
                to={`/interviews/${item.id}`}
                className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-card sm:p-6"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
                      {SCENARIO_LABEL[item.scenario] ?? item.scenario}
                    </p>
                    <h2 className="mt-1 text-[16px] font-extrabold text-ink group-hover:text-brand-deep">
                      {item.title}
                    </h2>
                  </div>
                  <Badge tone={meta.tone} dot>{meta.label}</Badge>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 text-[11px] text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    <CalendarClock size={13} />
                    {formatDateTime(item.created_at)}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <ListChecks size={13} />
                    {item.question_count} 个问题 · 最长 {Math.round(item.max_seconds / 60)} 分钟
                  </span>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-line/70 pt-3 text-[11px]">
                  <span className="text-muted">点击查看问题清单与状态</span>
                  <span className="inline-flex items-center gap-1 font-semibold text-brand-deep">
                    进入 <ArrowRight size={12} />
                  </span>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
