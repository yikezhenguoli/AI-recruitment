import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  Archive,
  Braces,
  CheckCircle2,
  FileText,
  Loader2,
  Send,
  Sparkles,
  Users,
  Wand2,
} from 'lucide-react'
import {
  archiveJob,
  createJdVersion,
  extractJd,
  generateJd,
  getJob,
  getJobStats,
  listInterviewPlans,
  listJobVersions,
  listWeightTemplates,
  patchJob,
  publishJob,
  selectJdVersion,
  setWeightPlan,
} from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useAuthStore } from '../store/authStore'
import { JOB_STATUS_LABEL } from '../types'
import type { JdStructured, JdWarning, WeightDimension } from '../types'

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="ttc-detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function StructuredSummary({ structured }: { structured: JdStructured }) {
  const responsibilities = Array.isArray(structured.responsibilities)
    ? structured.responsibilities
    : []
  const required = Array.isArray(structured.required_skills)
    ? structured.required_skills
    : []
  const preferred = Array.isArray(structured.preferred_skills)
    ? structured.preferred_skills
    : []
  return (
    <div className="ttc-jd-structured">
      {structured.role_title && <DetailRow label="岗位名称" value={structured.role_title} />}
      {structured.seniority_level && (
        <DetailRow label="资历" value={structured.seniority_level} />
      )}
      {structured.min_years_experience != null && (
        <DetailRow
          label="经验年限"
          value={`${structured.min_years_experience} 年以上`}
        />
      )}
      {required.length > 0 && (
        <div className="ttc-skill-groups">
          <div>
            <h3>必备技能</h3>
            <div className="ttc-chip-list">
              {required.map((skill) => (
                <span key={skill} className="ttc-chip ttc-chip-blue">
                  {skill}
                </span>
              ))}
            </div>
          </div>
          {preferred.length > 0 && (
            <div>
              <h3>优先技能</h3>
              <div className="ttc-chip-list">
                {preferred.map((skill) => (
                  <span key={skill} className="ttc-chip">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {responsibilities.length > 0 && (
        <div className="ttc-responsibility-block">
          <h3>岗位职责</h3>
          <ul>
            {responsibilities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {!structured.role_title && responsibilities.length === 0 && (
        <pre className="ttc-json-preview">
          {JSON.stringify(structured, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const role = useAuthStore((state) => state.user?.role)
  const jobId = id ?? ''

  const [prompt, setPrompt] = useState('')
  const [variants, setVariants] = useState(1)
  const [extractText, setExtractText] = useState('')
  const [manualJd, setManualJd] = useState('')
  const [extracted, setExtracted] = useState<{
    structured: JdStructured
    warnings: JdWarning[]
  } | null>(null)
  const [weights, setWeights] = useState<WeightDimension[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
  })
  const versionsQuery = useQuery({
    queryKey: ['job', jobId, 'versions'],
    queryFn: () => listJobVersions(jobId),
    enabled: Boolean(jobId),
  })
  const statsQuery = useQuery({
    queryKey: ['job', jobId, 'stats'],
    queryFn: () => getJobStats(jobId),
    enabled: Boolean(jobId),
  })
  const plansQuery = useQuery({
    queryKey: ['job', jobId, 'interview-plans'],
    queryFn: () => listInterviewPlans(jobId),
    enabled: Boolean(jobId),
  })
  const templatesQuery = useQuery({
    queryKey: ['weight-templates'],
    queryFn: listWeightTemplates,
  })

  const job = jobQuery.data
  const versions = versionsQuery.data ?? []
  const templates = templatesQuery.data ?? []

  useEffect(() => {
    if (weights.length === 0 && templates[0]?.dimensions?.length) {
      setWeights(templates[0].dimensions.map((item) => ({ ...item })))
    }
  }, [templates, weights.length])

  const totalWeight = useMemo(
    () => weights.reduce((sum, item) => sum + Number(item.weight_pct || 0), 0),
    [weights],
  )

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['job', jobId] }),
      queryClient.invalidateQueries({ queryKey: ['job', jobId, 'versions'] }),
      queryClient.invalidateQueries({ queryKey: ['job', jobId, 'stats'] }),
    ])
  }

  const showError = (err: unknown, fallback: string) =>
    setError(getApiErrorMessage(err, fallback))
  const clearFeedback = () => {
    setError(null)
    setMessage(null)
  }

  const generateMutation = useMutation({
    mutationFn: () =>
      generateJd(jobId, { prompt: prompt.trim(), variants }),
    onSuccess: async (result) => {
      clearFeedback()
      setMessage(
        result.versions.length > 0
          ? `AI 已生成 ${result.versions.length} 个 JD 版本；选择「设为当前」后才会成为岗位当前版本。`
          : 'AI 返回了生成建议，但未创建版本。',
      )
      await invalidate()
    },
    onError: (err) => showError(err, 'AI 生成 JD 失败。'),
  })

  const extractMutation = useMutation({
    mutationFn: () => extractJd(jobId, extractText.trim()),
    onSuccess: (result) => {
      clearFeedback()
      setExtracted(result)
      setManualJd(extractText)
      setMessage('JD 结构抽取完成，可保存为新版本。')
    },
    onError: (err) => showError(err, 'JD 结构抽取失败。'),
  })

  const versionMutation = useMutation({
    mutationFn: (payload: { jd_text: string; structured: JdStructured }) =>
      createJdVersion(jobId, payload),
    onSuccess: async () => {
      clearFeedback()
      setManualJd('')
      setMessage('新 JD 版本已保存。')
      await invalidate()
    },
    onError: (err) => showError(err, '保存 JD 版本失败。'),
  })

  const selectMutation = useMutation({
    mutationFn: (versionId: string) => selectJdVersion(jobId, versionId),
    onSuccess: async () => {
      clearFeedback()
      setMessage('已设为岗位当前 JD 版本。')
      await invalidate()
    },
    onError: (err) => showError(err, '切换 JD 版本失败。'),
  })

  const publishMutation = useMutation({
    mutationFn: () => publishJob(jobId),
    onSuccess: async () => {
      clearFeedback()
      setMessage('岗位已发布。')
      await invalidate()
    },
    onError: (err) => showError(err, '发布岗位失败。'),
  })

  const archiveMutation = useMutation({
    mutationFn: () => archiveJob(jobId),
    onSuccess: async () => {
      clearFeedback()
      setMessage('岗位已归档。')
      await invalidate()
    },
    onError: (err) => showError(err, '归档岗位失败。'),
  })

  const weightMutation = useMutation({
    mutationFn: () =>
      setWeightPlan(jobId, {
        name: '岗位权重方案',
        mode: 'custom',
        dimensions: weights.map((item) => ({
          key: item.key,
          label: item.label,
          weight_pct: Number(item.weight_pct),
          description: item.description ?? undefined,
        })),
      }),
    onSuccess: async () => {
      clearFeedback()
      setMessage('权重方案已保存。')
      await invalidate()
    },
    onError: (err) => showError(err, '保存权重方案失败。'),
  })

  const renameMutation = useMutation({
    mutationFn: (payload: { title: string; department: string; headcount: string }) =>
      patchJob(
        jobId,
        {
          title: payload.title,
          department: payload.department || null,
          headcount: payload.headcount ? Number(payload.headcount) : null,
        },
        job?.updated_at ?? '',
      ),
    onSuccess: async () => {
      clearFeedback()
      setMessage('岗位基本信息已更新。')
      await invalidate()
    },
    onError: (err) => showError(err, '更新岗位基本信息失败。'),
  })

  const onSaveExtracted = (event: FormEvent) => {
    event.preventDefault()
    if (!extracted || !manualJd.trim()) return
    versionMutation.mutate({
      jd_text: manualJd.trim(),
      structured: extracted.structured,
    })
  }

  if (jobQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      </div>
    )
  }

  if (jobQuery.isError || !job) {
    return (
      <div className="ttc-page">
        <section className="ttc-page-head">
          <div>
            <h1>岗位详情</h1>
            <p>无法读取该岗位。</p>
          </div>
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={16} />
            返回岗位列表
          </Link>
        </section>
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>岗位读取失败</strong>
            <span>{getApiErrorMessage(jobQuery.error, '岗位可能不存在。')}</span>
          </div>
        </div>
      </div>
    )
  }

  const current = job.current_version
  const canEdit = job.status !== 'locked' && job.status !== 'archived'
  const stats = statsQuery.data

  return (
    <div className="ttc-page">
      {message && (
        <div className="ttc-notice">
          <CheckCircle2 size={16} />
          <span>{message}</span>
        </div>
      )}
      {error && (
        <div className="ttc-notice ttc-notice-warn">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            JOB PROFILE
            <span className="hero-eyebrow-line" />
            <span>{job.id.slice(0, 8)}</span>
          </div>
          <h1>{job.title}</h1>
          <p>
            {JOB_STATUS_LABEL[job.status]} · 更新于 {formatDateTime(job.updated_at)}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={16} />
            返回列表
          </Link>
          <Link to={`/candidates?job=${job.id}`} className="ttc-btn ttc-btn-secondary">
            <Users size={16} />
            候选人筛选
          </Link>
          {job.status === 'draft' && (
            <button
              type="button"
              className="ttc-btn ttc-btn-primary"
              disabled={publishMutation.isPending || !job.current_version_id}
              onClick={() => publishMutation.mutate()}
            >
              <Send size={15} />
              发布岗位
            </button>
          )}
          {role === 'admin' && job.status !== 'archived' && (
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary"
              disabled={archiveMutation.isPending}
              onClick={() => archiveMutation.mutate()}
            >
              <Archive size={15} />
              归档
            </button>
          )}
        </div>
      </section>

      <section className="ttc-kpi-grid">
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>候选人</span>
            <Users size={17} />
          </div>
          <strong className="ttc-kpi-value">{stats?.candidates ?? '—'}</strong>
          <p className="ttc-kpi-hint">GET /jobs/{'{id}'}/stats</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>评估数</span>
            <Braces size={17} />
          </div>
          <strong className="ttc-kpi-value">{stats?.assessments ?? '—'}</strong>
          <p className="ttc-kpi-hint">匹配与确定性评估合计</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>语音会话</span>
            <FileText size={17} />
          </div>
          <strong className="ttc-kpi-value">{stats?.voice_sessions ?? '—'}</strong>
          <p className="ttc-kpi-hint">Qwen Realtime 中转</p>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span>JD 版本</span>
            <Sparkles size={17} />
          </div>
          <strong className="ttc-kpi-value">{versions.length}</strong>
          <p className="ttc-kpi-hint">AI 生成 / 手工 / 抽取</p>
        </article>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">岗位信息</h2>
              <p className="ttc-card-sub">来自 GET /api/v1/jobs/{'{id}'}</p>
            </div>
            <span className="ttc-job-icon">
              <FileText size={18} />
            </span>
          </div>
          <div className="ttc-detail-rows">
            <DetailRow label="岗位名称" value={job.title} />
            <DetailRow label="部门" value={job.department || '未设置'} />
            <DetailRow
              label="招聘人数"
              value={job.headcount != null ? `${job.headcount} 人` : '未设置'}
            />
            <DetailRow label="状态" value={JOB_STATUS_LABEL[job.status]} />
            <DetailRow label="创建时间" value={formatDateTime(job.created_at)} />
            <DetailRow label="更新时间" value={formatDateTime(job.updated_at)} />
          </div>

          {canEdit && (
            <form
              className="ttc-inline-form"
              onSubmit={(event) => {
                event.preventDefault()
                const form = new FormData(event.currentTarget)
                renameMutation.mutate({
                  title: String(form.get('title') || '').trim(),
                  department: String(form.get('department') || '').trim(),
                  headcount: String(form.get('headcount') || '').trim(),
                })
              }}
            >
              <input name="title" defaultValue={job.title} placeholder="岗位名称" required />
              <input
                name="department"
                defaultValue={job.department ?? ''}
                placeholder="部门"
              />
              <input
                name="headcount"
                type="number"
                min={1}
                defaultValue={job.headcount ?? ''}
                placeholder="人数"
              />
              <button
                type="submit"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                disabled={renameMutation.isPending}
              >
                保存信息
              </button>
            </form>
          )}
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">当前 JD</h2>
              <p className="ttc-card-sub">岗位发布与匹配使用当前版本</p>
            </div>
            <span className={`ttc-badge ${current ? 'ttc-badge-green' : 'ttc-badge-amber'}`}>
              {current ? `v${current.version_no}` : '未选择版本'}
            </span>
          </div>
          {current ? (
            <>
              <StructuredSummary structured={current.structured} />
              <pre className="ttc-jd-text">{current.jd_text}</pre>
            </>
          ) : (
            <div className="ttc-empty-state ttc-empty-compact">
              <Sparkles size={22} />
              <strong>还没有 JD 版本</strong>
              <span>用右侧 AI 生成、抽取或手工保存一版，然后发布岗位。</span>
            </div>
          )}
        </article>
      </section>

      <section className="ttc-card ttc-card-pad">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">JD 版本与 AI 生成</h2>
            <p className="ttc-card-sub">
              DeepSeek 通过后端 /jobs/{'{id}'}/jd/generate 与 /jd/extract 调用
            </p>
          </div>
          <Wand2 size={18} className="ttc-accent-icon" />
        </div>

        <div className="ttc-jd-tools">
          <form
            className="ttc-tool-block"
            onSubmit={(event) => {
              event.preventDefault()
              if (prompt.trim().length < 10) {
                setError('提示词至少 10 个字符。')
                return
              }
              generateMutation.mutate()
            }}
          >
            <h3>
              <Sparkles size={15} />
              AI 生成 JD
            </h3>
            <textarea
              rows={5}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="描述岗位背景、职责、必须技能等，越具体越好。"
              maxLength={5000}
            />
            <div className="ttc-tool-actions">
              <label>
                版本数
                <select
                  value={variants}
                  onChange={(event) => setVariants(Number(event.target.value))}
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                </select>
              </label>
              <button
                type="submit"
                className="ttc-btn ttc-btn-primary ttc-btn-sm"
                disabled={generateMutation.isPending || !canEdit}
              >
                {generateMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                生成
              </button>
            </div>
          </form>

          <form
            className="ttc-tool-block"
            onSubmit={(event) => {
              event.preventDefault()
              if (extractText.trim().length < 20) {
                setError('待抽取的 JD 至少 20 个字符。')
                return
              }
              extractMutation.mutate()
            }}
          >
            <h3>
              <Braces size={15} />
              从原文抽取结构
            </h3>
            <textarea
              rows={5}
              value={extractText}
              onChange={(event) => setExtractText(event.target.value)}
              placeholder="粘贴已有 JD 原文，AI 只抽取、不补写。"
              maxLength={20000}
            />
            <div className="ttc-tool-actions">
              <span className="ttc-muted">
                {extracted ? `${extracted.warnings.length} 条警告` : '缺失项会写入 warnings'}
              </span>
              <button
                type="submit"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                disabled={extractMutation.isPending}
              >
                {extractMutation.isPending && (
                  <Loader2 size={14} className="animate-spin" />
                )}
                抽取
              </button>
            </div>
          </form>

          <form className="ttc-tool-block" onSubmit={onSaveExtracted}>
            <h3>
              <FileText size={15} />
              保存为 JD 版本
            </h3>
            <textarea
              rows={5}
              value={manualJd}
              onChange={(event) => setManualJd(event.target.value)}
              placeholder="可直接编辑；结构取自上方抽取结果。"
              maxLength={20000}
            />
            <div className="ttc-tool-actions">
              <span className="ttc-muted">
                {extracted ? '将保存抽取出的 structured' : '请先执行「从原文抽取结构」'}
              </span>
              <button
                type="submit"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                disabled={
                  versionMutation.isPending || !extracted || manualJd.trim().length < 20
                }
              >
                保存版本
              </button>
            </div>
          </form>
        </div>

        {extracted && (
          <div className="ttc-extract-result">
            <h3>抽取结果</h3>
            <pre className="ttc-json-preview">
              {JSON.stringify(
                { structured: extracted.structured, warnings: extracted.warnings },
                null,
                2,
              )}
            </pre>
          </div>
        )}

        <div className="ttc-version-list">
          {versions.map((version) => {
            const isCurrent = version.id === job.current_version_id
            return (
              <article
                key={version.id}
                className={`ttc-version-row ${isCurrent ? 'is-current' : ''}`}
              >
                <div>
                  <strong>
                    v{version.version_no}
                    {isCurrent && <span className="ttc-badge ttc-badge-green">当前</span>}
                  </strong>
                  <span>
                    {version.source} · {formatDateTime(version.created_at)}
                  </span>
                  <p>{version.jd_text.slice(0, 160)}</p>
                </div>
                {!isCurrent && canEdit && (
                  <button
                    type="button"
                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={selectMutation.isPending}
                    onClick={() => selectMutation.mutate(version.id)}
                  >
                    设为当前
                  </button>
                )}
              </article>
            )
          })}
          {versions.length === 0 && (
            <p className="ttc-muted">还没有 JD 版本。</p>
          )}
        </div>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">权重方案</h2>
              <p className="ttc-card-sub">
                合计必须为 100；保存会通过 PUT /jobs/{'{id}'}/weight-plan 新建版本
              </p>
            </div>
            <span
              className={`ttc-badge ${
                totalWeight === 100 ? 'ttc-badge-green' : 'ttc-badge-red'
              }`}
            >
              合计 {totalWeight}
            </span>
          </div>
          <div className="ttc-weight-list">
            {weights.map((item, index) => (
              <label key={item.key} className="ttc-weight-row">
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.key}</small>
                </span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={item.weight_pct}
                  onChange={(event) => {
                    const next = [...weights]
                    next[index] = {
                      ...item,
                      weight_pct: Number(event.target.value),
                    }
                    setWeights(next)
                  }}
                />
                <em>%</em>
              </label>
            ))}
          </div>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary ttc-btn-sm"
            disabled={
              weightMutation.isPending ||
              weights.length === 0 ||
              totalWeight !== 100 ||
              !canEdit
            }
            onClick={() => weightMutation.mutate()}
          >
            保存权重方案
          </button>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">面试方案</h2>
              <p className="ttc-card-sub">GET /jobs/{'{id}'}/interview-plans</p>
            </div>
          </div>
          {(plansQuery.data ?? []).length > 0 ? (
            <ul className="ttc-plain-list">
              {plansQuery.data?.map((plan) => (
                <li key={plan.id}>
                  <strong>{plan.name}</strong>
                  <span>
                    {plan.rounds} 轮 · {plan.duration_min} 分钟
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ttc-muted">该岗位及租户暂无可用面试方案。</p>
          )}
        </article>
      </section>
    </div>
  )
}
