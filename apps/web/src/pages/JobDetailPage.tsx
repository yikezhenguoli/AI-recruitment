import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  FileText,
  Rocket,
  Sparkles,
  Wand2,
} from 'lucide-react'
import {
  createVersion,
  generateJD,
  getJob,
  getJobStats,
  getWeightPlan,
  listVersions,
  publishJob,
  selectVersion,
  setWeightPlan,
} from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { JDVersion, JobStatus, WeightDimension } from '../types'

const STATUS_LABEL: Record<JobStatus, string> = {
  draft: '草稿',
  published: '已发布',
  locked: '已锁定',
  archived: '已归档',
}

export default function JobDetailPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const [jdDraft, setJdDraft] = useState('')
  const [prompt, setPrompt] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const jobQuery = useQuery({ queryKey: ['job', id], queryFn: () => getJob(id), enabled: Boolean(id) })
  const versionsQuery = useQuery({
    queryKey: ['jobVersions', id],
    queryFn: () => listVersions(id),
    enabled: Boolean(id),
  })
  const statsQuery = useQuery({
    queryKey: ['jobStats', id],
    queryFn: () => getJobStats(id),
    enabled: Boolean(id),
  })
  const planQuery = useQuery({
    queryKey: ['jobWeightPlan', id],
    queryFn: () => getWeightPlan(id),
    enabled: Boolean(id),
  })

  const job = jobQuery.data
  const versions = versionsQuery.data ?? []
  const plan = planQuery.data

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['job', id] })
    void queryClient.invalidateQueries({ queryKey: ['jobVersions', id] })
    void queryClient.invalidateQueries({ queryKey: ['jobWeightPlan', id] })
    void queryClient.invalidateQueries({ queryKey: ['jobStats', id] })
    void queryClient.invalidateQueries({ queryKey: ['jobs'] })
  }

  const saveVersion = useMutation({
    mutationFn: async () => {
      const version = await createVersion(id, {
        jd_text: jdDraft.trim(),
        structured: {},
      })
      await selectVersion(id, version.id)
      return version
    },
    onSuccess: () => {
      setMessage('已保存并设为当前 JD 版本。')
      setError('')
      setJdDraft('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '保存 JD 失败。')),
  })

  const useVersion = useMutation({
    mutationFn: (version: JDVersion) => selectVersion(id, version.id),
    onSuccess: () => {
      setMessage('已切换当前 JD 版本。')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '切换版本失败。')),
  })

  const publish = useMutation({
    mutationFn: () => publishJob(id),
    onSuccess: () => {
      setMessage('岗位已发布。')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '发布失败：需要草稿岗位与已选定的 JD 版本。')),
  })

  const generate = useMutation({
    mutationFn: () => generateJD(id, { prompt: prompt.trim(), variants: 1 }),
    onSuccess: (result) => {
      if (result.suggestions?.length) {
        setMessage(`建议：${result.suggestions.join('；')}`)
      } else {
        setMessage(`模型生成 ${result.versions.length} 个 JD 版本，请在下方选择。`)
      }
      setError('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, 'JD 生成失败：请确认已配置岗位模型。')),
  })

  const savePlan = useMutation({
    mutationFn: (dimensions: WeightDimension[]) =>
      setWeightPlan(id, { name: '自定义岗位权重', mode: 'custom', dimensions }),
    onSuccess: () => {
      setMessage('权重方案已更新。')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '保存权重失败：权重合计必须为 100。')),
  })

  const [dims, setDims] = useState<WeightDimension[] | null>(null)
  const editableDims = dims ?? plan?.dimensions ?? []
  const weightSum = editableDims.reduce((sum, dim) => sum + Number(dim.weight_pct || 0), 0)

  if (jobQuery.isError) {
    return (
      <div className="ttc-page">
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取岗位</strong>
            <span>{getApiErrorMessage(jobQuery.error)}</span>
          </div>
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary ttc-btn-sm">
            返回列表
          </Link>
        </div>
      </div>
    )
  }

  const canEdit = job && job.status !== 'locked' && job.status !== 'archived'

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            POSITION
            <span className="hero-eyebrow-line" />
            <span>{job ? STATUS_LABEL[job.status] : '加载中'}</span>
          </div>
          <h1>{job?.title ?? '岗位详情'}</h1>
          <p>
            {job?.department ?? '未设置部门'} · 在招 {job?.headcount ?? '—'} 人 · 更新于{' '}
            {formatDateTime(job?.updated_at)}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={15} />
            返回列表
          </Link>
          {job?.status === 'draft' && (
            <button
              type="button"
              className="ttc-btn ttc-btn-primary"
              disabled={publish.isPending || !job.current_version_id}
              title={job.current_version_id ? undefined : '先选定一个 JD 版本'}
              onClick={() => publish.mutate()}
            >
              <Rocket size={16} />
              {publish.isPending ? '发布中…' : '发布岗位'}
            </button>
          )}
        </div>
      </section>

      {(message || error) && (
        <div className={error ? 'ttc-inline-error' : 'ttc-inline-ok'}>
          {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{error || message}</span>
        </div>
      )}

      <div className="ttc-kpi-grid">
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-blue">
              <FileText size={16} />
            </span>
            <span>候选人</span>
          </div>
          <strong className="ttc-kpi-value">{statsQuery.data?.candidates ?? '—'}</strong>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-green">
              <CheckCircle2 size={16} />
            </span>
            <span>评估</span>
          </div>
          <strong className="ttc-kpi-value">{statsQuery.data?.assessments ?? '—'}</strong>
        </article>
        <article className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-violet">
              <Sparkles size={16} />
            </span>
            <span>语音会话</span>
          </div>
          <strong className="ttc-kpi-value">{statsQuery.data?.voice_sessions ?? '—'}</strong>
        </article>
      </div>

      <div className="ttc-detail-grid">
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">当前 JD</h2>
              <p className="ttc-card-sub">评估时的必备技能从这里抽取。</p>
            </div>
            <FileText size={18} className="ttc-accent-icon" />
          </div>
          <pre className="ttc-jd-text">{job?.current_version?.jd_text ?? '尚未选定 JD 版本'}</pre>
        </article>

        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">权重方案</h2>
              <p className="ttc-card-sub">
                {plan ? `${plan.name} · 合计 ${weightSum}%` : '加载中'}
              </p>
            </div>
            <Wand2 size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-weight-list">
            {editableDims.map((dim) => (
              <label key={dim.key} className="ttc-weight-row">
                <span>{dim.label}</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={dim.weight_pct}
                  disabled={!canEdit}
                  onChange={(event) => {
                    const next = editableDims.map((item) =>
                      item.key === dim.key
                        ? { ...item, weight_pct: Number(event.target.value) }
                        : item,
                    )
                    setDims(next)
                  }}
                />
                <span className="ttc-muted">%</span>
              </label>
            ))}
          </div>
          <div className="ttc-form-actions">
            <span className={weightSum === 100 ? 'ttc-muted' : 'ttc-inline-hint'}>
              合计 {weightSum}%
            </span>
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              disabled={!canEdit || weightSum !== 100 || savePlan.isPending}
              onClick={() => savePlan.mutate(editableDims)}
            >
              保存权重
            </button>
          </div>
        </article>
      </div>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">JD 版本</h2>
            <p className="ttc-card-sub">可粘贴新版本，或让模型生成候选版本后择一启用。</p>
          </div>
          <FileText size={18} className="ttc-accent-icon" />
        </div>

        {canEdit && (
          <>
            <label className="ttc-login-field ttc-field-block">
              <span>粘贴新 JD（至少 20 字）</span>
              <textarea
                rows={6}
                value={jdDraft}
                onChange={(event) => setJdDraft(event.target.value)}
                placeholder="粘贴岗位描述…"
              />
            </label>
            <div className="ttc-form-actions">
              <button
                type="button"
                className="ttc-btn ttc-btn-primary ttc-btn-sm"
                disabled={jdDraft.trim().length < 20 || saveVersion.isPending}
                onClick={() => saveVersion.mutate()}
              >
                保存为新版本并启用
              </button>
            </div>

            <label className="ttc-login-field ttc-field-block">
              <span>AI 生成 JD</span>
              <textarea
                rows={3}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="例如：为技术部生成一名后端工程师 JD，要求 3 年以上 Python 经验"
              />
            </label>
            <div className="ttc-form-actions">
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                disabled={prompt.trim().length < 10 || generate.isPending}
                onClick={() => generate.mutate()}
              >
                <Sparkles size={15} />
                {generate.isPending ? '生成中…' : '生成 JD 版本'}
              </button>
            </div>
          </>
        )}

        <div className="ttc-version-list">
          {versions.map((version) => (
            <div
              key={version.id}
              className={`ttc-version-row ${
                version.id === job?.current_version_id ? 'is-current' : ''
              }`}
            >
              <div className="ttc-version-head">
                <strong>v{version.version_no}</strong>
                <span className="ttc-badge ttc-badge-blue">{version.source}</span>
                {version.id === job?.current_version_id && (
                  <span className="ttc-badge ttc-badge-green">当前</span>
                )}
                {version.created_at && (
                  <span className="ttc-muted">{formatDateTime(version.created_at)}</span>
                )}
              </div>
              <p>{version.jd_text.slice(0, 220)}</p>
              {canEdit && version.id !== job?.current_version_id && (
                <button
                  type="button"
                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                  onClick={() => useVersion.mutate(version)}
                >
                  设为当前
                </button>
              )}
            </div>
          ))}
          {versions.length === 0 && <p className="ttc-muted">还没有 JD 版本。</p>}
        </div>
      </article>
    </div>
  )
}
