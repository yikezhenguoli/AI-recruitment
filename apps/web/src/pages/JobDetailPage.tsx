import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CalendarClock,
  GraduationCap,
  Pencil,
  Users,
} from 'lucide-react'
import { getSavedJob } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="ttc-detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const jobName = id ? decodeURIComponent(id) : ''
  const justCreated = Boolean((location.state as { created?: boolean } | null)?.created)

  const jobQuery = useQuery({
    queryKey: ['savedJob', jobName],
    queryFn: () => getSavedJob(jobName),
    enabled: Boolean(jobName),
  })

  if (jobQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      </div>
    )
  }

  if (jobQuery.isError || !jobQuery.data) {
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
            <span>{getApiErrorMessage(jobQuery.error, '该岗位可能已被删除或后端会话已失效。')}</span>
          </div>
        </div>
      </div>
    )
  }

  const job = jobQuery.data
  const structured = job.structured
  const schema = job.scoring_schema
  const totalPoints = schema.dimensions.reduce((sum, dim) => sum + dim.max_points, 0)

  return (
    <div className="ttc-page">
      {justCreated && (
        <div className="ttc-notice">
          <span className="ttc-dot ttc-dot-green" />
          <span>岗位档案已保存。下一步可进入候选人筛选，上传简历并开始 AI 评分。</span>
        </div>
      )}

      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            JOB PROFILE
            <span className="hero-eyebrow-line" />
            <span>{job.name}</span>
          </div>
          <h1>{structured.role_title}</h1>
          <p>岗位画像与评分维度来自已保存的真实岗位数据。</p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={16} />
            返回列表
          </Link>
          <Link to={`/jobs/${encodeURIComponent(job.name)}/edit`} className="ttc-btn ttc-btn-secondary">
            <Pencil size={15} />
            编辑岗位
          </Link>
          <Link to={`/candidates?job=${encodeURIComponent(job.name)}`} className="ttc-btn ttc-btn-primary">
            <Users size={16} />
            开始候选人筛选
          </Link>
        </div>
      </section>

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">岗位结构化信息</h2>
              <p className="ttc-card-sub">由 AI 从岗位描述中提取</p>
            </div>
            <span className="ttc-job-icon">
              <Briefcase size={18} />
            </span>
          </div>

          <div className="ttc-detail-rows">
            <DetailRow label="岗位名称" value={job.name} />
            <DetailRow label="资历要求" value={structured.seniority_level || '未明确'} />
            <DetailRow
              label="经验年限"
              value={
                structured.min_years_experience != null
                  ? `${structured.min_years_experience} 年以上`
                  : '未明确'
              }
            />
            <DetailRow
              label="学历要求"
              value={
                structured.education_requirements?.level ||
                structured.education_requirements?.field ||
                '未明确'
              }
            />
            <DetailRow label="最近更新" value={formatDateTime(job.updated_at)} />
          </div>

          <div className="ttc-skill-groups">
            <div>
              <h3>必备技能</h3>
              <div className="ttc-chip-list">
                {structured.required_skills.length > 0 ? (
                  structured.required_skills.map((skill) => (
                    <span key={skill} className="ttc-chip ttc-chip-blue">
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="ttc-muted">未提取到必备技能</span>
                )}
              </div>
            </div>
            <div>
              <h3>优先技能</h3>
              <div className="ttc-chip-list">
                {structured.preferred_skills.length > 0 ? (
                  structured.preferred_skills.map((skill) => (
                    <span key={skill} className="ttc-chip">
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="ttc-muted">未提取到优先技能</span>
                )}
              </div>
            </div>
          </div>

          <div className="ttc-responsibility-block">
            <h3>岗位职责</h3>
            {structured.responsibilities.length > 0 ? (
              <ul>
                {structured.responsibilities.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="ttc-muted">未提取到岗位职责。</p>
            )}
          </div>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">评分维度</h2>
              <p className="ttc-card-sub">
                {schema.dimensions.length} 个维度 · 合计 {totalPoints} 分
              </p>
            </div>
            <CalendarClock size={18} className="ttc-accent-icon" />
          </div>

          <div className="ttc-dimension-list">
            {schema.dimensions.map((dimension) => (
              <div key={dimension.name} className="ttc-dimension-row">
                <div className="ttc-dimension-head">
                  <strong>{dimension.label}</strong>
                  <span>{dimension.max_points} 分</span>
                </div>
                <p>{dimension.description}</p>
                <div className="ttc-progress-track">
                  <i style={{ width: `${Math.min(100, (dimension.max_points / 100) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>

          {schema.dimensions.length === 0 && (
            <div className="ttc-empty-state ttc-empty-compact">
              <GraduationCap size={20} />
              <strong>该岗位没有评分维度</strong>
              <span>请编辑岗位或重新解析 JD。</span>
            </div>
          )}
        </article>
      </section>

      <section className="ttc-card ttc-card-pad">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">原始岗位描述</h2>
            <p className="ttc-card-sub">保存时的 JD 原文</p>
          </div>
          <ArrowRight size={16} className="ttc-muted-icon" />
        </div>
        <pre className="ttc-jd-text">{job.jd_text}</pre>
      </section>
    </div>
  )
}
