import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, Briefcase, Plus, RefreshCw } from 'lucide-react'
import { listSavedJobs } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'

export default function JobListPage() {
  const jobsQuery = useQuery({
    queryKey: ['savedJobs'],
    queryFn: listSavedJobs,
  })

  const jobs = jobsQuery.data ?? []

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            JOB PORTFOLIO
            <span className="hero-eyebrow-line" />
            <span>POSITIONS</span>
          </div>
          <h1>岗位管理</h1>
          <p>管理已保存的岗位画像、评分维度与后续候选人筛选流程。</p>
        </div>
        <div className="ttc-heading-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => void jobsQuery.refetch()}
          >
            <RefreshCw size={15} className={jobsQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
          <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
            <Plus size={16} />
            新建岗位
          </Link>
        </div>
      </section>

      {jobsQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取岗位列表</strong>
            <span>{getApiErrorMessage(jobsQuery.error, '请确认后端服务已启动。')}</span>
          </div>
          <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm" onClick={() => void jobsQuery.refetch()}>
            重试
          </button>
        </div>
      )}

      {jobsQuery.isLoading && (
        <div className="ttc-job-grid">
          <div className="ttc-card ttc-skeleton-card" />
          <div className="ttc-card ttc-skeleton-card" />
          <div className="ttc-card ttc-skeleton-card" />
        </div>
      )}

      {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
        <div className="ttc-card ttc-empty-large">
          <Briefcase size={30} />
          <h2>还没有保存的岗位</h2>
          <p>从一段岗位描述开始，AI 会提取结构化信息并生成可编辑的评分维度。</p>
          <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
            <Plus size={16} />
            创建第一个岗位
          </Link>
        </div>
      )}

      {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && (
        <div className="ttc-job-grid">
          {jobs.map((job) => (
            <Link
              key={job.name}
              to={`/jobs/${encodeURIComponent(job.name)}`}
              className="ttc-card ttc-job-card"
            >
              <div className="ttc-job-card-top">
                <span className="ttc-job-icon">
                  <Briefcase size={18} />
                </span>
                <span className="ttc-badge ttc-badge-blue">已保存</span>
              </div>
              <h3>{job.role_title}</h3>
              <p>{job.name}</p>
              <div className="ttc-job-card-foot">
                <span>更新于 {formatDateTime(job.updated_at)}</span>
                <ArrowRight size={15} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
