import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Database, RefreshCw, Search, Sparkles, Users } from 'lucide-react'
import { reindexTalent, searchTalent, similarCandidates } from '../api/talent'
import { getApiErrorMessage } from '../lib/apiError'
import type { TalentHit, TalentSearchResult } from '../types'

export default function TalentPage() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<TalentSearchResult | null>(null)
  const [similar, setSimilar] = useState<{ name: string; items: TalentHit[] } | null>(null)
  const [reindexNote, setReindexNote] = useState('')
  const [error, setError] = useState('')

  const searchMutation = useMutation({
    mutationFn: () => searchTalent(query, 10),
    onSuccess: (data) => {
      setError('')
      setSimilar(null)
      setResult(data)
    },
    onError: (err) => setError(getApiErrorMessage(err, '检索失败。')),
  })

  const reindexMutation = useMutation({
    mutationFn: () => reindexTalent(),
    onSuccess: (data) => {
      setError('')
      setReindexNote(
        `扫描 ${data.scanned} 人，写入 ${data.indexed} 人` +
          (data.skipped.length ? `，跳过 ${data.skipped.length} 人` : '') +
          (data.warnings.length ? `；告警：${data.warnings.join('；')}` : ''),
      )
      void queryClient.invalidateQueries({ queryKey: ['talent'] })
    },
    onError: (err) => setError(getApiErrorMessage(err, '重建索引失败。')),
  })

  const similarMutation = useMutation({
    mutationFn: (hit: TalentHit) => similarCandidates(hit.candidate_id, 5),
    onSuccess: (data, hit) => {
      setError('')
      setSimilar({ name: hit.display_name, items: data.items })
    },
    onError: (err) => setError(getApiErrorMessage(err, '读取相似候选人失败。')),
  })

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            TALENT POOL
            <span className="hero-eyebrow-line" />
            <span>SEMANTIC SEARCH</span>
          </div>
          <h1>人才库</h1>
          <p>按语义检索简历内容，找出相近候选人；索引来自每位候选人最新的已完成简历版本。</p>
        </div>
        <div className="ttc-heading-actions">
          <button type="button" className="ttc-btn ttc-btn-secondary"
            disabled={reindexMutation.isPending}
            onClick={() => reindexMutation.mutate()}>
            <RefreshCw size={15} className={reindexMutation.isPending ? 'animate-spin' : ''} />
            {reindexMutation.isPending ? '重建中…' : '重建索引'}
          </button>
        </div>
      </section>

      {error && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>操作未完成</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {reindexNote && (
        <div className="ttc-card" style={{ padding: '12px 16px' }}>
          <span className="ttc-muted" style={{ fontSize: 11 }}>{reindexNote}</span>
        </div>
      )}

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">语义检索</h2>
            <p className="ttc-card-sub">例如「Python 后端 数据库 高并发」。</p>
          </div>
          <Search size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-inline-form">
          <label className="ttc-login-field" style={{ flexBasis: 320 }}>
            <span>检索条件</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)}
              placeholder="输入技能、经历或项目关键词" />
          </label>
          <button type="button" className="ttc-btn ttc-btn-primary"
            disabled={!query.trim() || searchMutation.isPending}
            onClick={() => searchMutation.mutate()}>
            <Sparkles size={15} />
            {searchMutation.isPending ? '检索中…' : '检索'}
          </button>
        </div>

        {result && (
          <div style={{ marginTop: 12 }}>
            <span className="ttc-muted" style={{ fontSize: 10 }}>
              后端 {result.backend} · 模型 {result.model} · 已索引 {result.indexed} 人
            </span>
            {result.warning && (
              <div className="ttc-error-panel" style={{ marginTop: 8 }}>
                <AlertCircle size={16} />
                <div>
                  <strong>降级提示</strong>
                  <span>{result.warning}</span>
                </div>
              </div>
            )}
            {result.hint && <p className="ttc-muted">{result.hint}</p>}
            {result.indexed === 0 && (
              <p className="ttc-muted">索引为空：先点右上角「重建索引」。</p>
            )}
            <div className="ttc-consent-list">
              {result.items.map((hit) => (
                <div key={hit.candidate_id} className="ttc-consent-row">
                  <div>
                    <strong>{hit.display_name}</strong>
                    <span className="ttc-muted">
                      相似度 {hit.score.toFixed(3)} · {hit.backend}
                      {hit.snippets && hit.snippets.length > 0 ? ` · ${hit.snippets[0]}` : ''}
                    </span>
                  </div>
                  <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                    disabled={similarMutation.isPending}
                    onClick={() => similarMutation.mutate(hit)}>
                    <Users size={14} /> 相似
                  </button>
                </div>
              ))}
              {result.indexed > 0 && result.items.length === 0 && (
                <p className="ttc-muted">没有匹配到候选人，换个说法试试。</p>
              )}
            </div>
          </div>
        )}
      </article>

      {similar && (
        <article className="ttc-card">
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">与「{similar.name}」相近的候选人</h2>
              <p className="ttc-card-sub">基于同一索引的余弦相似度。</p>
            </div>
            <Database size={18} className="ttc-accent-icon" />
          </div>
          <div className="ttc-consent-list">
            {similar.items.map((hit) => (
              <div key={hit.candidate_id} className="ttc-consent-row">
                <div>
                  <strong>{hit.display_name}</strong>
                  <span className="ttc-muted">相似度 {hit.score.toFixed(3)}</span>
                </div>
              </div>
            ))}
            {similar.items.length === 0 && <p className="ttc-muted">没有相近候选人。</p>}
          </div>
        </article>
      )}
    </div>
  )
}
