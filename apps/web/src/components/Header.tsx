import React from 'react'
import { Activity, ArrowUpRight, Check } from 'lucide-react'

interface HeaderProps {
  step: number
}

const STEPS = [
  { num: 1, label: '岗位描述', en: 'JOB BRIEF' },
  { num: 2, label: '简历上传', en: 'RESUME INTAKE' },
  { num: 3, label: '智能筛选', en: 'AI SCREENING' },
  { num: 4, label: '候选人结果', en: 'CANDIDATES' },
]

export const Header: React.FC<HeaderProps> = ({ step }) => (
  <header className="app-header">
    <div className="header-inner">
      <a className="brand-lockup" href="#top" aria-label="AI AFS home">
        <span className="brand-mark"><Activity size={21} strokeWidth={2.2} /></span>
        <span className="brand-copy">
          <strong>AI AFS<span className="brand-period">.</span></strong>
          <small>INTELLIGENT TALENT SCREENING</small>
        </span>
      </a>

      <nav className="workflow-nav" aria-label="Recruitment workflow">
        {STEPS.map((item, index) => {
          const active = step === item.num
          const done = step > item.num
          return (
            <React.Fragment key={item.num}>
              {index > 0 && <span className={`workflow-connector ${done ? 'is-done' : ''}`} />}
              <div className={`workflow-step ${active ? 'is-active' : ''} ${done ? 'is-done' : ''}`} aria-current={active ? 'step' : undefined}>
                <span className="workflow-number">{done ? <Check size={13} /> : `0${item.num}`}</span>
                <span className="workflow-labels">
                  <strong>{item.label}</strong>
                  <small>{item.en}</small>
                </span>
              </div>
            </React.Fragment>
          )
        })}
      </nav>

      <div className="header-status">
        <span className="status-dot" />
        <span>系统就绪</span>
        <ArrowUpRight size={14} />
      </div>
    </div>
  </header>
)
