import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Construction, Sparkles } from 'lucide-react'

interface PlaceholderPageProps {
  title: string
  description: string
  features: string[]
  phase?: string
}

export default function PlaceholderPage({
  title,
  description,
  features,
  phase = '下一阶段接入',
}: PlaceholderPageProps) {
  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            TTC WORKSPACE
            <span className="hero-eyebrow-line" />
            <span>MODULE PLANNED</span>
          </div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <Link to="/" className="ttc-btn ttc-btn-secondary">
          <ArrowLeft size={16} />
          返回工作台
        </Link>
      </section>

      <section className="ttc-card ttc-card-pad ttc-placeholder">
        <div className="ttc-placeholder-icon">
          <Construction size={28} />
        </div>
        <span className="ttc-badge ttc-badge-amber">{phase}</span>
        <h2>{title}尚未接入真实业务接口</h2>
        <p>
          当前版本只交付岗位创建、简历上传、评分排名与评估报告的主流程。
          本页面保留正式路由，但不会用演示数据冒充已经实现的功能。
        </p>

        <div className="ttc-placeholder-divider" />

        <div className="ttc-placeholder-features">
          <div className="ttc-mini-heading">
            <Sparkles size={14} />
            规划中的能力
          </div>
          <div className="ttc-feature-grid">
            {features.map((feature, index) => (
              <div key={feature} className="ttc-feature-item">
                <b>{String(index + 1).padStart(2, '0')}</b>
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="ttc-placeholder-actions">
          <Link to="/jobs/new" className="ttc-btn ttc-btn-primary">
            新建岗位
            <ArrowRight size={16} />
          </Link>
          <Link to="/jobs" className="ttc-btn ttc-btn-secondary">
            查看岗位管理
          </Link>
        </div>
      </section>
    </div>
  )
}
