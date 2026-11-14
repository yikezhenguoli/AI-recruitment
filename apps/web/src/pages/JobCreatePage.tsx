import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Loader2, Plus, Sparkles } from 'lucide-react'
import { createJob, generateJd } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'

export default function JobCreatePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [jdText, setJdText] = useState('')
  const [generate, setGenerate] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (jdText.trim() && jdText.trim().length < 20) {
      setError('岗位描述至少需要 20 个字符；也可以留空稍后用 AI 生成。')
      return
    }
    if (generate && prompt.trim().length < 10) {
      setError('AI 生成提示词至少需要 10 个字符。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const created = await createJob({
        title: title.trim(),
        department: department.trim() || null,
        headcount: headcount ? Number(headcount) : null,
        jd_text: jdText.trim() ? jdText.trim() : null,
      })
      if (generate) {
        try {
          await generateJd(created.id, { prompt: prompt.trim(), variants: 1 })
        } catch (err: unknown) {
          setError(
            `岗位已创建，但 AI 生成 JD 失败：${getApiErrorMessage(
              err,
              '请检查 DeepSeek 配置。',
            )}`,
          )
          setSubmitting(false)
          navigate(`/jobs/${created.id}`, { replace: false })
          return
        }
      }
      navigate(`/jobs/${created.id}`)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '创建岗位失败。'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            JOB INTAKE
            <span className="hero-eyebrow-line" />
            <span>POST /api/v1/jobs</span>
          </div>
          <h1>新建岗位</h1>
          <p>
            岗位创建后可继续用 DeepSeek 生成/抽取 JD、维护多版本、配置权重并发布。
          </p>
        </div>
        <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
          <ArrowLeft size={16} />
          返回岗位列表
        </Link>
      </section>

      <form className="ttc-card ttc-card-pad ttc-job-form" onSubmit={onSubmit}>
        <div className="ttc-form-grid">
          <label className="ttc-field">
            <span>岗位名称 *</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：AI 后端工程师"
              maxLength={160}
              required
            />
          </label>
          <label className="ttc-field">
            <span>部门</span>
            <input
              value={department}
              onChange={(event) => setDepartment(event.target.value)}
              placeholder="例如：研发中心"
            />
          </label>
          <label className="ttc-field">
            <span>招聘人数</span>
            <input
              type="number"
              min={1}
              value={headcount}
              onChange={(event) => setHeadcount(event.target.value)}
              placeholder="可选"
            />
          </label>
        </div>

        <label className="ttc-field">
          <span>岗位描述（可选，至少 20 字）</span>
          <textarea
            rows={8}
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            placeholder="粘贴现有 JD，或留空后在岗位详情页用 AI 生成。"
            maxLength={20000}
          />
        </label>

        <label className="ttc-checkbox">
          <input
            type="checkbox"
            checked={generate}
            onChange={(event) => setGenerate(event.target.checked)}
          />
          <span>
            创建后立即用 DeepSeek 生成一版 JD 草稿
            <small>会调用 POST /jobs/{'{id}'}/jd/generate，并写入新的 JD 版本。</small>
          </span>
        </label>

        {generate && (
          <label className="ttc-field">
            <span>AI 生成提示词 *</span>
            <textarea
              rows={4}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="例如：招聘一名 3 年以上经验的 AI 后端工程师，负责 FastAPI 服务、LLM 接入与数据管线。"
              maxLength={5000}
            />
          </label>
        )}

        {error && (
          <div className="ttc-inline-error" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="ttc-card-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            取消
          </Link>
          <button type="submit" className="ttc-btn ttc-btn-primary" disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                正在创建…
              </>
            ) : generate ? (
              <>
                <Sparkles size={16} />
                创建并生成 JD
              </>
            ) : (
              <>
                <Plus size={16} />
                创建岗位
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
