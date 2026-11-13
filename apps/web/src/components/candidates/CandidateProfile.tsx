import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Award,
  BookOpen,
  Briefcase,
  CalendarDays,
  Download,
  FileText,
  GraduationCap,
  Mail,
  MapPin,
  Phone,
  Printer,
  ShieldCheck,
  User,
} from 'lucide-react'
import { getCandidateDetail } from '../../api/candidates'
import { getExportUrl } from '../../api/reports'
import { getResumePreviewUrl } from '../../api/resumes'
import { getSavedJob } from '../../api/jobs'
import { getApiErrorMessage } from '../../lib/apiError'
import { formatDateTime, formatPersonName } from '../../lib/format'
import { maskEmail, maskPhone, sanitizeAdditionalInfo } from '../../lib/privacy'
import { useSessionStore } from '../../store/sessionStore'
import type { Stage } from '../../types'

interface Props {
  candidateId: string
  mode: 'detail' | 'report'
}

const STAGE_LABEL: Record<Stage, string> = {
  queued: '排队中',
  parsing: '解析文件',
  extracting: '提取信息',
  screening: '条件筛选',
  evaluating: 'AI 评分',
  done: '已完成',
  error: '处理失败',
  skipped: '重复/跳过',
  filtered: '已过滤',
  review: '待人工复核',
}

function stageTone(stage: Stage): string {
  if (stage === 'done') return 'ttc-badge-green'
  if (stage === 'error') return 'ttc-badge-red'
  return 'ttc-badge-amber'
}

function scoreTone(score?: number): string {
  if (score == null) return 'ttc-score-muted'
  if (score >= 80) return 'ttc-score-good'
  if (score >= 40) return 'ttc-score-mid'
  return 'ttc-score-low'
}

function joinParts(parts: Array<string | null | undefined>, separator = ' · '): string {
  return parts.filter(Boolean).join(separator)
}

