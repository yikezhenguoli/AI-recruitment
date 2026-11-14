import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Briefcase,
  Cpu,
  Database,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { getHealth, getReadiness } from '../api/client'
import { listJobs } from '../api/jobs'
import { listCandidates } from '../api/candidates'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useAuthStore } from '../store/authStore'
import { JOB_STATUS_LABEL } from '../types'
import { CinematicBackground } from '../components/visual/CinematicBackground'
import { CountUp } from '../components/visual/CountUp'
import { NetworkField } from '../components/visual/NetworkField'
import { PremiumWaveform } from '../components/visual/PremiumWaveform'
import { Reveal } from '../components/visual/Reveal'
import { TalentOrbit } from '../components/visual/TalentOrbit'

type Tone = 'ok' | 'warn' | 'danger' | 'neutral'

const STEPS = [
  {
    index: '01',
    title: '创建岗位',
    description: '创建岗位后用 DeepSeek 生成或抽取 JD，配置权重并发布。',
    to: '/jobs/new',
    action: '进入',
  },
  {
    index: '02',
    title: '上传简历',
    description: '为候选人上传 PDF / DOCX，后端 worker 解析原文并生成 claims。',
    to: '/candidates',
    action: '查看',
  },
  {
    index: '03',
    title: '匹配与报告',
    description: '小模型匹配 + DeepSeek 解释 + 确定性评估，人工复核后导出 JSON。',
    to: '/candidates',
    action: '查看',
  },
]

