import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, Briefcase, Sparkles } from 'lucide-react'
import { createJob } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'

export default function JobCreatePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [jdText, setJdText] = useState('')
  const [error, setError] = useState('')

  const create = useMutation({
    mutationFn: () =>
      createJob({
        title: title.trim(),
        department: department.trim() || null,
        headcount: headcount ? Number(headcount) : null,
        jd_text: jdText.trim() ? jdText.trim() : null,
      }),
    onSuccess: (job) => navigate(`/jobs/${job.id}`, { replace: true }),
    onError: (err) => setError(getApiErrorMessage(err, '创建岗位失败。')),
  })

  const jdTooShort = jdText.trim().length > 0 && jdText.trim().length < 20

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            NEW POSITION
            <span className="hero-eyebrow-line" />
            <span>JOB INTAKE</span>
          </div>
          <h1>新建岗位</h1>
          <p>先建岗位骨架，再在详情页粘贴或让模型生成 JD，选定版本后发布。</p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={15} />
            返回列表
          </Link>
        </div>
      </section>

      <form
        className="ttc-card ttc-form-card"
        onSubmit={(event) => {
          event.preventDefault()
          if (!title.trim() || jdTooShort) return
          setError('')
          create.mutate()
        }}
      >
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">岗位信息</h2>
            <p className="ttc-card-sub">岗位名称必填；JD 可以稍后补充。</p>
          </div>
          <Briefcase size={18} className="ttc-accent-icon" />
        </div>

        <div className="ttc-form-grid">
          <label className="ttc-login-field">
            <span>岗位名称</span>
            <input
              value={title}
              maxLength={160}
              required
              placeholder="例如：后端工程师"
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label className="ttc-login-field">
            <span>部门</span>
            <input
              value={department}
              placeholder="例如：技术部"
              onChange={(event) => setDepartment(event.target.value)}
            />
          </label>
          <label className="ttc-login-field">
            <span>招聘人数</span>
            <input
              type="number"
              min={1}
              value={headcount}
              placeholder="留空表示不限"
              onChange={(event) => setHeadcount(event.target.value)}
            />
          </label>
        </div>

        <label className="ttc-login-field ttc-field-block">
          <span>岗位描述（可选，至少 20 字）</span>
          <textarea
            rows={10}
            value={jdText}
            placeholder="粘贴完整的岗位描述；留空则创建后通过模型生成。"
            onChange={(event) => setJdText(event.target.value)}
          />
        </label>

        {jdTooShort && <p className="ttc-inline-hint">JD 少于 20 字，后端会拒绝保存。</p>}
        {error && (
          <div className="ttc-inline-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="ttc-form-actions">
          <button
            type="submit"
            className="ttc-btn ttc-btn-primary"
            disabled={create.isPending || !title.trim() || jdTooShort}
          >
            <Sparkles size={16} />
            {create.isPending ? '创建中…' : '创建岗位'}
          </button>
        </div>
      </form>
    </div>
  )
}
