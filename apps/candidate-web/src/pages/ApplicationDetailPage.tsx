import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  FileText,
  Lightbulb,
  Loader2,
  PhoneCall,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from 'lucide-react'
import {
  createApplication,
  getApplication,
  runMatch,
} from '../api/portal'
import type { ApplicationDetail } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatBytes, formatDateTime, scoreTone } from '../lib/format'
import { ASSESSMENT_STATUS, INTERVIEW_STATUS, PARSE_STATUS, SCENARIO_LABEL } from '../lib/labels'
import {
  Badge,
  ErrorNote,
  LoadingBlock,
  PageHeader,
  ScoreRing,
} from '../components/ui'

const TONE_COLOR = {
  good: 'bg-jade',
  mid: 'bg-brand',
  low: 'bg-amber-500',
  none: 'bg-slate-300',
}

export default function ApplicationDetailPage() {
  const { id = '' } = useParams()
  const [detail, setDetail] = useState<ApplicationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [matching, setMatching] = useState(false)
  const [matchError, setMatchError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const data = await getApplication(id)
      setDetail(data)
      setError(null)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '投递详情加载失败。'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!detail) return
    const status = detail.parse_status
    if (status === 'done' || status === 'failed') return
    const timer = window.setInterval(() => void load(), 2500)
    return () => window.clearInterval(timer)
  }, [detail, load])

  const handleMatch = async () => {
    if (matching) return
    setMatching(true)
    setMatchError(null)
    try {
      await runMatch(id)
      await load()
    } catch (err: unknown) {
      setMatchError(getApiErrorMessage(err, '匹配评估生成失败。'))
    } finally {
      setMatching(false)
    }
  }

  const handleReupload = async (file: File | null | undefined) => {
    if (!file || !detail) return
    setUploading(true)
    setMatchError(null)
    try {
      await createApplication(detail.job_id, file, true)
      await load()
    } catch (err: unknown) {
      setMatchError(getApiErrorMessage(err, '重新上传失败。'))
    } finally {
      setUploading(false)
    }
  }

  if (loading) return <LoadingBlock text="正在加载投递详情…" />
  if (error || !detail) {
    return (
      <div className="mx-auto max-w-2xl">
        <ErrorNote message={error ?? '投递记录不存在。'} />
        <Link to="/applications" className="btn-ghost mt-4">
          <ArrowLeft size={15} />
          返回我的投递
        </Link>
      </div>
    )
  }

  const parseMeta = detail.parse_status ? PARSE_STATUS[detail.parse_status] : null
  const assessment = detail.assessment
  const report = assessment?.report_json?.explanation ?? assessment?.report_json ?? null
  const score = assessment?.match_score ?? null

  return (
    <div>
      <Link to="/applications" className="btn-quiet mb-4 -ml-2">
        <ArrowLeft size={14} />
        返回我的投递
      </Link>

      <PageHeader
        eyebrow="Application"
        title={detail.title}
        description={`${detail.department ?? '未分部门'} · 投递于 ${formatDateTime(detail.created_at)}`}
        actions={
          <Link to={`/jobs/${detail.job_id}`} className="btn-ghost">
            查看岗位
            <ArrowRight size={15} />
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
        <div className="space-y-5">
          <section className="card p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
              <ScoreRing score={score} size={124} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="section-title">AI 匹配评估</h2>
                  {assessment ? (
                    <Badge tone={ASSESSMENT_STATUS[assessment.status]?.tone ?? 'muted'} dot>
                      {ASSESSMENT_STATUS[assessment.status]?.label ?? assessment.status}
                    </Badge>
                  ) : (
                    <Badge>尚未生成</Badge>
                  )}
                </div>
                {assessment ? (
                  <>
                    <p className="mt-2 text-xs leading-relaxed text-muted">
                      {report?.summary ||
                        '评估已生成，但本次没有返回文字摘要。可查看下方维度明细。'}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => void handleMatch()}
                        disabled={matching || detail.parse_status !== 'done'}
                      >
                        {matching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                        {matching ? '重新评估中…' : '重新生成评估'}
                      </button>
                      <span className="text-[10px] text-muted">
                        模型 {assessment.model_version ?? '—'} · 更新于{' '}
                        {formatDateTime(assessment.updated_at)}
                      </span>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="mt-2 text-xs leading-relaxed text-muted">
                      简历解析完成后，可以生成「你的简历 × 这个岗位」的匹配评估。评估是辅助信息，
                      不是录用结论。
                    </p>
                    <button
                      type="button"
                      className="btn-primary mt-3"
                      onClick={() => void handleMatch()}
                      disabled={matching || detail.parse_status !== 'done'}
                    >
                      {matching ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                      {matching ? '正在生成（约 10–40 秒）…' : '生成匹配评估'}
                    </button>
                    {detail.parse_status !== 'done' && (
                      <p className="mt-2 text-[10px] text-amber-700">需要先等简历解析完成。</p>
                    )}
                  </>
                )}
              </div>
            </div>

            {matching && (
              <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-line">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-brand" />
              </div>
            )}
            {matchError && <div className="mt-4"><ErrorNote message={matchError} /></div>}
          </section>

          {report && (
            <>
              <ReportList
                icon={<CheckCircle2 size={16} />}
                tone="jade"
                title="你的优势"
                items={report.strengths ?? []}
                empty="本次评估没有列出明显优势。"
              />
              <ReportList
                icon={<AlertTriangle size={16} />}
                tone="amber"
                title="岗位关注的缺口"
                items={report.gaps ?? []}
                empty="本次评估没有列出明显缺口。"
              />
              <ReportList
                icon={<Lightbulb size={16} />}
                tone="brand"
                title="可以提前准备的说明"
                items={report.suggestions ?? []}
                empty="暂无补充建议。"
              />
              <ReportList
                icon={<ShieldCheck size={16} />}
                tone="slate"
                title="待核实项"
                items={report.risk_notes ?? []}
                empty="暂无待核实项。"
              />
            </>
          )}

          {detail.dimensions.length > 0 && (
            <section className="card p-6">
              <h2 className="section-title">评分维度</h2>
              <p className="mt-1 text-xs text-muted">
                权重来自该岗位的评估方案。分数是小模型给出的语义相似度，不是面试结论。
              </p>
              <div className="mt-4 space-y-4">
                {detail.dimensions.map((dimension) => {
                  const value = dimension.score ?? 0
                  const dimTone = scoreTone(dimension.score)
                  return (
                    <div key={dimension.dimension_key}>
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="font-semibold text-ink">{dimension.label}</span>
                        <span className="tabular-nums text-muted">
                          权重 {Number(dimension.weight_pct).toFixed(1)}% · 得分{' '}
                          {dimension.score === null ? '—' : value.toFixed(1)}
                        </span>
                      </div>
                      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-line">
                        <div
                          className={`h-full rounded-full ${TONE_COLOR[dimTone]}`}
                          style={{ width: `${Math.max(2, value)}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </div>

        <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
          <section className="card p-6">
            <h2 className="section-title">投递资料</h2>
            <div className="mt-4 space-y-3 text-xs">
              <Row label="简历文件">
                <span className="inline-flex max-w-[190px] items-center gap-1 truncate font-semibold text-ink">
                  <FileText size={12} />
                  {detail.file_name ?? '—'}
                </span>
              </Row>
              <Row label="文件大小">{formatBytes(detail.size_bytes)}</Row>
              <Row label="解析状态">
                {parseMeta ? (
                  <Badge tone={parseMeta.tone} dot>
                    {parseMeta.label}
                  </Badge>
                ) : (
                  '—'
                )}
              </Row>
              <Row label="上传时间">{formatDateTime(detail.uploaded_at)}</Row>
            </div>

            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(event) => void handleReupload(event.target.files?.[0])}
            />
            <button
              type="button"
              className="btn-ghost mt-4 w-full"
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <UploadCloud size={14} />}
              {uploading ? '正在上传新简历…' : '更换简历'}
            </button>
            <p className="mt-2 text-[10px] leading-relaxed text-muted">
              更换后仍沿用已授予的简历处理授权，并会重新解析。
            </p>
          </section>

          <section className="card p-6">
            <h2 className="section-title">面试安排</h2>
            {detail.interviews.length === 0 ? (
              <p className="mt-2 text-xs leading-relaxed text-muted">
                暂无面试安排。招聘方复核后会决定是否发起 AI 初筛沟通。
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {detail.interviews.map((interview) => {
                  const meta = INTERVIEW_STATUS[interview.status]
                  return (
                    <li key={interview.id}>
                      <Link
                        to={`/interviews/${interview.id}`}
                        className="flex items-center justify-between gap-2 rounded-xl border border-line bg-white/70 px-3 py-2.5 text-xs transition hover:border-brand/40"
                      >
                        <span className="inline-flex items-center gap-2 font-semibold text-ink">
                          <PhoneCall size={14} className="text-brand-deep" />
                          {SCENARIO_LABEL[interview.scenario] ?? interview.scenario}
                        </span>
                        {meta ? <Badge tone={meta.tone}>{meta.label}</Badge> : null}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section className="card p-6">
            <div className="flex items-start gap-2">
              <ClipboardList size={16} className="mt-0.5 shrink-0 text-muted" />
              <div>
                <p className="text-xs font-bold text-ink">关于匹配分</p>
                <p className="mt-1 text-[10.5px] leading-relaxed text-muted">
                  分数来自简历文本与岗位描述的语义相似度（0–100），并受岗位评估方案权重影响。
                  它可能受简历写法影响，不能证明经历真实性。最终录用决定由人工做出。
                </p>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      <span className="text-right text-ink">{children}</span>
    </div>
  )
}

function ReportList({
  icon,
  tone,
  title,
  items,
  empty,
}: {
  icon: ReactNode
  tone: 'jade' | 'amber' | 'brand' | 'slate'
  title: string
  items: string[]
  empty: string
}) {
  const toneClass = {
    jade: 'bg-jade-soft text-jade-deep',
    amber: 'bg-amber-50 text-amber-700',
    brand: 'bg-brand-soft text-brand-deep',
    slate: 'bg-slate-100 text-slate-600',
  }[tone]

  return (
    <section className="card p-6">
      <div className="flex items-center gap-2">
        <span className={`flex h-8 w-8 items-center justify-center rounded-xl ${toneClass}`}>{icon}</span>
        <h2 className="section-title">{title}</h2>
      </div>
      {items.length === 0 ? (
        <p className="mt-3 text-xs text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((item, index) => (
            <li key={`${index}-${item.slice(0, 8)}`} className="flex items-start gap-2 text-xs leading-relaxed text-ink/85">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-40" />
              {item}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