export function CandidateProfile({ candidateId, mode }: Props) {
  const session = useSessionStore((state) => state.session)
  const [showContact, setShowContact] = useState(false)

  const detailQuery = useQuery({
    queryKey: ['candidateDetail', session?.sessionId, candidateId],
    queryFn: () => getCandidateDetail(session!.sessionId, candidateId),
    enabled: Boolean(session?.sessionId && candidateId),
  })

  const jobQuery = useQuery({
    queryKey: ['savedJob', session?.jobName],
    queryFn: () => getSavedJob(session!.jobName!),
    enabled: Boolean(session?.jobName),
  })

  const schemaMap = useMemo(() => {
    const map = new Map<string, { label: string; maxPoints: number }>()
    jobQuery.data?.scoring_schema.dimensions.forEach((dimension) => {
      map.set(dimension.name, { label: dimension.label, maxPoints: dimension.max_points })
    })
    return map
  }, [jobQuery.data])

  if (!session) {
    return (
      <div className="ttc-page">
        <section className="ttc-card ttc-card-pad ttc-empty-large">
          <User size={30} />
          <h2>尚未选择候选人会话</h2>
          <p>候选人详情依赖当前批次的会话数据。请先在候选人页面上传简历并完成 AI 筛选。</p>
          <Link to="/candidates" className="ttc-btn ttc-btn-primary">
            前往候选人筛选
          </Link>
        </section>
      </div>
    )
  }

  if (detailQuery.isLoading) {
    return (
      <div className="ttc-page">
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
        <div className="ttc-card ttc-card-pad ttc-skeleton-block" />
      </div>
    )
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div className="ttc-page">
        <section className="ttc-page-head">
          <div>
            <h1>{mode === 'report' ? '评估报告' : '候选人详情'}</h1>
            <p>无法读取当前候选人。</p>
          </div>
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={16} />
            返回候选人列表
          </Link>
        </section>
        <div className="ttc-error-panel">
          <AlertTriangle size={18} />
          <div>
            <strong>候选人读取失败</strong>
            <span>{getApiErrorMessage(detailQuery.error, '会话可能已失效，请重新运行筛选。')}</span>
          </div>
        </div>
      </div>
    )
  }

  const candidate = detailQuery.data.candidate
  const resume = detailQuery.data.resume_structured
  const dimensions = candidate.dimension_scores ?? []
  const personal = resume.personal_info
  const resumeName = formatPersonName(personal.first_name, personal.last_name)
  const displayName = candidate.name || resumeName || candidate.file_name
  const parseMethodLabel =
    candidate.parse_method === 'primary'
      ? '文本解析'
      : candidate.parse_method === 'ocr'
        ? 'OCR 回退'
        : candidate.parse_method || '—'
  const roleTitle =
    jobQuery.data?.structured.role_title || session.jobRoleTitle || '未记录岗位名称'
  const totalMax =
    dimensions.reduce((sum, dimension) => sum + (schemaMap.get(dimension.name)?.maxPoints ?? 0), 0) ||
    100
  const isReport = mode === 'report'

  const safeAdditionalInfo = sanitizeAdditionalInfo(resume.additional_info || {})
  const hasEducation = resume.education.length > 0
  const hasWork = resume.work_experience.length > 0
  const hasProjects = resume.projects.length > 0
  const hasPublications = resume.publications.length > 0
  const hasCertifications = resume.certifications.length > 0
  const hasAdditionalInfo = Object.keys(safeAdditionalInfo).length > 0

  const dimensionInsights = dimensions.map((dimension) => {
    const max = schemaMap.get(dimension.name)?.maxPoints ?? 0
    return {
      ...dimension,
      label: schemaMap.get(dimension.name)?.label || dimension.name,
      max,
      ratio: max > 0 ? dimension.score / max : 0,
    }
  })
  const strengths = dimensionInsights
    .filter((dimension) => dimension.max > 0 && dimension.ratio >= 0.6)
    .sort((a, b) => b.ratio - a.ratio)
    .slice(0, 3)
  const risks = dimensionInsights
    .filter((dimension) => dimension.max > 0 && dimension.ratio < 0.4)
    .sort((a, b) => a.ratio - b.ratio)
    .slice(0, 3)

  return (
    <div className={`ttc-page ttc-profile-page ${isReport ? 'ttc-report-page' : ''}`}>
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            {isReport ? 'ASSESSMENT REPORT' : 'CANDIDATE PROFILE'}
            <span className="hero-eyebrow-line" />
            <span>{isReport ? '人工可复核' : 'EVIDENCE-FIRST'}</span>
          </div>
          <h1>{isReport ? `评估报告 · ${displayName}` : displayName}</h1>
          <p>
            {roleTitle} · {candidate.file_name}
          </p>
        </div>
        <div className="ttc-heading-actions">
          <Link to="/candidates" className="ttc-btn ttc-btn-secondary">
            <ArrowLeft size={16} />
            返回候选人列表
          </Link>
          {!isReport ? (
            <Link to={`/candidates/${candidate.candidate_id}/report`} className="ttc-btn ttc-btn-primary">
              查看评估报告
              <ArrowRight size={16} />
            </Link>
          ) : (
            <Link to={`/candidates/${candidate.candidate_id}`} className="ttc-btn ttc-btn-secondary">
              查看候选人详情
            </Link>
          )}
          {isReport && (
            <>
              <button type="button" className="ttc-btn ttc-btn-secondary" onClick={() => window.print()}>
                <Printer size={15} />
                打印
              </button>
              <a
                href={getExportUrl(session.sessionId)}
                className="ttc-btn ttc-btn-primary"
                download
              >
                <Download size={15} />
                导出本批次 Excel
              </a>
            </>
          )}
          {candidate.preview_available && (
            <a
              href={getResumePreviewUrl(session.sessionId, candidate.candidate_id)}
              target="_blank"
              rel="noreferrer"
              className="ttc-btn ttc-btn-secondary"
            >
              原文 PDF
            </a>
          )}
        </div>
      </section>

      {isReport && (
        <div className="ttc-report-header">
          <div>
            <strong>TTC · 才多对 AI 赋能与人才挖掘平台</strong>
            <span>候选人岗位适配评估报告</span>
          </div>
          <div>
            <span>生成时间：{formatDateTime(session.startedAt)}</span>
            <span>报告编号：{candidate.candidate_id.slice(0, 8).toUpperCase()}</span>
          </div>
        </div>
      )}

      <section className="ttc-profile-hero">
        <div className={`ttc-profile-score ${scoreTone(candidate.score)}`}>
          <span>岗位适配参考分</span>
          <strong>
            {candidate.score ?? '—'}
            <small>/ 100</small>
          </strong>
          <span className={`ttc-badge ${stageTone(candidate.stage)}`}>
            {STAGE_LABEL[candidate.stage]}
          </span>
        </div>
        <div className="ttc-profile-meta">
          <div>
            <span>候选人</span>
            <strong>{displayName}</strong>
          </div>
          <div>
            <span>当前岗位</span>
            <strong>{roleTitle}</strong>
          </div>
          <div>
            <span>评分维度</span>
            <strong>{dimensions.length} 个 · 合计 {totalMax} 分</strong>
          </div>
          <div>
            <span>解析方式</span>
            <strong>{parseMethodLabel}</strong>
          </div>
        </div>
      </section>

      {(candidate.error || candidate.screening_reason || candidate.stage !== 'done') && (
        <div className="ttc-warning-panel">
          <div className="ttc-warning-head">
            <AlertTriangle size={16} />
            <strong>需要人工关注</strong>
          </div>
          <ul>
            <li>
              <span>当前状态</span>
              <b>{STAGE_LABEL[candidate.stage]}</b>
            </li>
            {(candidate.error || candidate.screening_reason) && (
              <li>
                <span>系统说明</span>
                <b>{candidate.error || candidate.screening_reason}</b>
              </li>
            )}
          </ul>
        </div>
      )}

      <section className="ttc-detail-grid">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">逐维度评分</h2>
              <p className="ttc-card-sub">分数由后端按评分 Schema 计算，解释来自 AI 评估</p>
            </div>
            <ShieldCheck size={18} className="ttc-accent-icon" />
          </div>

          {dimensions.length > 0 ? (
            <div className="ttc-dimension-list">
              {dimensions.map((dimension) => {
                const meta = schemaMap.get(dimension.name)
                const maxPoints = meta?.maxPoints
                return (
                  <div key={dimension.name} className="ttc-dimension-row">
                    <div className="ttc-dimension-head">
                      <strong>{meta?.label || dimension.name}</strong>
                      <span>
                        {dimension.score}
                        {maxPoints ? ` / ${maxPoints}` : ''} 分
                      </span>
                    </div>
                    <p>{dimension.reason}</p>
                    <div className="ttc-progress-track">
                      <i
                        style={{
                          width: `${Math.min(100, maxPoints ? (dimension.score / maxPoints) * 100 : dimension.score)}%`,
                        }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="ttc-empty-note">
              <FileText size={18} />
              <span>
                当前结果未包含逐维度分数。该会话可能由旧版本产生，请重新运行筛选生成。
              </span>
            </div>
          )}
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">评分依据</h2>
              <p className="ttc-card-sub">AI 引用的主要匹配理由</p>
            </div>
            <BookOpen size={18} className="ttc-accent-icon" />
          </div>

          {candidate.explanation.length > 0 ? (
            <ul className="ttc-explanation-list">
              {candidate.explanation.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          ) : (
            <div className="ttc-empty-note">
              <FileText size={18} />
              <span>后端未返回评分依据。</span>
            </div>
          )}

          <div className="ttc-report-disclaimer">
            <ShieldCheck size={15} />
            <p>
              AI 结果仅作为招聘辅助参考，最终录用由 HR 结合原始材料人工复核。当前版本尚未接入
              M4 外部证据核验，因此不展示“证据可信度”结论，也不制造单一人才总分之外的能力判断。
            </p>
          </div>
        </article>
      </section>

      <section className="ttc-card ttc-card-pad">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">相对优势、风险与待核实</h2>
            <p className="ttc-card-sub">
              界面按维度得分占比分组（60% / 40%），仅用于阅读，不改变 AI 评分与排名
            </p>
          </div>
          <AlertTriangle size={18} className="ttc-accent-icon" />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-white/70 bg-white/45 p-4">
            <h3 className="mb-2 text-[10px] font-extrabold text-[#3c5875]">相对优势维度</h3>
            {strengths.length > 0 ? (
              <ul className="space-y-2">
                {strengths.map((dimension) => (
                  <li key={dimension.name} className="text-[9px] leading-relaxed text-[#52718f]">
                    <strong className="text-[#2f6fae]">
                      {dimension.label} · {dimension.score}/{dimension.max}
                    </strong>
                    <span className="mt-1 block">{dimension.reason}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[9px] leading-relaxed text-[#8ba2b9]">
                当前没有明显高于 60% 的评分维度；这不代表候选人没有能力，只代表现有材料对该岗位的证据不足。
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-white/70 bg-white/45 p-4">
            <h3 className="mb-2 text-[10px] font-extrabold text-[#3c5875]">相对风险 / 待核实</h3>
            {risks.length > 0 ? (
              <ul className="space-y-2">
                {risks.map((dimension) => (
                  <li key={dimension.name} className="text-[9px] leading-relaxed text-[#52718f]">
                    <strong className="text-[#a55353]">
                      {dimension.label} · {dimension.score}/{dimension.max}
                    </strong>
                    <span className="mt-1 block">{dimension.reason}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[9px] leading-relaxed text-[#8ba2b9]">
                当前没有低于 40% 的评分维度。仍建议结合原始简历和人工面试复核。
              </p>
            )}
            <p className="mt-3 border-t border-white/70 pt-2 text-[8px] leading-relaxed text-[#91a6bb]">
              以上为 AI 评分维度推导。M4 外部证据核验尚未接入，未找到公开证据不等于经历不存在。
            </p>
          </div>
        </div>
      </section>

      <section className="ttc-profile-sections">
        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">候选人信息</h2>
              <p className="ttc-card-sub">来自后端返回的结构化简历，不是前端硬编码</p>
              <span className="ttc-badge ttc-badge-amber mt-2 inline-flex">
                AI 提取 · 未人工确认
              </span>
            </div>
            <User size={18} className="ttc-accent-icon" />
          </div>

          <div className="ttc-contact-grid">
            <div>
              <span>姓名</span>
              <strong>{resumeName || displayName}</strong>
            </div>
            <div>
              <span>所在地</span>
              <strong>{personal.location || '—'}</strong>
            </div>
            <div>
              <span>邮箱</span>
              <strong>{showContact ? personal.email || '—' : maskEmail(personal.email)}</strong>
            </div>
            <div>
              <span>电话</span>
              <strong>{showContact ? personal.phone || '—' : maskPhone(personal.phone)}</strong>
            </div>
          </div>
          <button
            type="button"
            className="ttc-text-link ttc-contact-toggle"
            onClick={() => setShowContact((current) => !current)}
          >
            {showContact ? '隐藏完整联系方式' : '显示完整联系方式'}
          </button>

          <div className="ttc-skill-groups">
            <div>
              <h3>技能</h3>
              <div className="ttc-chip-list">
                {resume.skills.length > 0 ? (
                  resume.skills.map((skill) => (
                    <span key={skill} className="ttc-chip ttc-chip-blue">
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="ttc-muted">未提取到技能信息</span>
                )}
              </div>
            </div>
          </div>
        </article>

        <article className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">教育背景</h2>
              <p className="ttc-card-sub">按简历原文提取</p>
            </div>
            <GraduationCap size={18} className="ttc-accent-icon" />
          </div>
          {hasEducation ? (
            <div className="ttc-timeline">
              {resume.education.map((entry, index) => (
                <div key={`${entry.institution}-${index}`} className="ttc-timeline-item">
                  <span className="ttc-timeline-dot" />
                  <div>
                    <strong>{entry.institution || '未注明学校'}</strong>
                    <span>{joinParts([entry.degree, entry.field], ' · ') || '未注明学历'}</span>
                    <small>
                      {joinParts([entry.start_date, entry.end_date], ' – ') || '未注明时间'}
                      {entry.score_gpa ? ` · GPA ${entry.score_gpa}` : ''}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="ttc-empty-note">
              <GraduationCap size={18} />
              <span>后端未返回教育背景信息。</span>
            </div>
          )}
        </article>
      </section>

      <section className="ttc-card ttc-card-pad">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">工作与项目经历</h2>
            <p className="ttc-card-sub">来自简历结构化提取</p>
          </div>
          <Briefcase size={18} className="ttc-accent-icon" />
        </div>

        {hasWork ? (
          <div className="ttc-experience-list">
            {resume.work_experience.map((entry, index) => (
              <div key={`${entry.organization}-${index}`} className="ttc-experience-item">
                <div className="ttc-experience-head">
                  <strong>{joinParts([entry.role, entry.organization], ' @ ') || '未注明经历'}</strong>
                  <span>{joinParts([entry.start_date, entry.end_date], ' – ') || '未注明时间'}</span>
                </div>
                {entry.responsibilities.length > 0 && (
                  <ul>
                    {entry.responsibilities.map((item, itemIndex) => (
                      <li key={itemIndex}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="ttc-empty-note">
            <Briefcase size={18} />
            <span>后端未返回工作经历信息。</span>
          </div>
        )}

        {hasProjects && (
          <div className="ttc-project-list">
            <h3>项目经历</h3>
            {resume.projects.map((entry, index) => (
              <div key={`${entry.name}-${index}`} className="ttc-project-item">
                <div className="ttc-experience-head">
                  <strong>{entry.name || '未命名项目'}</strong>
                  {entry.technologies.length > 0 && (
                    <span>{entry.technologies.join(' · ')}</span>
                  )}
                </div>
                {entry.description && <p>{entry.description}</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      {(hasPublications || hasCertifications || hasAdditionalInfo) && (
        <section className="ttc-card ttc-card-pad">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">其他信息</h2>
              <p className="ttc-card-sub">论文、证书与后端额外提取字段</p>
            </div>
            <Award size={18} className="ttc-accent-icon" />
          </div>

          {hasPublications && (
            <div className="ttc-other-block">
              <h3>论文 / 出版物</h3>
              <ul className="ttc-plain-list">
                {resume.publications.map((entry, index) => (
                  <li key={`${entry.title}-${index}`}>
                    {joinParts([entry.title, entry.journal, entry.year], ' · ')}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasCertifications && (
            <div className="ttc-other-block">
              <h3>证书</h3>
              <ul className="ttc-plain-list">
                {resume.certifications.map((entry, index) => (
                  <li key={`${entry.name}-${index}`}>
                    {joinParts([entry.name, entry.issuer, entry.date], ' · ')}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasAdditionalInfo && (
            <div className="ttc-other-block">
              <h3>额外信息</h3>
              <pre className="ttc-jd-text">{JSON.stringify(safeAdditionalInfo, null, 2)}</pre>
              <p className="ttc-muted">
                敏感字段（电话、邮箱、学号、性别、政治面貌等）已按隐私策略隐藏或脱敏。
              </p>
            </div>
          )}
        </section>
      )}

      <section className="ttc-card ttc-card-pad ttc-profile-footer">
        <div>
          <CalendarDays size={16} />
          <span>会话开始：{formatDateTime(session.startedAt)}</span>
        </div>
        <div>
          <MapPin size={16} />
          <span>候选人编号：{candidate.candidate_id}</span>
        </div>
        <div>
          <Mail size={16} />
          <span>联系方式默认脱敏</span>
        </div>
        <div>
          <Phone size={16} />
          <span>AI 辅助 · 人工复核</span>
        </div>
      </section>
    </div>
  )
}
