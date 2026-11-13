import React, { useEffect, useState } from 'react'
import { Briefcase, ChevronRight, Loader2, Plus, Trash2 } from 'lucide-react'
import { getSavedJob, listSavedJobs, parseJD, saveJobProfile } from '../api/jobs'
import { getApiErrorMessage } from '../lib/apiError'
import type {
  GraduationYearFilterConfig,
  JDStructured,
  SavedJobProfile,
  SavedJobSummary,
  ScoringDimension,
  ScoringSchema,
} from '../types'

interface Props {
  onParsed: (jdText: string, structured: JDStructured, schema: ScoringSchema) => void
  onProceed: (schema: ScoringSchema, graduationFilter: GraduationYearFilterConfig) => void
  onSaved?: (job: SavedJobProfile) => void
  proceedLabel?: string
}

function toSnakeCase(label: string, fallback: string): string {
  const ascii = label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  return ascii || fallback
}

const EMPTY_NEW_DIM = { label: '', description: '', max_points: '' }
const DEFAULT_GRADUATION_FILTER: GraduationYearFilterConfig = {
  enabled: false,
  accepted_years: [],
  unknown_year_behavior: 'manual_review',
  degree_selection: 'highest_relevant_degree',
}
const CURRENT_YEAR = new Date().getFullYear()
const SUGGESTED_YEARS = Array.from({ length: 6 }, (_, idx) => CURRENT_YEAR - 1 + idx)

