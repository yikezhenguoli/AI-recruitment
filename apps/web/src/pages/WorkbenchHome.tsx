import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  Briefcase,
  Mic,
  Sparkles,
  Users,
  Waves,
} from 'lucide-react'
import { listCandidates } from '../api/candidates'
import { listJobs } from '../api/jobs'
import { listVoiceSessions } from '../api/voice'
import { useAuthStore } from '../store/authStore'
import { formatDateTime } from '../lib/format'

const STATUS_LABEL: Record<string, string> = {
  created: '待接通',
  live: '进行中',
  ended: '已结束',
  failed: '失败',
  revoked: '授权撤回',
  connecting: '连接中',
}

export default function WorkbenchHome() {
  const user = useAuthStore((state) => state.user)

  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs({ limit: 100 }) })
  const candidatesQuery = useQuery({ queryKey: ['candidates'], queryFn: () => listCandidates() })
  const sessionsQuery = useQuery({
    queryKey: ['voiceSessions', 'home'],
    queryFn: () => listVoiceSessions({ limit: 6 }),
  })

  const jobs = jobsQuery.data ?? []
  const candidates = candidatesQuery.data ?? []
  const sessions = sessionsQuery.data ?? []
  const published = jobs.filter((job) => job.status === 'published').length
  const live = sessions.filter((session) => session.status === 'live').length

  return (
    <div className="ttc-page">
      <section className="ttc-hero-card">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            AI RECRUITING WORKBENCH
            <span className="hero-eyebrow-line" />
            <span>TTC</span>
          </div>
          <h1>你好，{user?.display_name ?? '招聘同事'}</h1>
          <p>
            岗位 → 简历解析 → 证据核验 → 语音面试 → 评估报告。每一步都由后端真实接口驱动，页面不填充模拟数据。
          </p>
          <div className="ttc-hero-actions">
            <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
              <Briefcase size={16} />
              新建岗位
            </Link>
            <Link to="/candidates" className="ttc-btn ttc-btn-secondary">
              <Users size={16} />
              管理候选人
            </Link>
            <Link to="/sessions" className="ttc-btn ttc-btn-secondary">
              <Mic size={16} />
              语音面试
            </Link>
          </div>
        </div>
        <div className="ttc-hero-orbit">
          <span className="ttc-hero-orbit-icon">
            <Sparkles size={26} />
          </span>
        </div>
      </section>

      <div className="ttc-kpi-grid">
        <Link to="/jobs" className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-blue">
              <Briefcase size={16} />
            </span>
            <span>岗位</span>
          </div>
          <strong className="ttc-kpi-value">{jobsQuery.isLoading ? '—' : jobs.length}</strong>
          <span className="ttc-kpi-hint">其中已发布 {published}</span>
        </Link>
        <Link to="/candidates" className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-green">
              <Users size={16} />
            </span>
            <span>候选人</span>
          </div>
          <strong className="ttc-kpi-value">
            {candidatesQuery.isLoading ? '—' : candidates.length}
          </strong>
          <span className="ttc-kpi-hint">
            合成 {candidates.filter((item) => item.is_synthetic).length} · 真实{' '}
            {candidates.filter((item) => !item.is_synthetic).length}
          </span>
        </Link>
        <Link to="/sessions" className="ttc-card ttc-kpi-card">
          <div className="ttc-kpi-top">
            <span className="ttc-kpi-icon ttc-kpi-icon-violet">
              <Waves size={16} />
            </span>
            <span>语音会话</span>
          </div>
          <strong className="ttc-kpi-value">
            {sessionsQuery.isLoading ? '—' : sessions.length}
          </strong>
          <span className="ttc-kpi-hint">进行中 {live}</span>
        </Link>
      </div>

      <div className="ttc-detail-grid">
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">最近的语音会话</h2>
              <p className="ttc-card-sub">实时转写与 AI 面试官均通过通义千问实时语音完成。</p>
            </div>
            <Link to="/sessions" className="ttc-text-link">
              全部 <ArrowRight size={14} />
            </Link>
          </div>
          <div className="ttc-session-mini-list">
            {sessions.map((session) => (
              <Link key={session.id} to={`/sessions/${session.id}`} className="ttc-session-mini">
                <span className={`ttc-badge ${session.status === 'live' ? 'ttc-badge-green' : 'ttc-badge-blue'}`}>
                  {STATUS_LABEL[session.status] ?? session.status}
                </span>
                <strong>{session.candidate_name}</strong>
                <span className="ttc-muted">{session.job_title ?? '未绑定岗位'}</span>
                <span className="ttc-muted">{formatDateTime(session.created_at)}</span>
              </Link>
            ))}
            {!sessionsQuery.isLoading && sessions.length === 0 && (
              <p className="ttc-muted">还没有语音会话，从候选人详情页发起第一位面试。</p>
            )}
          </div>
        </article>

        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">闭环说明</h2>
              <p className="ttc-card-sub">每一步的产物都是下一步的输入。</p>
            </div>
          </div>
          <ol className="ttc-flow-list">
            <li>
              <strong>岗位与 JD</strong>
              <span>粘贴或生成 JD，选定版本后发布，权重合计必须 100%。</span>
            </li>
            <li>
              <strong>简历解析</strong>
              <span>上传后进入任务队列，WebSocket 推送解析进度，抽取出可核验声明。</span>
            </li>
            <li>
              <strong>证据核验</strong>
              <span>Crossref DOI 精确检索，A/B 级证据才计入评估分。</span>
            </li>
            <li>
              <strong>语音面试</strong>
              <span>需候选人授权；AI 面试官按问题清单提问，回答实时转写。</span>
            </li>
            <li>
              <strong>评估报告</strong>
              <span>确定性规则出分，人工复核只改说明不改分数，可导出 JSON。</span>
            </li>
          </ol>
        </article>
      </div>
    </div>
  )
}
