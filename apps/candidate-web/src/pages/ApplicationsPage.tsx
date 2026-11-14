import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BellRing,
  CircleCheck,
  CircleDashed,
  FileText,
  PhoneCall,
  RotateCw,
} from 'lucide-react'
import { getApplications } from '../api/portal'
import type { ApplicationSummary } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatRelative, scoreTone } from '../lib/format'
import { ASSESSMENT_STATUS, INTERVIEW_STATUS, PARSE_STATUS } from '../lib/labels'
import { Badge, EmptyState, ErrorNote, LoadingBlock, PageHeader, ScoreRing } from '../components/ui'

const TONE_COLOR = {
  good: 'bg-jade',
  mid: 'bg-brand',
  low: 'bg-amber-500',
  none: 'bg-slate-300',
}

function stages(item: ApplicationSummary) {
  const parsed = item.parse_status === 'done'
  const assessed = Boolean(item.assessment_status && item.assessment_status !== 'generating')
  const interviewing = Boolean(item.interview_id)
  return [
    { key: 'submitted', label: '已投递', done: true },
    { key: 'parsed', label: '简历解析', done: parsed, active: !parsed },
    { key: 'assessed', label: 'AI 评估', done: assessed, active: parsed && !assessed },
    { key: 'interview', label: '面试沟通', done: interviewing, active: assessed && !interviewing },
  ]
}

export default function ApplicationsPage() {
  const [items, setItems] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getApplications()
      .then((data) => {
        if (!cancelled) {
          setItems(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getApiErrorMessage(err, '投递记录加载失败。'))
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
        eyebrow="My Applications"
        title="我的投递"
        description="每一份投递的解析状态、匹配评估与面试安排都在这里。匹配分只作参考，不代表录用结论。"
        actions={
          <Link to="/jobs" className="btn-ghost">
            浏览更多岗位
            <ArrowRight size={15} />
          </Link>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {loading ? (
        <LoadingBlock text="正在加载投递记录…" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<FileText size={22} />}
          title="还没有投递记录"
          description="去岗位广场看看，上传一份简历即可开始。第一次投递会自动建立你的求职档案。"
          action={
            <Link to="/jobs" className="btn-primary">
              去看岗位
              <ArrowRight size={15} />
            </Link>
          }
        />
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const tone = scoreTone(item.match_score)
            const parseMeta = item.parse_status ? PARSE_STATUS[item.parse_status] : null
            const assessmentMeta = item.assessment_status
              ? ASSESSMENT_STATUS[item.assessment_status]
              : null
            const interviewMeta = item.interview_status
              ? INTERVIEW_STATUS[item.interview_status]
              : null
            const step = stages(item)

            return (
              <Link
                key={item.id}
                to={`/applications/${item.id}`}
                className="card group block p-5 transition hover:-translate-y-0.5 hover:shadow-card sm:p-6"
              >
                <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-[16px] font-extrabold text-ink group-hover:text-brand-deep">
                        {item.title}
                      </h2>
                      {item.department && <Badge tone="brand">{item.department}</Badge>}
                      {parseMeta && <Badge tone={parseMeta.tone} dot>{parseMeta.label}</Badge>}
                      {interviewMeta && <Badge tone={interviewMeta.tone} dot>{interviewMeta.label}</Badge>}
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted">
                      <span>投递于 {formatRelative(item.created_at)}</span>
                      {item.file_name && (
                        <span className="inline-flex items-center gap-1">
                          <FileText size={11} />
                          {item.file_name}
                        </span>
                      )}
                      {assessmentMeta && (
                        <span className="inline-flex items-center gap-1">
                          <CircleCheck size={11} />
                          评估{assessmentMeta.label}
                        </span>
                      )}
                    </div>

                    <ol className="mt-4 flex flex-wrap items-center gap-1.5">
                      {step.map((node, index) => (
                        <li key={node.key} className="flex items-center gap-1.5">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                              node.done
                                ? 'bg-jade-soft text-jade-deep'
                                : node.active
                                  ? 'bg-brand-soft text-brand-deep'
                                  : 'bg-white/70 text-muted'
                            }`}
                          >
                            {node.done ? (
                              <CircleCheck size={11} />
                            ) : node.active ? (
                              <BellRing size={11} />
                            ) : (
                              <CircleDashed size={11} />
                            )}
                            {node.label}
                          </span>
                          {index < step.length - 1 && <span className="h-px w-3 bg-line" />}
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div className="flex shrink-0 items-center gap-4">
                    <div className="flex flex-col items-center">
                      <div className={`mb-1 h-1.5 w-16 overflow-hidden rounded-full bg-line`}>
                        <div
                          className={`h-full rounded-full ${TONE_COLOR[tone]}`}
                          style={{ width: `${item.match_score ?? 0}%` }}
                        />
                      </div>
                      <ScoreRing score={item.match_score} size={76} label="匹配度" />
                    </div>
                    <div className="hidden flex-col items-end gap-1 text-[11px] text-muted sm:flex">
                      {item.interview_id ? (
                        <span className="inline-flex items-center gap-1 text-jade-deep">
                          <PhoneCall size={12} />
                          有面试安排
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <RotateCw size={12} />
                          等待招聘方
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1 font-semibold text-brand-deep">
                        查看详情 <ArrowRight size={12} />
                      </span>
                    </div>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
