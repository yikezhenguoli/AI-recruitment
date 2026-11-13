import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  RefreshCw,
  Search,
} from 'lucide-react'
import { getExportUrl } from '../../api/reports'
import { getResumePreviewUrl } from '../../api/resumes'
import { maskEmail } from '../../lib/privacy'
import type {
  CandidateResult,
  ScoringSchema,
  SessionResultsResponse,
  Stage,
} from '../../types'

interface Props {
  sessionId: string
  results: SessionResultsResponse
  jobRoleTitle?: string
  scoringSchema?: ScoringSchema
  onNewBatch: () => void
}

type StageFilter = 'all' | 'done' | 'issues'
type SortKey = 'score' | 'name'
type SortDir = 'asc' | 'desc'

const STAGE_LABEL: Record<Stage, string> = {
  queued: '排队中',
  parsing: '解析文件',
  extracting: '提取信息',
  screening: '条件筛选',
  evaluating: 'AI 评分',
  done: '已排名',
  error: '处理失败',
  skipped: '重复/跳过',
  filtered: '已过滤',
  review: '待人工复核',
}

function statusTone(stage: Stage): string {
  if (stage === 'done') return 'ttc-badge-green'
  if (stage === 'error') return 'ttc-badge-red'
  if (stage === 'skipped') return 'ttc-badge-amber'
  return 'ttc-badge-amber'
}

function scoreTone(score?: number): string {
  if (score == null) return 'ttc-score-muted'
  if (score >= 80) return 'ttc-score-good'
  if (score >= 40) return 'ttc-score-mid'
  return 'ttc-score-low'
}

