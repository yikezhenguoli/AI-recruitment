import {
  AlertCircle,
  BadgeCheck,
  BrainCircuit,
  CheckCircle2,
  ListChecks,
} from 'lucide-react'
import type { CandidateCapabilityAssessment } from '../../types'

function scoreTone(score: number | null): string {
  if (score === null || score < 60) return 'is-danger'
  if (score < 80) return 'is-warning'
  return 'is-good'
}

export function CapabilityAssessmentPanel({
  assessment,
  compact = false,
}: {
  assessment?: CandidateCapabilityAssessment
  compact?: boolean
}) {
  if (!assessment) return null

  const coverage = Math.round(assessment.evidence_coverage.ratio * 100)
  return (
    <section className={`ttc-capability-card ${compact ? 'is-compact' : ''}`}>
      <div className="ttc-capability-head">
        <div>
          <div className="ttc-mini-heading">
            <BrainCircuit size={14} />
            <span>INTERVIEW CAPABILITY EVIDENCE</span>
          </div>
          <h3>面试能力证据评分</h3>
        </div>
        <span
          className={`ttc-badge ${
            assessment.status === 'unassessed' || assessment.review_required
              ? 'ttc-badge-amber'
              : 'ttc-badge-green'
          }`}
        >
          {assessment.status === 'unassessed'
            ? '证据不足'
            : assessment.review_required
              ? '建议复核'
              : '已评估'}
        </span>
      </div>

      <div className={`ttc-capability-score ${scoreTone(assessment.score)}`}>
        <div>
          <span>能力得分</span>
          <strong>{assessment.score === null ? '—' : assessment.score.toFixed(1)}</strong>
          <small>/ 100</small>
        </div>
        <div className="ttc-capability-score-copy">
          <p>{assessment.summary}</p>
          <span>
            已回答引用覆盖 {assessment.evidence_coverage.cited_turns} /{' '}
            {assessment.evidence_coverage.candidate_turns} 轮 · {coverage}%
          </span>
        </div>
      </div>

      {!compact && (
        <>
          <h4 className="ttc-report-subhead">能力维度</h4>
          <div className="ttc-capability-dimensions">
            {assessment.dimensions.map((dimension) => (
              <div key={dimension.key} className="ttc-capability-dimension">
                <div>
                  <strong>{dimension.label}</strong>
                  <span>权重 {dimension.weight_pct}%</span>
                  <b>{dimension.score === null ? '证据不足' : `${dimension.score.toFixed(1)} 分`}</b>
                </div>
                <div className="ttc-capability-track" aria-hidden="true">
                  <i style={{ width: `${dimension.score ?? 0}%` }} />
                </div>
                <p>{dimension.reason}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {(assessment.strengths.length > 0 || assessment.gaps.length > 0) && (
        <div className="ttc-capability-insights">
          {assessment.strengths.length > 0 && (
            <div>
              <h4>
                <BadgeCheck size={13} />
                已展示优势
              </h4>
              <ul className="ttc-plain-list">
                {assessment.strengths.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          )}
          {assessment.gaps.length > 0 && (
            <div>
              <h4>
                <AlertCircle size={13} />
                能力证据缺口
              </h4>
              <ul className="ttc-plain-list">
                {assessment.gaps.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {assessment.verification_questions.length > 0 && (
        <>
          <h4 className="ttc-report-subhead">建议下一轮核验</h4>
          <ul className="ttc-plain-list">
            {assessment.verification_questions.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      )}

      {!compact && assessment.evidence.length > 0 && (
        <details className="ttc-capability-evidence">
          <summary>
            <ListChecks size={14} />
            查看能力判断引用的 {assessment.evidence.length} 条原始回答
          </summary>
          <div>
            {assessment.evidence.map((item) => (
              <blockquote key={item.turn_id}>
                <span>候选人原话 · {item.turn_id.slice(0, 8)}</span>
                {item.text}
              </blockquote>
            ))}
          </div>
        </details>
      )}

      <div className="ttc-capability-boundary">
        <CheckCircle2 size={14} />
        <div>
          <strong>评分边界</strong>
          <span>
            只代表候选人在本次问答中展示出的岗位相关能力证据，不是通用智力、
            人格或长期绩效测评，也不能替代技能测试和专业人工面试。
          </span>
          {assessment.review_required && <span>证据覆盖不足，请结合完整回答人工复核。</span>}
        </div>
      </div>
    </section>
  )
}
