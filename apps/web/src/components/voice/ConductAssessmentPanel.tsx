import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { CandidateConductAssessment } from '../../types'

function scoreTone(score: number | null, veto: boolean): string {
  if (veto || (score !== null && score < 60)) return 'ttc-conduct-tone-danger'
  if (score !== null && score < 80) return 'ttc-conduct-tone-warning'
  return 'ttc-conduct-tone-good'
}

export function ConductAssessmentPanel({
  assessment,
  compact = false,
}: {
  assessment?: CandidateConductAssessment
  compact?: boolean
}) {
  if (!assessment) return null

  const tone = scoreTone(assessment.score, assessment.veto)
  const badgeClass = assessment.veto
    ? 'ttc-badge ttc-badge-red'
    : assessment.status === 'unassessed'
      ? 'ttc-badge ttc-badge-amber'
      : 'ttc-badge ttc-badge-green'

  return (
    <section className={`ttc-conduct-card ${compact ? 'is-compact' : ''}`}>
      <div className="ttc-conduct-head">
        <div>
          <div className="ttc-mini-heading">
            {assessment.veto ? <ShieldAlert size={14} /> : <ShieldCheck size={14} />}
            <span>INTERVIEW CONDUCT</span>
          </div>
          <h3>面试言行审核</h3>
        </div>
        <span className={badgeClass}>
          {assessment.veto
            ? '一票否决'
            : assessment.status === 'unassessed'
              ? '待人工复核'
              : assessment.review_required
                ? '建议复核'
                : '已审核'}
        </span>
      </div>

      <div className={`ttc-conduct-score ${tone}`}>
        <div>
          <span>言行得分</span>
          <strong>{assessment.score === null ? '—' : assessment.score.toFixed(1)}</strong>
          <small>/ 100</small>
        </div>
        <p>{assessment.summary}</p>
      </div>

      {assessment.veto && (
        <div className="ttc-conduct-veto" role="alert">
          <AlertTriangle size={17} />
          <div>
            <strong>严重言行触发自动否决</strong>
            {assessment.veto_reasons.map((reason) => (
              <span key={reason}>{reason}</span>
            ))}
          </div>
        </div>
      )}

      {assessment.incidents.length > 0 && (
        <>
          <h4 className="ttc-report-subhead">行为记录与原始证据</h4>
          <div className="ttc-conduct-incidents">
            {assessment.incidents.map((incident, index) => (
              <article
                key={`${incident.category}-${incident.evidence_turn_ids.join('-')}-${index}`}
                className={`ttc-conduct-incident is-${incident.severity}`}
              >
                <div>
                  <span className="ttc-badge ttc-badge-red">
                    {incident.severity === 'severe' ? '严重' : incident.severity === 'moderate' ? '中等' : '轻微'}
                  </span>
                  <strong>{incident.category_label}</strong>
                </div>
                <p>{incident.description}</p>
                {incident.quotes.map((quote) => (
                  <blockquote key={quote.turn_id}>
                    <span>候选人原话 · {quote.turn_id.slice(0, 8)}</span>
                    {quote.text}
                  </blockquote>
                ))}
              </article>
            ))}
          </div>
        </>
      )}

      {!compact && (
        <>
          <h4 className="ttc-report-subhead">评分维度</h4>
          <div className="ttc-conduct-dimensions">
            {assessment.dimensions.map((dimension) => (
              <div key={dimension.key} className="ttc-conduct-dimension">
                <div>
                  <strong>{dimension.label}</strong>
                  <span>
                    权重 {dimension.weight_pct}% ·{' '}
                    {dimension.score === null ? '依据不足' : `${dimension.score.toFixed(1)} 分`}
                  </span>
                </div>
                <p>{dimension.reason}</p>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="ttc-conduct-boundary">
        <CheckCircle2 size={14} />
        <div>
          <strong>审核边界</strong>
          <span>
            仅依据双方文字转写审核可观察到的言行，不评价外貌、声线、口音、情绪或敏感属性。
          </span>
          {assessment.review_required && (
            <span>自动结果应结合完整转写和原始证据人工复核。</span>
          )}
        </div>
      </div>
    </section>
  )
}
