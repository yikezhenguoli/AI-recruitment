import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, Briefcase, Plus, RefreshCw } from 'lucide-react'
import { listJobs } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { JobStatus } from '../types'

const STATUS_LABEL: Record<JobStatus, string> = {
  draft: '草稿',
  published: '已发布',
  locked: '已锁定',
  archived: '已归档',
}

const STATUS_CLASS: Record<JobStatus, string> = {
  draft: 'ttc-badge-amber',
  published: 'ttc-badge-green',
  locked: 'ttc-badge-blue',
  archived: 'ttc-badge-red',
}

export default function JobListPage() {
  const [status, setStatus] = useState<'all' | JobStatus>('all')
  const jobsQuery = useQuery({
    queryKey: ['jobs', status],
    queryFn: () => listJobs(status === 'all' ? {} : { status }),
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
          <p>维护岗位、JD 版本与评分权重；发布后的岗位才能接受候选人投递。</p>
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

      <div className="ttc-filter-chips">
        {(
          [
            ['all', '全部'],
            ['draft', '草稿'],
            ['published', '已发布'],
            ['locked', '已锁定'],
            ['archived', '已归档'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`ttc-chip ${status === value ? 'ttc-chip-blue' : ''}`}
            onClick={() => setStatus(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {jobsQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取岗位列表</strong>
            <span>{getApiErrorMessage(jobsQuery.error, '请确认后端服务已启动。')}</span>
          </div>
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary ttc-btn-sm"
            onClick={() => void jobsQuery.refetch()}
          >
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
          <h2>这个筛选下没有岗位</h2>
          <p>创建岗位后可以粘贴 JD、让模型抽取结构化要求，再发布给候选人。</p>
          <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
            <Plus size={16} />
            创建岗位
          </Link>
        </div>
      )}

      {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && (
        <div className="ttc-job-grid">
          {jobs.map((job) => (
            <Link key={job.id} to={`/jobs/${job.id}`} className="ttc-card ttc-job-card">
              <div className="ttc-job-card-top">
                <span className="ttc-job-icon">
                  <Briefcase size={18} />
                </span>
                <span className={`ttc-badge ${STATUS_CLASS[job.status]}`}>
                  {STATUS_LABEL[job.status]}
                </span>
              </div>
              <h3>{job.title}</h3>
              <p>{job.department ?? '未设置部门'}</p>
              <div className="ttc-job-meta">
                <span>在招 {job.headcount ?? '—'} 人</span>
                <span>{job.current_version_id ? '已选 JD 版本' : '暂无 JD'}</span>
              </div>
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