export default function WorkbenchHome() {
  const user = useAuthStore((state) => state.user)
  const jobsQuery = useQuery({
    queryKey: ['jobs', 'home'],
    queryFn: () => listJobs({ limit: 100 }),
  })
  const candidatesQuery = useQuery({
    queryKey: ['candidates', 'home'],
    queryFn: () => listCandidates({ limit: 100 }),
  })
  const healthQuery = useQuery({
    queryKey: ['health', 'live'],
    queryFn: getHealth,
    retry: 1,
    refetchInterval: 30_000,
  })
  const readyQuery = useQuery({
    queryKey: ['health', 'ready'],
    queryFn: getReadiness,
    retry: 1,
    refetchInterval: 30_000,
  })

  const [waveMotion, setWaveMotion] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true
    }
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setWaveMotion(!media.matches)
    sync()
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', sync)
      return () => media.removeEventListener('change', sync)
    }
    media.addListener(sync)
    return () => media.removeListener(sync)
  }, [])

  const jobs = jobsQuery.data ?? []
  const candidates = candidatesQuery.data ?? []

  const backendValue = healthQuery.isLoading
    ? '检测中'
    : healthQuery.isError
      ? '离线'
      : '在线'

  const dbValue = readyQuery.isLoading
    ? '检测中'
    : readyQuery.isError
      ? '异常'
      : readyQuery.data?.status === 'ready'
        ? '就绪'
        : '未知'

  const backendTone: Tone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : 'ok'

  const dbTone: Tone = readyQuery.isLoading
    ? 'neutral'
    : readyQuery.isError
      ? 'danger'
      : 'ok'

  const recentJobs = jobs.slice(0, 4)

  return (
    <div className="lg2-home">
      <section className="lg2-hero" aria-labelledby="lg2-home-title">
        <CinematicBackground />
        <div className="lg2-hero-field" aria-hidden="true">
          <NetworkField />
        </div>

        <div className="lg2-hero-grid">
          <div className="lg2-hero-copy">
            <div className="lg2-eyebrow">
              <span className="lg2-eyebrow-dot" aria-hidden="true" />
              AUTHENTICATED WORKSPACE
              <span className="lg2-eyebrow-line" aria-hidden="true" />
              TTC /api/v1
            </div>

            <div className="ttc-page-head lg2-hero-title">
              <h1 id="lg2-home-title">招聘工作台</h1>
            </div>

            <p className="lg2-hero-lead">
              岗位、候选人、简历解析、匹配评估与语音会话均来自真实 /api/v1 接口；
              当前登录身份为 {user?.display_name ?? '招聘管理员'}。AI 只做辅助，最终判断由招聘人员完成。
            </p>

            <div className="lg2-flowline" aria-label="AI 招聘工作流">
              <span>岗位画像</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>简历解析</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>匹配评估</span>
              <em>真实链路</em>
            </div>

            <div className="lg2-hero-actions">
              <Link to="/jobs/new" className="lg2-btn lg2-btn--primary">
                <Plus size={17} aria-hidden="true" />
                新建岗位
              </Link>
              <Link to="/candidates" className="lg2-btn lg2-btn--glass">
                <Users size={17} aria-hidden="true" />
                进入候选人筛选
              </Link>
              <Link to="/jobs" className="lg2-link">
                岗位管理
                <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            </div>

            <div className="lg2-hero-status">
              <span className={`lg2-chip is-${backendTone}`}>
                <Activity size={14} aria-hidden="true" />
                后端 · {backendValue}
              </span>
              <span className={`lg2-chip is-${dbTone}`}>
                <Database size={14} aria-hidden="true" />
                数据库 · {dbValue}
              </span>
              <span className="lg2-trust">
                <ShieldCheck size={14} aria-hidden="true" />
                Bearer 鉴权 · 租户隔离 · 人工复核
              </span>
            </div>
          </div>

          <article className="lg2-panel lg2-panel--focal lg2-orbit-panel">
            <header className="lg2-orbit-head">
              <div>
                <span className="lg2-kicker">TALENT SIGNAL ORBIT</span>
                <h2 className="lg2-panel-title">AI 招聘工作流</h2>
              </div>
              <span className="lg2-orbit-note">工作流示意 · 非实时统计</span>
            </header>
            <TalentOrbit />
          </article>
        </div>
      </section>

      <div className="lg2-ambient-wave" role="group" aria-label="首页环境波形">
        <div className="lg2-ambient-wave-head">
          <span>TALENT SIGNAL</span>
          <span className="lg2-ambient-wave-head-right">
            <span>视觉氛围 · 非实时数据</span>
            <button
              type="button"
              className="lg2-ambient-wave-toggle"
              onClick={() => setWaveMotion((current) => !current)}
              aria-pressed={waveMotion}
              aria-label={waveMotion ? '暂停首页环境波形动效' : '开启首页环境波形动效'}
              title={waveMotion ? '暂停首页环境波形动效' : '开启首页环境波形动效'}
            >
              {waveMotion ? <Pause size={12} aria-hidden="true" /> : <Play size={12} aria-hidden="true" />}
              动效 {waveMotion ? '开' : '关'}
            </button>
          </span>
        </div>
        <PremiumWaveform tone="subtle" height={140} motionOverride={waveMotion} />
      </div>

      <Reveal>
        <section className="lg2-kpi-strip" aria-label="工作台实时状态">
          <article className="lg2-kpi lg2-kpi--xl">
            <div className="lg2-kpi-head">
              <span>岗位</span>
              <Briefcase size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {jobsQuery.isLoading ? (
                <span className="lg2-skeleton-block" style={{ width: 88, height: 46 }} aria-hidden="true" />
              ) : (
                <>
                  <CountUp value={jobs.length} ariaLabel={`${jobs.length} 个岗位`} />
                  <span className="lg2-kpi-unit">个</span>
                </>
              )}
            </strong>
            <span className="lg2-kpi-watermark" aria-hidden="true">
              JOBS
            </span>
            <p className="lg2-kpi-hint">来自 /api/v1/jobs · 当前租户</p>
          </article>

          <article className="lg2-kpi lg2-kpi--session">
            <div className="lg2-kpi-head">
              <span>候选人</span>
              <Users size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {candidatesQuery.isLoading ? '…' : candidates.length}
            </strong>
            <Link to="/candidates" className="lg2-kpi-hint lg2-kpi-hint--link">
              进入候选人筛选
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </article>

          <article className="lg2-kpi lg2-kpi--backend">
            <div className="lg2-kpi-head">
              <span>后端状态</span>
              <Activity size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{backendValue}</strong>
            <p className="lg2-kpi-hint">/api/v1/health/live · 30 秒轮询</p>
          </article>

          <article className="lg2-kpi lg2-kpi--llm">
            <div className="lg2-kpi-head">
              <span>数据库</span>
              <Cpu size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{dbValue}</strong>
            <p className="lg2-kpi-hint">/api/v1/health/ready · PostgreSQL</p>
          </article>
        </section>
      </Reveal>

      <Reveal delay={70}>
        <section className="lg2-main-grid">
          <article className="lg2-panel lg2-panel--jobs">
            <header className="lg2-panel-head">
              <div>
                <span className="lg2-kicker">RECENT JOBS</span>
                <h2 className="lg2-panel-title">近期岗位</h2>
                <p className="lg2-panel-sub">来自 /api/v1/jobs · 点击进入岗位详情</p>
              </div>
              <div className="lg2-panel-actions">
                <button
                  type="button"
                  className="lg2-icon-btn"
                  onClick={() => void jobsQuery.refetch()}
                  aria-label="刷新岗位列表"
                  title="刷新岗位列表"
                >
                  <RefreshCw
                    size={16}
                    className={jobsQuery.isFetching ? 'lg2-spin' : ''}
                    aria-hidden="true"
                  />
                </button>
                <Link to="/jobs" className="lg2-link">
                  查看全部
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              </div>
            </header>

            <div className="lg2-job-list lg2-data-surface" aria-busy={jobsQuery.isLoading}>
              {jobsQuery.isLoading && (
                <>
                  {[0, 1, 2].map((row) => (
                    <div className="lg2-skeleton-row" key={row} aria-hidden="true">
                      <span className="lg2-skeleton-block lg2-skeleton-block--pill" />
                      <span className="lg2-skeleton-block lg2-skeleton-block--icon" />
                      <span>
                        <span className="lg2-skeleton-block" style={{ width: '62%' }} />
                        <span
                          className="lg2-skeleton-block lg2-skeleton-block--pill"
                          style={{ marginTop: 8 }}
                        />
                      </span>
                      <span className="lg2-skeleton-block lg2-skeleton-block--pill" />
                      <span />
                    </div>
                  ))}
                </>
              )}

              {jobsQuery.isError && (
                <div className="lg2-inline-error" role="alert">
                  <AlertCircle size={18} aria-hidden="true" />
                  <div>
                    <strong>无法读取岗位列表</strong>
                    <span>{getApiErrorMessage(jobsQuery.error, '请确认后端服务已启动。')}</span>
                  </div>
                  <button
                    type="button"
                    className="lg2-btn lg2-btn--glass lg2-btn--sm"
                    onClick={() => void jobsQuery.refetch()}
                  >
                    <RefreshCw size={14} aria-hidden="true" />
                    重试
                  </button>
                </div>
              )}

              {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
                <div className="lg2-empty-state">
                  <Database size={26} aria-hidden="true" />
                  <strong>暂无岗位</strong>
                  <span>创建第一个岗位后，它会以真实数据出现在这里。</span>
                  <Link to="/jobs/new" className="lg2-btn lg2-btn--primary lg2-btn--sm">
                    <Plus size={15} aria-hidden="true" />
                    新建岗位
                  </Link>
                </div>
              )}

              {!jobsQuery.isLoading &&
                !jobsQuery.isError &&
                recentJobs.map((job, index) => (
                  <Link
                    key={job.id}
                    to={`/jobs/${job.id}`}
                    className="lg2-job-row"
                    style={{ animationDelay: `${index * 60}ms` }}
                  >
                    <span className="lg2-job-index">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="lg2-job-icon">
                      <Briefcase size={18} aria-hidden="true" />
                    </span>
                    <span className="lg2-job-meta">
                      <strong>{job.title}</strong>
                      <span>
                        {job.department || '未设置部门'} · {JOB_STATUS_LABEL[job.status]}
                      </span>
                    </span>
                    <time className="lg2-job-time" dateTime={job.updated_at}>
                      {formatDateTime(job.updated_at)}
                    </time>
                    <ArrowRight className="lg2-job-arrow" size={16} aria-hidden="true" />
                  </Link>
                ))}
            </div>

            <footer className="lg2-panel-foot">
              <span>
                数据来源 <code>/api/v1/jobs</code>
              </span>
              <span>Bearer 鉴权 · 租户隔离</span>
            </footer>
          </article>

          <aside className="lg2-rail" aria-label="招聘流程与接入范围">
            <article className="lg2-panel lg2-rail-panel">
              <header>
                <span className="lg2-kicker">WORKFLOW</span>
                <h2 className="lg2-panel-title">开始一条招聘流程</h2>
                <p className="lg2-panel-sub">全部使用真实后端接口</p>
              </header>

              <ol className="lg2-step-list">
                {STEPS.map((step) => (
                  <li className="lg2-step" key={step.index}>
                    <span className="lg2-step-index" aria-hidden="true">
                      {step.index}
                    </span>
                    <div className="lg2-step-body">
                      <strong>{step.title}</strong>
                      <span>{step.description}</span>
                    </div>
                    <Link to={step.to} aria-label={`${step.action}：${step.title}`}>
                      {step.action}
                    </Link>
                  </li>
                ))}
              </ol>
            </article>

            <article className="lg2-panel lg2-panel--inline lg2-scope-panel">
              <div className="lg2-scope-head">
                <Activity size={15} aria-hidden="true" />
                当前接入范围
              </div>
              <ul className="lg2-scope-list">
                <li>
                  <span className="lg2-dot lg2-dot--green" aria-hidden="true" />
                  岗位、JD 版本、候选人、简历解析、匹配评估与证据均走 `/api/v1`。
                </li>
                <li>
                  <span className="lg2-dot lg2-dot--amber" aria-hidden="true" />
                  语音会话通过后端中转接入 Qwen Realtime；需候选人先完成语音授权。
                </li>
                <li>
                  <span className="lg2-dot lg2-dot--blue" aria-hidden="true" />
                  管理后台展示数据源、审计日志、任务指标与集成状态。
                </li>
              </ul>
              <div className="lg2-scope-links">
                <Link to="/sessions" className="lg2-link">
                  语音会话
                  <ArrowUpRight size={13} aria-hidden="true" />
                </Link>
                <Link to="/candidates" className="lg2-link">
                  候选人筛选
                  <ArrowRight size={13} aria-hidden="true" />
                </Link>
              </div>
            </article>
          </aside>
        </section>
      </Reveal>
    </div>
  )
}
