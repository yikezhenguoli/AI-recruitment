import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, Plus, RefreshCw, UserPlus, Users } from 'lucide-react'
import { createCandidate, listCandidates } from '../api/candidates'
import { listJobs } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'

export default function CandidatesPage() {
  const queryClient = useQueryClient()
  const [jobFilter, setJobFilter] = useState('')
  const [name, setName] = useState('')
  const [jobId, setJobId] = useState('')
  const [error, setError] = useState('')

  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs({ limit: 100 }) })
  const candidatesQuery = useQuery({
    queryKey: ['candidates', jobFilter],
    queryFn: () => listCandidates(jobFilter ? { job_id: jobFilter } : {}),
  })
  const jobs = jobsQuery.data ?? []
  const candidates = candidatesQuery.data ?? []
  const jobTitle = (id: string | null) => jobs.find((job) => job.id === id)?.title ?? '未绑定岗位'

  const create = useMutation({
    mutationFn: () =>
      createCandidate({ display_name: name.trim(), job_id: jobId || null, source: 'demo' }),
    onSuccess: () => {
      setName('')
      setError('')
      void queryClient.invalidateQueries({ queryKey: ['candidates'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建候选人失败。')),
  })

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            TALENT PIPELINE
            <span className="hero-eyebrow-line" />
            <span>CANDIDATES</span>
          </div>
          <h1>候选人</h1>
          <p>候选人档案聚合简历、声明抽取、评估与语音面试；真实候选人须先取得授权。</p>
        </div>
        <div className="ttc-heading-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => void candidatesQuery.refetch()}
          >
            <RefreshCw size={15} className={candidatesQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </section>

      <section className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">新建合成候选人</h2>
            <p className="ttc-card-sub">
              真实候选人需走授权流程；当前入口只创建合成样本，用于流程联调与演示。
            </p>
          </div>
          <UserPlus size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-launch-form">
          <label className="ttc-login-field">
            <span>姓名</span>
            <input
              value={name}
              required
              maxLength={80}
              placeholder="例如：Alex Chen（合成）"
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="ttc-login-field">
            <span>目标岗位（可选）</span>
            <select value={jobId} onChange={(event) => setJobId(event.target.value)}>
              <option value="">不绑定岗位</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary ttc-launch-submit"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            <Plus size={16} />
            {create.isPending ? '创建中…' : '创建候选人'}
          </button>
        </div>
        {error && (
          <div className="ttc-inline-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
      </section>

      <div className="ttc-filter-chips">
        <button
          type="button"
          className={`ttc-chip ${jobFilter === '' ? 'ttc-chip-blue' : ''}`}
          onClick={() => setJobFilter('')}
        >
          全部
        </button>
        {jobs.map((job) => (
          <button
            key={job.id}
            type="button"
            className={`ttc-chip ${jobFilter === job.id ? 'ttc-chip-blue' : ''}`}
            onClick={() => setJobFilter(job.id)}
          >
            {job.title}
          </button>
        ))}
      </div>

      {candidatesQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取候选人</strong>
            <span>{getApiErrorMessage(candidatesQuery.error)}</span>
          </div>
        </div>
      )}

      {candidatesQuery.isLoading && <div className="ttc-card ttc-skeleton-card" />}

      {!candidatesQuery.isLoading && !candidatesQuery.isError && candidates.length === 0 && (
        <div className="ttc-card ttc-empty-large">
          <Users size={30} />
          <h2>还没有候选人</h2>
          <p>先创建一位合成候选人，再在详情页上传简历并触发解析。</p>
        </div>
      )}

      {candidates.length > 0 && (
        <div className="ttc-table-card">
          <div className="ttc-table-scroll">
            <table className="ttc-result-table">
              <thead>
                <tr>
                  <th>姓名</th>
                  <th>岗位</th>
                  <th>来源</th>
                  <th>类型</th>
                  <th>创建时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => (
                  <tr key={candidate.id}>
                    <td>{candidate.display_name}</td>
                    <td>{jobTitle(candidate.job_id)}</td>
                    <td className="ttc-muted">{candidate.source}</td>
                    <td>
                      <span
                        className={`ttc-badge ${
                          candidate.is_synthetic ? 'ttc-badge-blue' : 'ttc-badge-amber'
                        }`}
                      >
                        {candidate.is_synthetic ? '合成' : '真实'}
                      </span>
                    </td>
                    <td className="ttc-muted">{formatDateTime(candidate.created_at)}</td>
                    <td className="ttc-col-action">
                      <Link className="ttc-text-link" to={`/candidates/${candidate.id}`}>
                        <ArrowRight size={15} />
                        详情
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
