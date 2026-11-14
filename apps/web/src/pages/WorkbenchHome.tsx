import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Briefcase,
  Database,
  Mic,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { getHealth } from '../api/client'
import { listCandidates } from '../api/candidates'
import { listJobs } from '../api/jobs'
import { listVoiceSessions } from '../api/voice'
import { CinematicBackground } from '../components/visual/CinematicBackground'
import { CountUp } from '../components/visual/CountUp'
import { NetworkField } from '../components/visual/NetworkField'
import { PremiumWaveform } from '../components/visual/PremiumWaveform'
import { Reveal } from '../components/visual/Reveal'
import { TalentOrbit } from '../components/visual/TalentOrbit'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime, JOB_STATUS_LABELS, VOICE_STATUS_LABELS } from '../lib/format'
import { useAuthStore } from '../store/authStore'

type Tone = 'ok' | 'warn' | 'danger' | 'neutral'

const STEPS = [
  {
    index: '01',
    title: '创建岗位',
    description: '编写或粘贴 JD，生成版本化岗位画像与可复核的权重维度。',
    to: '/jobs/new',
    action: '新建',
  },
  {
    index: '02',
    title: '简历与证据核验',
    description: '上传 PDF / DOCX，追踪解析任务进度与候选人声明核验等级。',
    to: '/candidates',
    action: '进入',
  },
  {
    index: '03',
    title: 'AI 语音初筛',
    description: '发起实时语音初筛，保留双端转写记录与提问规划。',
    to: '/sessions',
    action: '查看',
  },
  {
    index: '04',
    title: '评估报告与录用',
    description: '分开呈现证据可信度与岗位匹配分，人工复核后推进面试与 Offer。',
    to: '/interviews',
    action: '推进',
  },
]

