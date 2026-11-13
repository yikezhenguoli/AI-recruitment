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
import { getHealth } from '../api/client'
import { listSavedJobs } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import { useSessionStore } from '../store/sessionStore'
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
    description: '粘贴 JD，由 DeepSeek 解析并生成可复核的评分维度。',
    to: '/jobs/new',
    action: '进入',
  },
  {
    index: '02',
    title: '上传简历',
    description: '批量上传 PDF / DOCX，实时查看真实处理进度。',
    to: '/candidates',
    action: '查看',
  },
  {
    index: '03',
    title: '评估报告',
    description: '查看岗位适配参考分与评分理由，人工复核后导出。',
    to: '/candidates',
    action: '查看',
  },
]

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
  const health = healthQuery.data

  const backendValue = healthQuery.isLoading
    ? '检测中'
    : healthQuery.isError
      ? '离线'
      : health?.status === 'ok'
        ? '在线'
        : '异常'

  const llmValue = healthQuery.isLoading
    ? '检测中'
    : healthQuery.isError
      ? '无法检测'
      : health?.llm_configured
        ? '已配置'
        : '待配置'

  const backendTone: Tone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : health?.status === 'ok'
        ? 'ok'
        : 'warn'

  const llmTone: Tone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : health?.llm_configured
        ? 'ok'
        : 'warn'

  const llmHint = health
    ? `${health.provider} · ${health.model}`
    : healthQuery.isError
      ? '无法读取 /health'
      : '等待健康检查返回供应商信息'

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
              LIVE WORKSPACE
              <span className="lg2-eyebrow-line" aria-hidden="true" />
              AI TALENT INTELLIGENCE
            </div>

            {/* Kept inside .ttc-page-head so the existing type-jitter animation still applies. */}
            <div className="ttc-page-head lg2-hero-title">
              <h1 id="lg2-home-title">招聘工作台</h1>
            </div>

            <p className="lg2-hero-lead">
              从岗位画像、简历筛选到评估报告，当前页面展示的岗位与会话状态均来自真实后端接口。
              AI 负责结构化辅助，最终判断由招聘人员完成。
            </p>

            <div className="lg2-flowline" aria-label="AI 招聘工作流">
              <span>岗位画像</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>简历筛选</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>评估报告</span>
              <em>AI 工作流</em>
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
              <span className={`lg2-chip is-${llmTone}`}>
                <Cpu size={14} aria-hidden="true" />
                LLM · {llmValue}
              </span>
              <span className="lg2-trust">
                <ShieldCheck size={14} aria-hidden="true" />
                AI 辅助决策 · 人工最终复核
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
              <span>已保存岗位</span>
              <Briefcase size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {jobsQuery.isLoading ? (
                <span className="lg2-skeleton-block" style={{ width: 88, height: 46 }} aria-hidden="true" />
              ) : (
                <>
                  <CountUp
                    value={jobs.length}
                    ariaLabel={`${jobs.length} 个已保存岗位`}
                  />
                  <span className="lg2-kpi-unit">个岗位</span>
                </>
              )}
            </strong>
            <span className="lg2-kpi-watermark" aria-hidden="true">
              SAVED JOBS
            </span>
            <p className="lg2-kpi-hint">
              {jobsQuery.isLoading
                ? '正在读取真实岗位档案…'
                : jobsQuery.isError
                  ? '岗位档案读取失败，可在下方重试'
                  : '来自 /api/jobs/saved · 真实岗位档案'}
            </p>
          </article>

          <article className="lg2-kpi lg2-kpi--session">
            <div className="lg2-kpi-head">
              <span>当前筛选会话</span>
              <Users size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{session ? '进行中' : '未开始'}</strong>
            {session ? (
              <p className="lg2-kpi-hint">
                {session.jobRoleTitle || session.jobName || '已选择岗位'} · 候选人文件{' '}
                <CountUp
                  value={session.totalFiles}
                  duration={800}
                  ariaLabel={`${session.totalFiles} 份候选人文件`}
                />{' '}
                份
              </p>
            ) : (
              <Link to="/candidates" className="lg2-kpi-hint lg2-kpi-hint--link">
                前往候选人筛选
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            )}
          </article>

          <article className="lg2-kpi lg2-kpi--backend">
            <div className="lg2-kpi-head">
              <span>后端状态</span>
              <Activity size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{backendValue}</strong>
            <p className="lg2-kpi-hint">健康检查 /health · 每 30 秒轮询</p>
          </article>

          <article className="lg2-kpi lg2-kpi--llm">
            <div className="lg2-kpi-head">
              <span>LLM 配置</span>
              <Cpu size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{llmValue}</strong>
            <p className="lg2-kpi-hint">{llmHint}</p>
          </article>
        </section>
      </Reveal>

      <Reveal delay={70}>
        <section className="lg2-main-grid">
          <article className="lg2-panel lg2-panel--jobs">
            <header className="lg2-panel-head">
              <div>
                <span className="lg2-kicker">SAVED JOB PROFILES</span>
                <h2 className="lg2-panel-title">近期岗位</h2>
                <p className="lg2-panel-sub">已保存的岗位画像与评分维度 · 点击进入岗位详情</p>
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

            <div
              className="lg2-job-list lg2-data-surface"
              aria-busy={jobsQuery.isLoading}
            >
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
                    <span>
                      {getApiErrorMessage(
                        jobsQuery.error,
                        '请确认后端服务已启动。',
                      )}
                    </span>
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
                  <strong>暂无已保存岗位</strong>
                  <span>创建第一个岗位后，它会以真实数据出现在这里。</span>
                  <Link to="/jobs/new" className="lg2-btn lg2-btn--primary lg2-btn--sm">
                    <Plus size={15} aria-hidden="true" />
                    新建岗位
                  </Link>
                </div>
              )}

              {!jobsQuery.isLoading &&
                !jobsQuery.isError &&
                jobs.slice(0, 4).map((job, index) => (
                  <Link
                    key={job.name}
                    to={`/jobs/${encodeURIComponent(job.name)}`}
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
                      <strong>{job.role_title}</strong>
                      <span>{job.name}</span>
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
                数据来源 <code>/api/jobs/saved</code>
              </span>
              <span>列表顺序以接口返回为准</span>
            </footer>
          </article>

          <aside className="lg2-rail" aria-label="招聘流程与接入范围">
            <article className="lg2-panel lg2-rail-panel">
              <header>
                <span className="lg2-kicker">WORKFLOW</span>
                <h2 className="lg2-panel-title">开始一条招聘流程</h2>
                <p className="lg2-panel-sub">当前版本优先打通真实 AI 闭环</p>
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
                    <Link
                      to={step.to}
                      aria-label={`${step.action}：${step.title}`}
                    >
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
                  岗位解析、简历处理、评分与导出使用当前 /api/* 真实接口。
                </li>
                <li>
                  <span className="lg2-dot lg2-dot--amber" aria-hidden="true" />
                  证据中心与管理后台为下一阶段范围；候选人详情、评估报告与本地语音波形预览已接入。
                </li>
                <li>
                  <span className="lg2-dot lg2-dot--blue" aria-hidden="true" />
                  当前版本尚未对齐正式 /api/v1 契约，后续通过兼容层评估。
                </li>
              </ul>
              <div className="lg2-scope-links">
                <Link to="/sessions" className="lg2-link">
                  语音会话（本地波形预览）
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
