import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Info, Sparkles } from 'lucide-react'
import { JobDescriptionForm } from '../components/JobDescriptionForm'
import type {
  GraduationYearFilterConfig,
  JDStructured,
  SavedJobProfile,
  ScoringSchema,
} from '../types'

export default function JobCreatePage() {
  const navigate = useNavigate()
  const [parsedRole, setParsedRole] = useState<string | null>(null)

  const handleParsed = (
    _jdText: string,
    structured: JDStructured,
    _schema: ScoringSchema,
  ) => {
    setParsedRole(structured.role_title)
  }

  const handleProceed = (
    _schema: ScoringSchema,
    _graduationFilter: GraduationYearFilterConfig,
  ) => {
    navigate('/jobs')
  }

  const handleSaved = (job: SavedJobProfile) => {
    navigate(`/jobs/${encodeURIComponent(job.name)}`, {
      state: { created: true },
    })
  }

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            JOB INTAKE
            <span className="hero-eyebrow-line" />
            <span>AI JD PARSING</span>
          </div>
          <h1>新建岗位</h1>
          <p>粘贴岗位描述，AI 将提取结构化岗位信息并生成评分维度。保存后可在岗位管理中复用。</p>
        </div>
        <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
          <ArrowLeft size={16} />
          返回岗位列表
        </Link>
      </section>

      <div className="ttc-notice">
        <Info size={16} />
        <span>
          本页调用 <code>/api/jobs/parse</code> 与 <code>/api/jobs/saved</code>。
          未配置 DeepSeek Key 时，解析会返回明确错误，不会生成假数据。
        </span>
      </div>

      {parsedRole && (
        <div className="ttc-parsed-badge">
          <Sparkles size={15} />
          已解析岗位：{parsedRole}
        </div>
      )}

      <JobDescriptionForm
        onParsed={handleParsed}
        onProceed={handleProceed}
        onSaved={handleSaved}
        proceedLabel="完成并查看岗位列表"
      />
    </div>
  )
}