export default function WorkbenchHome() {
  const user = useAuthStore((state) => state.user)

  const jobsQuery = useQuery({
    queryKey: ['jobs', 'home'],
    queryFn: () => listJobs({ limit: 8 }),
  })

  const candidatesQuery = useQuery({
    queryKey: ['candidates', 'home'],
    queryFn: () => listCandidates(),
  })

  const sessionsQuery = useQuery({
    queryKey: ['voice-sessions', 'home'],
    queryFn: () => listVoiceSessions({ limit: 8 }),
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
  const candidates = candidatesQuery.data ?? []
  const sessions = sessionsQuery.data ?? []
  const health = healthQuery.data

  const publishedCount = jobs.filter((job) => job.status === 'published').length
  const activeSessionsCount = sessions.filter(
    (session) => session.status === 'live' || session.status === 'connecting' || session.status === 'created',
  ).length

  const isHealthy = health?.status === 'ready' || health?.status === 'ok'
  const isDbHealthy = health?.database === 'ok' || health?.database === 'ready'

  const backendValue = healthQuery.isLoading
    ? '检测中'
    : healthQuery.isError
      ? '离线'
      : isHealthy
        ? '在线'
        : '异常'

  const backendTone: Tone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : isHealthy
        ? 'ok'
        : 'warn'

  const databaseValue = healthQuery.isLoading
    ? '检测中'
    : healthQuery.isError
      ? '未连接'
      : health?.database
        ? isDbHealthy
          ? '已连接'
          : health.database
        : '就绪'

  const databaseTone: Tone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : isDbHealthy || Boolean(health)
        ? 'ok'
        : 'warn'

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

            <div className="ttc-page-head lg2-hero-title">
              <h1 id="lg2-home-title">招聘工作台</h1>
            </div>

            <p className="lg2-hero-lead">
              串联岗位画像、简历核验、实时语音初筛与双账本评估报告。展示数据均来自{' '}
              <code>/api/v1</code> 真实接口；AI 负责结构化证据提取，最终录用由招聘人员复核裁决。
            </p>

            <div className="lg2-flowline" aria-label="AI 招聘闭环">
              <span>岗位画像</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>简历核验</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>语音初筛</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span>双账本报告</span>
              <em>人工复核</em>
            </div>

            <div className="lg2-hero-actions">
              <Link to="/jobs/new" className="lg2-btn lg2-btn--primary">
                <Plus size={17} aria-hidden="true" />
                新建岗位
              </Link>
              <Link to="/candidates" className="lg2-btn lg2-btn--glass">
                <Users size={17} aria-hidden="true" />
                候选人筛选
              </Link>
              <Link to="/sessions" className="lg2-link">
                语音初筛台
                <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            </div>

            <div className="lg2-hero-status">
              <span className={`lg2-chip is-${backendTone}`}>
                <Activity size={14} aria-hidden="true" />
                API · {backendValue}
              </span>
              <span className={`lg2-chip is-${databaseTone}`}>
                <Database size={14} aria-hidden="true" />
                DB · {databaseValue}
              </span>
              <span className="lg2-trust">
                <ShieldCheck size={14} aria-hidden="true" />
                {user ? `${user.display_name} (${user.role})` : '双账本独立计算 · 人工最终复核'}
              </span>
            </div>
          </div>

          <article className="lg2-panel lg2-panel--focal lg2-orbit-panel">
            <header className="lg2-orbit-head">
              <div>
                <span className="lg2-kicker">TALENT SIGNAL ORBIT</span>
                <h2 className="lg2-panel-title">全链路协同视图</h2>
              </div>
              <span className="lg2-orbit-note">流程导航 · 非实时统计</span>
            </header>
            <TalentOrbit />
          </article>
        </div>
      </section>

      <div className="lg2-ambient-wave" role="group" aria-label="首页环境波形">
        <div className="lg2-ambient-wave-head">
          <span>ACOUSTIC SIGNAL FIELD</span>
          <span className="lg2-ambient-wave-head-right">
            <span>环境氛围波形 · 语音台支持实时互动</span>
            <button
              type="button"
              className="lg2-ambient-wave-toggle"
              onClick={() => setWaveMotion((current) => !current)}
              aria-pressed={waveMotion}
              aria-label="首页环境波形动效"
              title={waveMotion ? '关闭首页环境波形动效' : '开启首页环境波形动效'}
            >
              {waveMotion ? <Pause size={12} aria-hidden="true" /> : <Play size={12} aria-hidden="true" />}
              动效 {waveMotion ? '开' : '关'}
            </button>
          </span>
        </div>
        <PremiumWaveform tone="subtle" height={140} motionOverride={waveMotion} />
      </div>

      <Reveal>
        <section className="lg2-kpi-strip" aria-label="工作台实时概览">
          <article className="lg2-kpi lg2-kpi--xl">
            <div className="lg2-kpi-head">
              <span>岗位档案</span>
              <Briefcase size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {jobsQuery.isLoading ? (
                <span className="lg2-skeleton-block" style={{ width: 88, height: 46 }} aria-hidden="true" />
              ) : (
                <>
                  <CountUp value={jobs.length} ariaLabel={`${jobs.length} 个岗位`} />
                  <span className="lg2-kpi-unit">个岗位</span>
                </>
              )}
            </strong>
            <span className="lg2-kpi-watermark" aria-hidden="true">
              OPEN ROLES
            </span>
            <p className="lg2-kpi-hint">
              {jobsQuery.isLoading
                ? '正在读取岗位目录…'
                : jobsQuery.isError
                  ? '岗位列表读取失败，可在下方重试'
                  : `其中已发布 ${publishedCount} 个 · /api/v1/jobs`}
            </p>
          </article>

          <article className="lg2-kpi lg2-kpi--session">
            <div className="lg2-kpi-head">
              <span>候选人池</span>
              <Users size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {candidatesQuery.isLoading ? (
                <span className="lg2-skeleton-block" style={{ width: 72, height: 34 }} aria-hidden="true" />
              ) : (
                <>
                  <CountUp value={candidates.length} duration={800} ariaLabel={`${candidates.length} 位候选人`} />
                  <span className="lg2-kpi-unit">位</span>
                </>
              )}
            </strong>
            <Link to="/candidates" className="lg2-kpi-hint lg2-kpi-hint--link">
              查看候选人与双账本报告
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </article>

          <article className="lg2-kpi lg2-kpi--backend">
            <div className="lg2-kpi-head">
              <span>语音初筛会话</span>
              <Mic size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">
              {sessionsQuery.isLoading ? (
                <span className="lg2-skeleton-block" style={{ width: 72, height: 34 }} aria-hidden="true" />
              ) : (
                <>
                  <CountUp value={sessions.length} duration={800} ariaLabel={`${sessions.length} 场语音面试`} />
                  <span className="lg2-kpi-unit">场</span>
                </>
              )}
            </strong>
            <Link to="/sessions" className="lg2-kpi-hint lg2-kpi-hint--link">
              {activeSessionsCount > 0 ? `${activeSessionsCount} 场待接通或进行中` : '进入实时语音初筛台'}
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </article>

          <article className="lg2-kpi lg2-kpi--llm">
            <div className="lg2-kpi-head">
              <span>服务就绪状态</span>
              <Activity size={18} aria-hidden="true" />
            </div>
            <strong className="lg2-kpi-value">{backendValue}</strong>
            <p className="lg2-kpi-hint">
              {healthQuery.isError
                ? getApiErrorMessage(healthQuery.error, '无法连接健康检查端点')
                : `数据库 ${databaseValue} · 每 30 秒巡检`}
            </p>
          </article>
        </section>
      </Reveal>

      <Reveal delay={70}>
        <section className="lg2-main-grid">
          <article className="lg2-panel lg2-panel--jobs">
            <header className="lg2-panel-head">
              <div>
                <span className="lg2-kicker">RECENT JOB PROFILES</span>
                <h2 className="lg2-panel-title">近期岗位</h2>
                <p className="lg2-panel-sub">岗位版本与权重方案概览 · 点击进入详情</p>
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
                  <strong>暂无岗位档案</strong>
                  <span>创建第一个岗位后，系统将同步显示维度权重与候选人推进状态。</span>
                  <Link to="/jobs/new" className="lg2-btn lg2-btn--primary lg2-btn--sm">
                    <Plus size={15} aria-hidden="true" />
                    新建岗位
                  </Link>
                </div>
              )}

              {!jobsQuery.isLoading &&
                !jobsQuery.isError &&
                jobs.slice(0, 5).map((job, index) => (
                  <Link
                    key={job.id}
                    to={`/jobs/${job.id}`}
                    className="lg2-job-row"
                    style={{ animationDelay: `${index * 60}ms` }}
                  >
                    <span className="lg2-job-index">{String(index + 1).padStart(2, '0')}</span>
                    <span className="lg2-job-icon">
                      <Briefcase size={18} aria-hidden="true" />
                    </span>
                    <span className="lg2-job-meta">
                      <strong>{job.title}</strong>
                      <span>
                        {job.department || '未分部门'} · 招 {job.headcount} 人 ·{' '}
                        {JOB_STATUS_LABELS[job.status] ?? job.status}
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
              <span>按最近更新时间排序</span>
            </footer>
          </article>

          <aside className="lg2-rail" aria-label="招聘推进指南与系统边界">
            <article className="lg2-panel lg2-rail-panel">
              <header>
                <span className="lg2-kicker">WORKFLOW</span>
                <h2 className="lg2-panel-title">招聘闭环导航</h2>
                <p className="lg2-panel-sub">从岗位画像到双账本人工复核</p>
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
                近期语音初筛 &amp; 可信原则
              </div>
              {sessions.length > 0 ? (
                <ul className="lg2-scope-list">
                  {sessions.slice(0, 2).map((session) => (
                    <li key={session.id}>
                      <span
                        className={`lg2-dot ${session.status === 'live' ? 'lg2-dot--green' : session.status === 'ended' ? 'lg2-dot--blue' : 'lg2-dot--amber'}`}
                        aria-hidden="true"
                      />
                      <span>
                        <Link to={`/sessions/${session.id}`} className="lg2-link" style={{ display: 'inline' }}>
                          {session.candidate_name || '候选人'} · {session.job_title || '未关联岗位'}
                        </Link>
                        {' '}（{VOICE_STATUS_LABELS[session.status] ?? session.status}）
                      </span>
                    </li>
                  ))}
                  <li>
                    <span className="lg2-dot lg2-dot--blue" aria-hidden="true" />
                    双账本原则：证据可信度与岗位匹配分永远分离展示，低覆盖度自动提示复核。
                  </li>
                </ul>
              ) : (
                <ul className="lg2-scope-list">
                  <li>
                    <span className="lg2-dot lg2-dot--green" aria-hidden="true" />
                    岗位、候选人、证据、语音初筛、面试与 Offer 已全量接入 /api/v1。
                  </li>
                  <li>
                    <span className="lg2-dot lg2-dot--blue" aria-hidden="true" />
                    证据可信度与岗位匹配度独立计算，拒绝单分黑盒排序。
                  </li>
                  <li>
                    <span className="lg2-dot lg2-dot--amber" aria-hidden="true" />
                    敏感核验与语音实时通话前需验证候选人隐私授权记录。
                  </li>
                </ul>
              )}
              <div className="lg2-scope-links">
                <Link to="/talent" className="lg2-link">
                  人才池检索
                  <ArrowUpRight size={13} aria-hidden="true" />
                </Link>
                <Link to="/offers" className="lg2-link">
                  录用 Offer
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