export function CandidateResults({
  sessionId,
  results,
  jobRoleTitle,
  scoringSchema,
  onNewBatch,
}: Props) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<StageFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const schemaMap = useMemo(() => {
    const map = new Map<string, { label: string; maxPoints: number }>()
    scoringSchema?.dimensions.forEach((dimension) => {
      map.set(dimension.name, { label: dimension.label, maxPoints: dimension.max_points })
    })
    return map
  }, [scoringSchema])

  const ranked = results.results.filter((candidate) => candidate.stage === 'done')
  const warnings = results.results.filter((candidate) => candidate.stage !== 'done')

  const visible = useMemo(() => {
    let list = [...results.results]
    if (filter === 'done') list = list.filter((candidate) => candidate.stage === 'done')
    if (filter === 'issues') list = list.filter((candidate) => candidate.stage !== 'done')

    const query = search.trim().toLowerCase()
    if (query) {
      list = list.filter((candidate) =>
        [candidate.name, candidate.file_name, candidate.email]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query)),
      )
    }

    list.sort((a, b) => {
      if (sortKey === 'score') {
        const sa = a.score ?? -1
        const sb = b.score ?? -1
        return sortDir === 'desc' ? sb - sa : sa - sb
      }
      const na = (a.name || a.file_name).toLowerCase()
      const nb = (b.name || b.file_name).toLowerCase()
      return sortDir === 'desc' ? nb.localeCompare(na) : na.localeCompare(nb)
    })
    return list
  }, [results.results, filter, search, sortKey, sortDir])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((current) => (current === 'desc' ? 'asc' : 'desc'))
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const SortIcon = ({ column }: { column: SortKey }) => {
    if (sortKey !== column) return null
    return sortDir === 'desc' ? <ChevronDown size={13} /> : <ChevronUp size={13} />
  }

  const renderDimensionLabel = (name: string) => schemaMap.get(name)?.label || name

  return (
    <section className="ttc-results-panel">
      <div className="ttc-results-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            CANDIDATE RANKING
            <span className="hero-eyebrow-line" />
            <span>03 / 03</span>
          </div>
          <h2>候选人排名</h2>
          <p>
            {jobRoleTitle ? `岗位：${jobRoleTitle} · ` : ''}
            共 {results.total} 份简历，排名与评分均来自真实 AI 处理结果。
          </p>
        </div>
        <div className="ttc-results-actions">
          {results.completed > 0 && (
            <a href={getExportUrl(sessionId)} className="ttc-btn ttc-btn-primary" download>
              <Download size={15} />
              导出 Excel
            </a>
          )}
          <button type="button" className="ttc-btn ttc-btn-secondary" onClick={onNewBatch}>
            <RefreshCw size={15} />
            开始新一轮
          </button>
        </div>
      </div>

      <div className="ttc-results-summary">
        <div>
          <span>已排名</span>
          <strong>{results.completed}</strong>
        </div>
        <div>
          <span>异常 / 待复核</span>
          <strong>{Math.max(results.results.length - results.completed, 0)}</strong>
        </div>
        <div>
          <span>总文件</span>
          <strong>{results.total}</strong>
        </div>
        <div>
          <span>后端状态</span>
          <strong>{results.status === 'done' ? '已完成' : '处理中'}</strong>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="ttc-warning-panel">
          <div className="ttc-warning-head">
            <AlertCircle size={16} />
            <strong>{warnings.length} 份简历需要关注</strong>
          </div>
          <ul>
            {warnings.map((candidate) => (
              <li key={candidate.candidate_id}>
                <span>{candidate.file_name}</span>
                <b>{candidate.error || candidate.screening_reason || STAGE_LABEL[candidate.stage]}</b>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ttc-result-toolbar">
        <label className="ttc-search-box">
          <Search size={15} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索姓名、文件名或邮箱…"
          />
        </label>
        <div className="ttc-filter-chips">
          <button
            type="button"
            className={filter === 'all' ? 'is-active' : ''}
            onClick={() => setFilter('all')}
          >
            全部（{results.results.length}）
          </button>
          <button
            type="button"
            className={filter === 'done' ? 'is-active' : ''}
            onClick={() => setFilter('done')}
          >
            已排名（{ranked.length}）
          </button>
          <button
            type="button"
            className={filter === 'issues' ? 'is-active' : ''}
            onClick={() => setFilter('issues')}
          >
            异常 / 待复核（{warnings.length}）
          </button>
        </div>
      </div>

      <div className="ttc-table-card">
        <div className="ttc-table-scroll">
          <table className="ttc-result-table">
            <thead>
              <tr>
                <th className="ttc-col-rank">#</th>
                <th>
                  <button type="button" className="ttc-table-sort" onClick={() => toggleSort('name')}>
                    候选人 <SortIcon column="name" />
                  </button>
                </th>
                <th className="ttc-col-score">
                  <button type="button" className="ttc-table-sort" onClick={() => toggleSort('score')}>
                    综合得分 <SortIcon column="score" />
                  </button>
                </th>
                <th>状态</th>
                <th className="ttc-col-dimensions">维度评分</th>
                <th className="ttc-col-action">操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((candidate, index) => {
                const expanded = expandedId === candidate.candidate_id
                const dimensions = candidate.dimension_scores || []
                return (
                  <Fragment key={candidate.candidate_id}>
                    <tr
                      className={`ttc-result-row ${expanded ? 'is-expanded' : ''}`}
                      onClick={() => setExpandedId(expanded ? null : candidate.candidate_id)}
                      aria-expanded={expanded}
                    >
                      <td className="ttc-col-rank">{index + 1}</td>
                      <td>
                        <div className="ttc-result-person">
                          <span className="ttc-avatar ttc-avatar-sm">
                            {(candidate.name || candidate.file_name).slice(0, 1)}
                          </span>
                          <div>
                            <strong>{candidate.name || '未识别姓名'}</strong>
                            <span>
                              <FileText size={11} />
                              {candidate.file_name}
                            </span>
                            {candidate.email && <small>{maskEmail(candidate.email)}</small>}
                          </div>
                        </div>
                      </td>
                      <td className="ttc-col-score">
                        <span className={`ttc-score-badge ${scoreTone(candidate.score)}`}>
                          {candidate.score ?? '—'}
                        </span>
                      </td>
                      <td>
                        <span className={`ttc-badge ${statusTone(candidate.stage)}`}>
                          {STAGE_LABEL[candidate.stage]}
                        </span>
                      </td>
                      <td className="ttc-col-dimensions">
                        {dimensions.length > 0 ? (
                          <span className="ttc-dimension-count">
                            {dimensions.length} 个维度
                            <span>
                              {dimensions
                                .slice(0, 2)
                                .map((dimension) => `${renderDimensionLabel(dimension.name)} ${dimension.score}`)
                                .join(' · ')}
                            </span>
                          </span>
                        ) : (
                          <span className="ttc-muted">—</span>
                        )}
                      </td>
                      <td className="ttc-col-action">
                        <Link
                          to={`/candidates/${candidate.candidate_id}`}
                          className="ttc-text-link"
                          onClick={(event) => event.stopPropagation()}
                        >
                          查看详情 <ArrowRight size={13} />
                        </Link>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="ttc-expanded-row">
                        <td colSpan={6}>
                          <div className="ttc-expanded-grid">
                            <div>
                              <h4>逐维度评分</h4>
                              {dimensions.length > 0 ? (
                                <div className="ttc-dimension-mini-list">
                                  {dimensions.map((dimension) => {
                                    const meta = schemaMap.get(dimension.name)
                                    return (
                                      <div key={dimension.name} className="ttc-dimension-mini">
                                        <div>
                                          <strong>{meta?.label || dimension.name}</strong>
                                          <span>
                                            {dimension.score} / {meta?.maxPoints ?? '—'} 分
                                          </span>
                                        </div>
                                        <p>{dimension.reason}</p>
                                        <div className="ttc-progress-track">
                                          <i
                                            style={{
                                              width: `${Math.min(
                                                100,
                                                meta?.maxPoints
                                                  ? (dimension.score / meta.maxPoints) * 100
                                                  : dimension.score,
                                              )}%`,
                                            }}
                                          />
                                        </div>
                                      </div>
                                    )
                                  })}
                                </div>
                              ) : (
                                <p className="ttc-muted">
                                  当前结果未包含逐维度分数（可能来自旧会话）。请重新运行筛选生成。
                                </p>
                              )}
                            </div>
                            <div>
                              <h4>评分依据</h4>
                              {candidate.explanation.length > 0 ? (
                                <ul className="ttc-explanation-list">
                                  {candidate.explanation.map((item, itemIndex) => (
                                    <li key={itemIndex}>{item}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="ttc-muted">后端未返回评分依据。</p>
                              )}
                              {(candidate.error || candidate.screening_reason) && (
                                <div className="ttc-expanded-issue">
                                  <AlertCircle size={14} />
                                  <span>{candidate.error || candidate.screening_reason}</span>
                                </div>
                              )}
                              <div className="ttc-expanded-actions">
                                <Link
                                  to={`/candidates/${candidate.candidate_id}`}
                                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                                >
                                  候选人详情
                                </Link>
                                <Link
                                  to={`/candidates/${candidate.candidate_id}/report`}
                                  className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                                >
                                  评估报告
                                </Link>
                                {candidate.preview_available && (
                                  <a
                                    href={getResumePreviewUrl(sessionId, candidate.candidate_id)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                                  >
                                    原文 PDF
                                  </a>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
        {visible.length === 0 && (
          <div className="ttc-empty-state ttc-empty-compact">
            <Search size={20} />
            <strong>没有匹配的候选人</strong>
            <span>调整搜索关键词或筛选条件后重试。</span>
          </div>
        )}
      </div>

      {results.completed > 0 && (
        <div className="ttc-results-foot">
          <span>
            <CheckCircle2 size={14} />
            评分来自 DeepSeek 真实调用；最终录用应由 HR 人工复核。
          </span>
        </div>
      )}
    </section>
  )
}
