import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Briefcase,
  Cpu,
  Database,
  Plus,
  RefreshCw,
  Sparkles,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getHealth } from '../api/client'
import { listSavedJobs } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useSessionStore } from '../store/sessionStore'

function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string
  value: string
  hint: string
  icon: LucideIcon
  tone: 'blue' | 'green' | 'amber' | 'violet'
}) {
  return (
    <article className="ttc-card ttc-kpi-card">
      <div className="ttc-kpi-top">
        <span>{label}</span>
        <span className={`ttc-kpi-icon ttc-kpi-icon-${tone}`}>
          <Icon size={17} />
        </span>
      </div>
      <strong className="ttc-kpi-value">{value}</strong>
      <span className="ttc-kpi-hint">{hint}</span>
    </article>
  )
}

export default function WorkbenchHome() {
  const session = useSessionStore((state) => state.session)
  const jobsQuery = useQuery({
    queryKey: ['savedJobs'],
    queryFn: listSavedJobs,
  })
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    retry: 1,
    refetchInterval: 30_000,
  })

  const jobs = jobsQuery.data ?? []
  const health = healthQuery.data

  const backendValue = healthQuery.isLoading
    ? '…'
    : healthQuery.isError
      ? '离线'
      : health?.status === 'ok'
        ? '在线'
        : '异常'

  const llmValue = healthQuery.isLoading
    ? '…'
    : healthQuery.isError
      ? '无法检测'
      : health?.llm_configured
        ? '已配置'
        : '待配置'

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            TALENT OVERVIEW
            <span className="hero-eyebrow-line" />
            <span>AI RECRUITMENT</span>
          </div>
          <h1>招聘工作台</h1>
          <p>从岗位画像到候选人评估，当前页面展示的岗位与会话状态均来自真实后端接口。</p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
            <Plus size={16} />
            新建岗位
          </Link>
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            <Briefcase size={16} />
            岗位管理
          </Link>
        </div>
      </section>

      <section className="ttc-kpi-grid">
        <KpiCard
          label="已保存岗位"
          value={jobsQuery.isLoading ? '—' : String(jobs.length)}
          hint="来自 /api/jobs/saved"
          icon={Briefcase}
          tone="blue"
        />
        <KpiCard
          label="当前筛选会话"
          value={session ? '进行中' : '未开始'}
          hint={session ? `候选人文件 ${session.totalFiles} 份` : '来自本地会话状态'}
          icon={Users}
          tone={session ? 'green' : 'violet'}
        />
        <KpiCard
          label="后端状态"
          value={backendValue}
          hint="来自 /health"
          icon={Activity}
          tone={healthQuery.isError ? 'amber' : 'green'}
        />
        <KpiCard
          label="LLM 配置"
          value={llmValue}
          hint={health ? `${health.provider} · ${health.model}` : 'DeepSeek OpenAI-compatible'}
          icon={Cpu}
          tone={health?.llm_configured ? 'green' : 'amber'}
        />
      </section>

      <section className="ttc-home-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">近期岗位</h2>
              <p className="ttc-card-sub">已保存的岗位画像与评分维度</p>
            </div>
            <div className="ttc-card-actions">
              <button
                type="button"
                className="ttc-icon-btn"
                onClick={() => void jobsQuery.refetch()}
                aria-label="刷新岗位列表"
              >
                <RefreshCw size={15} className={jobsQuery.isFetching ? 'animate-spin' : ''} />
              </button>
              <Link to="/jobs" className="ttc-text-link">
                查看全部 <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          <div className="ttc-job-list">
            {jobsQuery.isLoading && (
              <>
                <div className="ttc-skeleton-row" />
                <div className="ttc-skeleton-row" />
                <div className="ttc-skeleton-row" />
              </>
            )}

            {jobsQuery.isError && (
              <div className="ttc-inline-error">
                <AlertCircle size={16} />
                <div>
                  <strong>无法读取岗位列表</strong>
                  <span>{getApiErrorMessage(jobsQuery.error, '请确认后端服务已启动。')}</span>
                </div>
              </div>
            )}

            {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
              <div className="ttc-empty-state">
                <Database size={24} />
                <strong>暂无已保存岗位</strong>
                <span>创建第一个岗位后，它会出现在这里。</span>
                <Link to="/jobs/new" className="ttc-btn ttc-btn-primary ttc-btn-sm">
                  <Plus size={14} />
                  新建岗位
                </Link>
              </div>
            )}

            {!jobsQuery.isLoading &&
              !jobsQuery.isError &&
              jobs.slice(0, 4).map((job) => (
                <Link
                  key={job.name}
                  to={`/jobs/${encodeURIComponent(job.name)}`}
                  className="ttc-job-row"
                >
                  <span className="ttc-job-icon">
                    <Briefcase size={17} />
                  </span>
                  <span className="ttc-job-meta">
                    <strong>{job.role_title}</strong>
                    <span>{job.name}</span>
                  </span>
                  <span className="ttc-job-time">{formatDateTime(job.updated_at)}</span>
                  <ArrowRight size={15} className="ttc-job-arrow" />
                </Link>
              ))}
          </div>
        </article>

        <div className="ttc-home-side">
          <article className="ttc-card ttc-card-pad">
            <div className="ttc-card-header">
              <div>
                <h2 className="ttc-card-title">开始一条招聘流程</h2>
                <p className="ttc-card-sub">当前版本优先打通真实 AI 闭环</p>
              </div>
              <Sparkles size={17} className="ttc-accent-icon" />
            </div>

            <ol className="ttc-flow-list">
              <li>
                <b>01</b>
                <div>
                  <strong>创建岗位</strong>
                  <span>粘贴 JD，由 DeepSeek 解析并生成评分维度。</span>
                </div>
                <Link to="/jobs/new">进入</Link>
              </li>
              <li>
                <b>02</b>
                <div>
                  <strong>上传简历</strong>
                  <span>批量上传 PDF / DOCX，实时查看处理进度。</span>
                </div>
                <Link to="/candidates">查看</Link>
              </li>
              <li>
                <b>03</b>
                <div>
                  <strong>评估报告</strong>
                  <span>查看岗位适配参考分与评分理由，导出结果。</span>
                </div>
                <Link to="/candidates">查看</Link>
              </li>
            </ol>
          </article>

          <article className="ttc-card ttc-card-pad ttc-scope-card">
            <div className="ttc-mini-heading">
              <Activity size={14} />
              当前接入范围
            </div>
            <ul>
              <li>
                <span className="ttc-dot ttc-dot-green" />
                岗位解析、简历处理、评分与导出使用当前 `/api/*` 真实接口。
              </li>
              <li>
                <span className="ttc-dot ttc-dot-amber" />
                候选人详情、证据中心、语音会话与管理后台为下一阶段范围。
              </li>
              <li>
                <span className="ttc-dot ttc-dot-blue" />
                当前版本尚未对齐正式 `/api/v1` 契约，后续通过兼容层评估。
              </li>
            </ul>
          </article>
        </div>
      </section>
    </div>
  )
}
