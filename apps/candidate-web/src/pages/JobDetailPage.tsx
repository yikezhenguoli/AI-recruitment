import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  FileText,
  Loader2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Users,
  X,
} from 'lucide-react'
import {
  createApplication,
  getApplication,
  getJob,
  saveProfile,
} from '../api/portal'
import type { ApplicationDetail, JobDetail, UploadResult } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDate } from '../lib/format'
import { PARSE_STATUS } from '../lib/labels'
import { Badge, ErrorNote, LoadingBlock } from '../components/ui'
import { useAuthStore } from '../store/auth'

const ACCEPTED = '.pdf,.docx,.txt'
const MAX_BYTES = 20 * 1024 * 1024

export default function JobDetailPage() {
  const { id = '' } = useParams()
  const user = useAuthStore((state) => state.user)
  const [job, setJob] = useState<JobDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)
  const [uploadPercent, setUploadPercent] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [application, setApplication] = useState<ApplicationDetail | null>(null)
  const [profileName, setProfileName] = useState(user?.display_name ?? '')
  const [creatingProfile, setCreatingProfile] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getJob(id)
      setJob(data)
      setError(null)
      if (data.application_id) {
        const detail = await getApplication(data.application_id)
        setApplication(detail)
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '岗位详情加载失败。'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!result || !application) return
    if (application.parse_status === 'done' || application.parse_status === 'failed') return
    const timer = window.setInterval(() => {
      void getApplication(result.application_id).then(setApplication).catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [result, application])

  const pickFile = (candidate: File | null | undefined) => {
    setSubmitError(null)
    if (!candidate) return
    const lower = candidate.name.toLowerCase()
    if (!ACCEPTED.split(',').some((suffix) => lower.endsWith(suffix))) {
      setSubmitError('仅支持 PDF、DOCX 和 TXT 格式的简历。')
      return
    }
    if (candidate.size > MAX_BYTES) {
      setSubmitError('文件超过 20 MB，请压缩后再上传。')
      return
    }
    setFile(candidate)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    pickFile(event.dataTransfer.files?.[0])
  }

  const handleProfile = async () => {
    if (!profileName.trim()) return
    setCreatingProfile(true)
    setSubmitError(null)
    try {
      await saveProfile(profileName.trim())
      await load()
    } catch (err: unknown) {
      setSubmitError(getApiErrorMessage(err, '保存求职档案失败。'))
    } finally {
      setCreatingProfile(false)
    }
  }

  const handleSubmit = async () => {
    if (!file || !job) return
    if (!acknowledged) {
      setSubmitError('请先阅读并勾选简历处理授权。')
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    setUploadPercent(0)
    try {
      const uploaded = await createApplication(job.id, file, true, setUploadPercent)
      setResult(uploaded)
      const detail = await getApplication(uploaded.application_id)
      setApplication(detail)
    } catch (err: unknown) {
      setSubmitError(getApiErrorMessage(err, '投递失败，请稍后重试。'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <LoadingBlock text="正在加载岗位详情…" />
  if (error || !job) {
    return (
      <div className="mx-auto max-w-2xl">
        <ErrorNote message={error ?? '岗位不存在。'} />
        <Link to="/jobs" className="btn-ghost mt-4">
          <ArrowLeft size={15} />
          返回岗位列表
        </Link>
      </div>
    )
  }

  const parseStatus = application?.parse_status
  const parseMeta = parseStatus ? PARSE_STATUS[parseStatus] : null

  return (
    <div>
      <Link to="/jobs" className="btn-quiet mb-4 -ml-2">
        <ArrowLeft size={14} />
        返回岗位列表
      </Link>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <header className="card p-6 sm:p-7">
            <div className="flex flex-wrap items-center gap-2">
              {job.department && <Badge tone="brand">{job.department}</Badge>}
              {job.headcount ? <Badge>招 {job.headcount} 人</Badge> : null}
              <span className="text-[11px] text-muted">发布于 {formatDate(job.published_at)}</span>
            </div>
            <h1 className="mt-3 text-[26px] font-extrabold tracking-tight text-ink">{job.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted">
              <span className="inline-flex items-center gap-1">
                <Building2 size={12} /> 本企业租户内岗位
              </span>
              <span className="inline-flex items-center gap-1">
                <Users size={12} /> AI 辅助初筛
              </span>
            </div>
          </header>

          <article className="card p-6 sm:p-7">
            <h2 className="section-title">岗位描述</h2>
            <div className="mt-3 h-px w-full bg-line/70" />
            <div className="prose-jd mt-4">{job.jd_text || '该岗位暂未填写岗位描述。'}</div>
          </article>

          <section className="card p-6 sm:p-7">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-brand-soft text-brand-deep">
                <Sparkles size={18} />
              </span>
              <div>
                <h2 className="section-title">投递后会发生什么</h2>
                <ol className="mt-3 space-y-2 text-xs leading-relaxed text-muted">
                  <li>1. 系统解析你的简历文本，抽取经历、技能与时间线。</li>
                  <li>2. 生成「简历 × 本岗位」的匹配评估，列出优势、缺口与待核实项。</li>
                  <li>3. 招聘人员在人工复核后会决定是否安排 AI 初筛沟通或正式面试。</li>
                  <li>4. 你可以随时在「我的投递」查看进度，并在「我的」里撤回授权。</li>
                </ol>
              </div>
            </div>
          </section>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card p-6">
            {!job.has_profile ? (
              <div>
                <h2 className="section-title">先完善求职档案</h2>
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  你的账号还没有关联求职档案。填写称呼后即可投递。
                </p>
                <label className="mt-4 block">
                  <span className="label">你的称呼</span>
                  <input
                    className="input"
                    value={profileName}
                    onChange={(event) => setProfileName(event.target.value)}
                    maxLength={80}
                  />
                </label>
                <button
                  type="button"
                  className="btn-primary mt-4 w-full"
                  disabled={creatingProfile || !profileName.trim()}
                  onClick={() => void handleProfile()}
                >
                  {creatingProfile ? <Loader2 size={16} className="animate-spin" /> : null}
                  保存并继续
                </button>
                {submitError && <div className="mt-3"><ErrorNote message={submitError} /></div>}
              </div>
            ) : result ? (
              <div>
                <span className="chip">投递成功</span>
                <h2 className="mt-3 text-lg font-extrabold text-ink">简历已收到</h2>
                <p className="mt-1 text-xs text-muted">{file?.name ?? application?.file_name}</p>

                <div className="mt-4 rounded-2xl bg-brand-soft/60 p-4">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink">简历解析</span>
                    {parseMeta ? <Badge tone={parseMeta.tone} dot>{parseMeta.label}</Badge> : null}
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-muted">
                    {parseStatus === 'done'
                      ? '解析完成，可以生成匹配评估了。'
                      : parseStatus === 'failed'
                        ? '解析失败，请检查文件是否可读后重新投递。'
                        : '解析正在后台排队，通常需要几秒到一分钟。'}
                  </p>
                </div>

                <div className="mt-4 space-y-2">
                  <Link to={`/applications/${result.application_id}`} className="btn-primary w-full">
                    查看投递详情
                    <ArrowRight size={15} />
                  </Link>
                  <Link to="/jobs" className="btn-ghost w-full">
                    继续看其他岗位
                  </Link>
                </div>
              </div>
            ) : application ? (
              <div>
                <span className="chip">已投递</span>
                <h2 className="mt-3 text-lg font-extrabold text-ink">你已投递该岗位</h2>
                <div className="mt-3 space-y-2 text-xs text-muted">
                  <p className="flex items-center justify-between gap-2">
                    <span>简历文件</span>
                    <span className="font-semibold text-ink">{application.file_name ?? '—'}</span>
                  </p>
                  <p className="flex items-center justify-between gap-2">
                    <span>解析状态</span>
                    {application.parse_status && PARSE_STATUS[application.parse_status] ? (
                      <Badge tone={PARSE_STATUS[application.parse_status].tone}>
                        {PARSE_STATUS[application.parse_status].label}
                      </Badge>
                    ) : (
                      <span>—</span>
                    )}
                  </p>
                </div>
                <Link to={`/applications/${application.id}`} className="btn-primary mt-4 w-full">
                  查看投递详情
                  <ArrowRight size={15} />
                </Link>
                <p className="mt-3 text-center text-[10px] text-muted">
                  想换一份简历？在投递详情页重新上传即可。
                </p>
              </div>
            ) : (
              <div>
                <h2 className="section-title">投递这个岗位</h2>
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  支持 PDF、DOCX、TXT，单个文件不超过 20 MB。
                </p>

                <div
                  onDragOver={(event) => {
                    event.preventDefault()
                    setDragging(true)
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => inputRef.current?.click()}
                  className={`mt-4 cursor-pointer rounded-2xl border-2 border-dashed px-4 py-7 text-center transition ${
                    dragging ? 'border-brand bg-brand-soft/70' : 'border-line bg-white/60 hover:border-brand/50'
                  }`}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED}
                    className="hidden"
                    onChange={(event) => pickFile(event.target.files?.[0])}
                  />
                  {file ? (
                    <div className="flex items-center justify-center gap-2 text-xs text-ink">
                      <FileText size={16} className="text-brand-deep" />
                      <span className="max-w-[180px] truncate font-semibold">{file.name}</span>
                      <button
                        type="button"
                        className="btn-quiet"
                        onClick={(event) => {
                          event.stopPropagation()
                          setFile(null)
                        }}
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <UploadCloud size={24} className="mx-auto text-brand" />
                      <p className="mt-2 text-xs font-semibold text-ink">拖入简历，或点击选择文件</p>
                      <p className="mt-1 text-[10px] text-muted">PDF / DOCX / TXT · 最大 20 MB</p>
                    </>
                  )}
                </div>

                <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-xl bg-brand-soft/50 p-3">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-[#2f89d8]"
                  />
                  <span className="text-[10.5px] leading-relaxed text-muted">
                    我同意企业为本次投递解析我的简历，并生成岗位匹配评估。数据仅用于招聘流程，
                    我可以在「我的 → 授权与隐私」中随时撤回。
                  </span>
                </label>

                {submitting && (
                  <div className="mt-3">
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
                      <div
                        className="h-full rounded-full bg-brand transition-all"
                        style={{ width: `${Math.max(6, uploadPercent)}%` }}
                      />
                    </div>
                    <p className="mt-1 text-center text-[10px] text-muted">正在上传 {uploadPercent}%</p>
                  </div>
                )}

                {submitError && <div className="mt-3"><ErrorNote message={submitError} /></div>}

                <button
                  type="button"
                  className="btn-primary mt-4 w-full"
                  disabled={!file || !acknowledged || submitting}
                  onClick={() => void handleSubmit()}
                >
                  {submitting ? <Loader2 size={16} className="animate-spin" /> : <UploadCloud size={16} />}
                  {submitting ? '正在投递…' : '确认投递'}
                </button>

                <div className="mt-4 flex items-start gap-2 text-[10px] leading-relaxed text-muted">
                  <ShieldCheck size={13} className="mt-0.5 shrink-0 text-jade" />
                  <span>简历仅在本企业租户内使用；系统默认不保存原始面试音频。</span>
                </div>
              </div>
            )}
          </div>

          {application?.assessment && (
            <div className="card mt-4 flex items-center gap-3 p-4">
              <CheckCircle2 size={18} className="text-jade" />
              <div className="text-xs">
                <p className="font-semibold text-ink">已有匹配评估</p>
                <Link to={`/applications/${application.id}`} className="text-brand-deep hover:underline">
                  查看评估详情
                </Link>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