export const JobDescriptionForm: React.FC<Props> = ({ onParsed, onProceed, onSaved, proceedLabel }) => {
  const [jdText, setJdText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<JDStructured | null>(null)
  const [savedJobs, setSavedJobs] = useState<SavedJobSummary[]>([])
  const [loadingSavedJobs, setLoadingSavedJobs] = useState(true)
  const [savedJobsError, setSavedJobsError] = useState<string | null>(null)
  const [selectedSavedJob, setSelectedSavedJob] = useState('')
  const [loadingSavedJob, setLoadingSavedJob] = useState(false)
  const [dims, setDims] = useState<ScoringDimension[]>([])
  const [showAddForm, setShowAddForm] = useState(false)
  const [newDim, setNewDim] = useState(EMPTY_NEW_DIM)
  const [addError, setAddError] = useState<string | null>(null)
  const [graduationFilter, setGraduationFilter] = useState<GraduationYearFilterConfig>(DEFAULT_GRADUATION_FILTER)
  const [yearInput, setYearInput] = useState('')
  const [yearError, setYearError] = useState<string | null>(null)
  const [saveName, setSaveName] = useState('')
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  const total = dims.reduce((s, d) => s + d.max_points, 0)
  const totalOk = total === 100
  const graduationFilterValid = !graduationFilter.enabled || graduationFilter.accepted_years.length > 0

  useEffect(() => {
    void refreshSavedJobs()
  }, [])

  const refreshSavedJobs = async () => {
    setLoadingSavedJobs(true)
    setSavedJobsError(null)
    try {
      setSavedJobs(await listSavedJobs())
    } catch (err: unknown) {
      setSavedJobsError(getApiErrorMessage(err, '加载已保存岗位失败'))
    } finally {
      setLoadingSavedJobs(false)
    }
  }

  const applyParsedJD = (text: string, structured: JDStructured, schema: ScoringSchema) => {
    setJdText(text)
    setPreview(structured)
    setDims(schema.dimensions)
    setShowAddForm(false)
    setNewDim(EMPTY_NEW_DIM)
    setAddError(null)
    setGraduationFilter(DEFAULT_GRADUATION_FILTER)
    setYearInput('')
    setYearError(null)
    setSaveError(null)
    setSaveSuccess(null)
    setSaveName(structured.role_title)
    onParsed(text, structured, schema)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!jdText.trim()) return
    setLoading(true)
    setError(null)
    setPreview(null)
    setDims([])
    setShowAddForm(false)
    setSelectedSavedJob('')
    setGraduationFilter(DEFAULT_GRADUATION_FILTER)
    setYearInput('')
    setYearError(null)
    setSaveError(null)
    setSaveSuccess(null)
    try {
      const res = await parseJD(jdText)
      applyParsedJD(jdText, res.structured, res.scoring_schema)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '岗位描述解析失败'))
    } finally {
      setLoading(false)
    }
  }

  const handleLoadSavedJob = async () => {
    if (!selectedSavedJob) return
    setLoadingSavedJob(true)
    setError(null)
    setSavedJobsError(null)
    try {
      const job = await getSavedJob(selectedSavedJob)
      applyParsedJD(job.jd_text, job.structured, job.scoring_schema)
      setSelectedSavedJob(job.name)
      setSaveName(job.name)
    } catch (err: unknown) {
      setSavedJobsError(getApiErrorMessage(err, '加载岗位失败'))
    } finally {
      setLoadingSavedJob(false)
    }
  }

  const updatePts = (idx: number, raw: string) => {
    const val = parseInt(raw, 10)
    setDims(prev => prev.map((d, i) => i === idx ? { ...d, max_points: isNaN(val) ? 0 : Math.max(0, Math.min(100, val)) } : d))
  }

  const updateLabel = (idx: number, label: string) => {
    setDims(prev => prev.map((d, i) => i === idx ? { ...d, label } : d))
  }

  const updateDescription = (idx: number, description: string) => {
    setDims(prev => prev.map((d, i) => i === idx ? { ...d, description } : d))
  }

  const removeDim = (idx: number) => {
    setDims(prev => prev.filter((_, i) => i !== idx))
  }

  const handleAddDim = () => {
    setAddError(null)
    if (!newDim.label.trim()) { setAddError('请填写维度名称。'); return }
    if (!newDim.description.trim()) { setAddError('请填写维度说明。'); return }
    const pts = parseInt(newDim.max_points as string, 10)
    if (isNaN(pts) || pts <= 0) { setAddError('分值必须是正数。'); return }
    const name = toSnakeCase(newDim.label, `custom_dimension_${dims.length + 1}`)
    if (dims.some(d => d.name === name)) { setAddError('该维度名称已存在。'); return }
    setDims(prev => [...prev, { name, label: newDim.label.trim(), description: newDim.description.trim(), max_points: pts }])
    setNewDim(EMPTY_NEW_DIM)
    setShowAddForm(false)
  }

  const handleProceed = () => {
    onProceed({ dimensions: dims }, graduationFilter)
  }

  const handleSaveJob = async () => {
    if (!preview || !jdText.trim() || !saveName.trim() || !totalOk) return
    setSaveLoading(true)
    setSaveError(null)
    setSaveSuccess(null)
    try {
      const job = await saveJobProfile({
        name: saveName,
        jd_text: jdText,
        structured: preview,
        scoring_schema: { dimensions: dims },
      })
      setSaveSuccess(`已保存岗位档案“${job.name}”。`)
      setSelectedSavedJob(job.name)
      await refreshSavedJobs()
      onSaved?.(job)
    } catch (err: unknown) {
      setSaveError(getApiErrorMessage(err, '保存岗位档案失败'))
    } finally {
      setSaveLoading(false)
    }
  }

  const addYear = (rawValue: string) => {
    const year = parseInt(rawValue.trim(), 10)
    if (isNaN(year) || year < 2000 || year > 2100) {
      setYearError('请输入有效的毕业年份。')
      return
    }
    setGraduationFilter(prev => ({
      ...prev,
      accepted_years: Array.from(new Set([...prev.accepted_years, year])).sort((a, b) => a - b),
    }))
    setYearInput('')
    setYearError(null)
  }

  const removeYear = (year: number) => {
    setGraduationFilter(prev => ({
      ...prev,
      accepted_years: prev.accepted_years.filter(item => item !== year),
    }))
  }

  const toggleGraduationFilter = (enabled: boolean) => {
    setGraduationFilter(prev => ({
      ...prev,
      enabled,
      accepted_years: enabled ? prev.accepted_years : [],
    }))
    setYearInput('')
    setYearError(null)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="hero-eyebrow"><span className="hero-eyebrow-dot" /> AI-ASSISTED JOB INTAKE <span className="hero-eyebrow-line" /> <span>01 / 03</span></div>
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-600 mb-4">
          <Briefcase className="w-7 h-7 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-gray-900">粘贴岗位描述</h1>
        <p className="text-gray-500 mt-2">
          AI 将解析岗位信息并生成可编辑的评分维度，保存后即可用于候选人筛选。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
                已保存岗位
              </label>
              <select
                value={selectedSavedJob}
                onChange={e => setSelectedSavedJob(e.target.value)}
                disabled={loadingSavedJobs || loadingSavedJob}
                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">选择已保存的岗位…</option>
                {savedJobs.map(job => (
                  <option key={job.name} value={job.name}>
                    {job.name} · {job.role_title}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={() => { void handleLoadSavedJob() }}
              disabled={!selectedSavedJob || loadingSavedJobs || loadingSavedJob}
              className="flex items-center justify-center gap-2 px-5 py-3 rounded-xl border border-gray-200 bg-white text-sm font-semibold text-gray-700 hover:border-brand-300 hover:text-brand-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loadingSavedJob ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> 加载中…</>
              ) : (
                <>加载岗位</>
              )}
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between gap-3 text-xs text-gray-500">
            <span>{loadingSavedJobs ? '正在加载已保存岗位…' : `共 ${savedJobs.length} 个已保存岗位`}</span>
            <button
              type="button"
              onClick={() => { void refreshSavedJobs() }}
              className="font-medium text-brand-600 hover:text-brand-700"
            >
              刷新
            </button>
          </div>
          {savedJobsError && (
            <p className="mt-2 text-xs text-red-600">{savedJobsError}</p>
          )}
        </div>

        <textarea
          value={jdText}
          onChange={e => setJdText(e.target.value)}
          placeholder="在此粘贴完整岗位描述…"
          rows={16}
          className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 placeholder-gray-400 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-y font-mono"
        />

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading || !jdText.trim()}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 text-white font-semibold text-sm hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> 正在解析岗位…</>
            ) : (
              <>解析岗位描述 <ChevronRight className="w-4 h-4" /></>
            )}
          </button>
        </div>
      </form>

      {preview && dims.length > 0 && (
        <div className="mt-8 space-y-4">
          <div className="rounded-xl border border-green-200 bg-green-50 p-5">
            <h3 className="font-semibold text-green-800 mb-3 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-green-500 text-white text-xs flex items-center justify-center">✓</span>
              岗位描述解析成功
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <span className="font-medium text-gray-700">岗位：</span>{' '}
                <span className="text-gray-900">{preview.role_title}</span>
              </div>
              {preview.seniority_level && (
                <div>
                  <span className="font-medium text-gray-700">资历：</span>{' '}
                  <span className="text-gray-900">{preview.seniority_level}</span>
                </div>
              )}
              {preview.min_years_experience !== undefined && preview.min_years_experience !== null && (
                <div>
                  <span className="font-medium text-gray-700">最低经验：</span>{' '}
                  <span className="text-gray-900">{preview.min_years_experience} 年</span>
                </div>
              )}
            </div>
            {preview.required_skills?.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">必备技能</p>
                <div className="flex flex-wrap gap-1.5">
                  {preview.required_skills.map(s => (
                    <span key={s} className="px-2 py-0.5 rounded-full bg-brand-100 text-brand-700 text-xs font-medium">{s}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-emerald-900">保存这个岗位档案</h3>
                <p className="text-xs text-emerald-700 mt-1">
                  保存 JD 与已确认的评分维度，后续可直接用于新的简历批次。
                </p>
              </div>
              {saveSuccess && <span className="text-xs font-medium text-emerald-700">{saveSuccess}</span>}
            </div>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                type="text"
                value={saveName}
                onChange={e => setSaveName(e.target.value)}
                placeholder="输入岗位档案名称"
                className="w-full rounded-xl border border-emerald-200 bg-white px-4 py-3 text-sm text-gray-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <button
                type="button"
                onClick={() => { void handleSaveJob() }}
                disabled={saveLoading || !saveName.trim() || !totalOk}
                className="flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saveLoading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> 保存中…</>
                ) : (
                  <>保存岗位档案</>
                )}
              </button>
            </div>
            {saveError && (
              <p className="mt-2 text-xs text-red-600">{saveError}</p>
            )}
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-amber-900">毕业年份筛选</h3>
                <p className="text-xs text-amber-700 mt-1">
                  可选。适用于实习或校招岗位，仅接受指定毕业年份的候选人。
                </p>
              </div>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-amber-900">
                <input
                  type="checkbox"
                  checked={graduationFilter.enabled}
                  onChange={e => toggleGraduationFilter(e.target.checked)}
                  className="rounded border-amber-300 text-brand-600 focus:ring-brand-500"
                />
                启用筛选
              </label>
            </div>

            {graduationFilter.enabled && (
              <div className="mt-4 space-y-4">
                <div>
                  <p className="text-xs font-semibold text-amber-800 uppercase tracking-wider mb-2">
                    接受的毕业年份
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED_YEARS.map(year => {
                      const active = graduationFilter.accepted_years.includes(year)
                      return (
                        <button
                          key={year}
                          type="button"
                          onClick={() => active ? removeYear(year) : addYear(String(year))}
                          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                            active
                              ? 'bg-brand-600 text-white'
                              : 'bg-white border border-amber-200 text-amber-800 hover:border-brand-300'
                          }`}
                        >
                          {year}
                        </button>
                      )
                    })}
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                  <input
                    type="number"
                    min={2000}
                    max={2100}
                    value={yearInput}
                    onChange={e => setYearInput(e.target.value)}
                    placeholder="添加其他年份"
                    className="w-full sm:w-44 text-sm border border-amber-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <button
                    type="button"
                    onClick={() => addYear(yearInput)}
                    className="px-3 py-2 rounded-lg bg-white border border-amber-200 text-sm text-amber-900 hover:border-brand-300 transition-colors"
                  >
                    添加年份
                  </button>
                  <p className="text-xs text-amber-700">
                    无法确定或置信度较低的毕业年份将进入人工复核。
                  </p>
                </div>

                {graduationFilter.accepted_years.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {graduationFilter.accepted_years.map(year => (
                      <button
                        key={year}
                        type="button"
                        onClick={() => removeYear(year)}
                        className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-white border border-amber-200 text-xs text-amber-900 hover:border-red-300"
                      >
                        {year}
                        <Trash2 className="w-3 h-3" />
                      </button>
                    ))}
                  </div>
                )}

                {yearError && <p className="text-xs text-red-600">{yearError}</p>}
                {!graduationFilterValid && (
                  <p className="text-xs text-red-600 font-medium">
                    至少添加一个接受的毕业年份才能启用此筛选。
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
            <div className="flex items-start justify-between mb-1">
              <h3 className="font-semibold text-blue-800">评分维度</h3>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                totalOk ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {total} / 100 分
              </span>
            </div>
            <p className="text-xs text-blue-600 mb-4">
可编辑维度名称、说明与分值；所有维度合计必须等于 100 分。
            </p>

            <div className="space-y-2">
              {dims.map((dim, idx) => (
                <div key={dim.name} className="rounded-lg bg-white border border-blue-100 px-4 py-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={dim.label}
                      onChange={e => updateLabel(idx, e.target.value)}
                      className="flex-1 min-w-0 text-sm font-medium text-gray-900 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-brand-500 focus:outline-none py-0.5"
                      placeholder="维度名称"
                    />
                    <div className="flex items-center gap-1 shrink-0">
                      <input
                        type="number"
                        min={1}
                        max={100}
                        value={dim.max_points}
                        onChange={e => updatePts(idx, e.target.value)}
                        className="w-14 text-center text-sm font-semibold rounded-lg border border-blue-200 bg-brand-50 text-brand-700 focus:outline-none focus:ring-1 focus:ring-brand-500 py-1"
                      />
                      <span className="text-xs text-gray-400">分</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeDim(idx)}
                      className="shrink-0 p-1 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="删除维度"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <input
                    type="text"
                    value={dim.description}
                    onChange={e => updateDescription(idx, e.target.value)}
                    className="w-full text-xs text-gray-500 bg-transparent border-b border-transparent hover:border-gray-200 focus:border-brand-400 focus:outline-none py-0.5"
                    placeholder="这个维度衡量什么？"
                  />
                </div>
              ))}
            </div>

            {!showAddForm ? (
              <button
                type="button"
                onClick={() => { setShowAddForm(true); setAddError(null) }}
                className="mt-3 flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 font-medium"
              >
                <Plus className="w-3.5 h-3.5" /> 添加维度
              </button>
            ) : (
              <div className="mt-3 rounded-lg bg-white border border-blue-200 px-4 py-3 space-y-2">
                <p className="text-xs font-semibold text-gray-600">新维度</p>
                <input
                  type="text"
                  value={newDim.label}
                  onChange={e => setNewDim(d => ({ ...d, label: e.target.value }))}
                  placeholder="维度名称（例如：沟通能力）"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <input
                  type="text"
                  value={newDim.description}
                  onChange={e => setNewDim(d => ({ ...d, description: e.target.value }))}
                  placeholder="维度说明（一句话）"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={newDim.max_points}
                    onChange={e => setNewDim(d => ({ ...d, max_points: e.target.value }))}
                    placeholder="分值"
                    className="w-24 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <span className="text-xs text-gray-400">分</span>
                </div>
                {addError && <p className="text-xs text-red-600">{addError}</p>}
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleAddDim}
                    className="px-3 py-1.5 rounded-lg bg-brand-600 text-white text-xs font-semibold hover:bg-brand-700 transition-colors"
                  >
                    添加
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowAddForm(false); setNewDim(EMPTY_NEW_DIM); setAddError(null) }}
                    className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs text-gray-600 hover:bg-gray-50 transition-colors"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}

            {!totalOk && (
              <p className="mt-3 text-xs text-red-600 font-medium">
                所有维度合计必须等于 100 分。当前合计：{total} 分。
              </p>
            )}
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleProceed}
              disabled={!totalOk || !graduationFilterValid || dims.length === 0}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 text-white font-semibold text-sm hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md"
            >
              {proceedLabel ?? '确认并继续'} <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
