import { useCallback, useEffect, useState } from 'react'
import {
  BadgeCheck,
  CheckCircle2,
  ClipboardList,
  Loader2,
  Lock,
  Mail,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
} from 'lucide-react'
import {
  createPrivacyRequest,
  getProfile,
  grantConsent,
  revokeConsent,
  saveProfile,
} from '../api/portal'
import type { Consent, ConsentPurpose, PrivacyRequest, ProfileResponse } from '../api/types'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import {
  CONSENT_DESCRIPTION,
  CONSENT_LABEL,
  PRIVACY_STATUS,
  PRIVACY_TYPE,
} from '../lib/labels'
import { Badge, ErrorNote, LoadingBlock, PageHeader } from '../components/ui'

const PURPOSES: ConsentPurpose[] = [
  'resume_process',
  'voice_interview',
  'recording',
  'model_training',
]

const PRIVACY_TYPES: Array<PrivacyRequest['request_type']> = [
  'access',
  'correct',
  'revoke',
  'delete',
]

function latestByPurpose(consents: Consent[]): Partial<Record<ConsentPurpose, Consent>> {
  const result: Partial<Record<ConsentPurpose, Consent>> = {}
  for (const consent of consents) {
    if (!result[consent.purpose]) result[consent.purpose] = consent
  }
  return result
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [nameNotice, setNameNotice] = useState<string | null>(null)
  const [busyPurpose, setBusyPurpose] = useState<ConsentPurpose | null>(null)
  const [consentError, setConsentError] = useState<string | null>(null)
  const [requestType, setRequestType] = useState<PrivacyRequest['request_type']>('access')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [privacyNotice, setPrivacyNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await getProfile()
      setProfile(data)
      setDisplayName(data.candidate?.display_name ?? data.account.display_name)
      setError(null)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '个人信息加载失败。'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleSaveName = async () => {
    const trimmed = displayName.trim()
    if (!trimmed) {
      setNameNotice('姓名不能为空。')
      return
    }
    setSavingName(true)
    setNameNotice(null)
    try {
      await saveProfile(trimmed)
      await load()
      setNameNotice('已保存。')
    } catch (err: unknown) {
      setNameNotice(getApiErrorMessage(err, '保存失败。'))
    } finally {
      setSavingName(false)
    }
  }

  const handleToggleConsent = async (purpose: ConsentPurpose, current: Consent | undefined) => {
    if (!profile?.candidate) return
    setBusyPurpose(purpose)
    setConsentError(null)
    try {
      if (current && current.status === 'granted') {
        await revokeConsent(current.id)
      } else {
        await grantConsent(profile.candidate.id, purpose)
      }
      await load()
    } catch (err: unknown) {
      setConsentError(getApiErrorMessage(err, '授权操作失败。'))
    } finally {
      setBusyPurpose(null)
    }
  }

  const handlePrivacySubmit = async () => {
    if (!profile?.candidate) return
    setSubmitting(true)
    setPrivacyNotice(null)
    try {
      const result = await createPrivacyRequest(profile.candidate.id, requestType, reason)
      setPrivacyNotice(`请求已提交（${result.status}），承诺 ${result.sla_hours} 小时内处理。`)
      setReason('')
      await load()
    } catch (err: unknown) {
      setPrivacyNotice(getApiErrorMessage(err, '请求提交失败。'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <LoadingBlock text="正在加载个人信息…" />
  if (error || !profile) {
    return <ErrorNote message={error ?? '个人信息不存在。'} />
  }

  const latest = latestByPurpose(profile.consents)
  const hasProfile = Boolean(profile.candidate)
  const currentConsentVersion = profile.consents[0]?.id

  return (
    <div>
      <PageHeader
        eyebrow="Profile & Privacy"
        title="我的"
        description="管理你的求职档案、授权范围与数据权利请求。授权可以随时撤回，撤回后不再发起新的处理。"
        actions={
          <button type="button" className="btn-quiet" onClick={() => void load()}>
            <RefreshCw size={14} />
            刷新
          </button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="space-y-5">
          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft text-brand-deep">
                <UserRound size={16} />
              </span>
              <h2 className="section-title">求职档案</h2>
              {hasProfile ? (
                <Badge tone="ok" dot>已建立</Badge>
              ) : (
                <Badge tone="warn" dot>未建立</Badge>
              )}
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="display-name">档案姓名</label>
                <input
                  id="display-name"
                  className="input"
                  value={displayName}
                  maxLength={80}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="用于简历与面试沟通"
                />
              </div>
              <div>
                <span className="label">默认联系方式</span>
                <div className="input flex items-center justify-between bg-slate-50 text-muted">
                  <span>{profile.candidate?.contact_masked ?? '未填写'}</span>
                  <Lock size={13} />
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="btn-primary"
                disabled={savingName}
                onClick={() => void handleSaveName()}
              >
                {savingName ? <Loader2 size={14} className="animate-spin" /> : <BadgeCheck size={14} />}
                {savingName ? '保存中…' : hasProfile ? '保存档案姓名' : '建立求职档案'}
              </button>
              {nameNotice && <span className="text-[11px] text-muted">{nameNotice}</span>}
            </div>
            {!hasProfile && (
              <p className="mt-3 text-[10.5px] leading-relaxed text-muted">
                你也可以直接去岗位详情投递，上传简历时会自动建立求职档案。
              </p>
            )}
          </section>

          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-jade-soft text-jade-deep">
                <ShieldCheck size={16} />
              </span>
              <h2 className="section-title">授权管理</h2>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              每一项授权单独生效。撤回不会删除已经产生的评估记录，但会阻止后续处理。
            </p>

            {consentError && <div className="mt-3"><ErrorNote message={consentError} /></div>}

            <ul className="mt-4 divide-y divide-line/70">
              {PURPOSES.map((purpose) => {
                const consent = latest[purpose]
                const granted = consent?.status === 'granted'
                const busy = busyPurpose === purpose
                return (
                  <li key={purpose} className="py-3.5 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-xs font-bold text-ink">{CONSENT_LABEL[purpose]}</p>
                          {granted ? (
                            <Badge tone="ok" dot>已授权</Badge>
                          ) : consent ? (
                            <Badge tone="muted" dot>已撤回</Badge>
                          ) : (
                            <Badge tone="muted" dot>未授权</Badge>
                          )}
                        </div>
                        <p className="mt-1 text-[10.5px] leading-relaxed text-muted">
                          {CONSENT_DESCRIPTION[purpose]}
                        </p>
                        {consent?.accepted_at && (
                          <p className="mt-1 text-[10px] text-muted/80">
                            最近授权于 {formatDateTime(consent.accepted_at)}
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        className={granted ? 'btn-ghost shrink-0' : 'btn-jade shrink-0'}
                        disabled={busy || !hasProfile}
                        onClick={() => void handleToggleConsent(purpose, consent)}
                      >
                        {busy && <Loader2 size={13} className="animate-spin" />}
                        {granted ? '撤回授权' : '授予授权'}
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>

            <div className="mt-4 rounded-xl bg-white/60 p-3 text-[10.5px] leading-relaxed text-muted">
              当前授权文本版本：portal-v1
              {currentConsentVersion ? ` · 最近一条授权记录 ${formatDateTime(profile.consents[0].accepted_at)}` : ''}
            </div>
          </section>
        </div>

        <div className="space-y-5">
          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft text-brand-deep">
                <Mail size={16} />
              </span>
              <h2 className="section-title">账号</h2>
            </div>
            <dl className="mt-4 space-y-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">登录邮箱</dt>
                <dd className="truncate font-semibold text-ink">{profile.account.email}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">登录姓名</dt>
                <dd className="font-semibold text-ink">{profile.account.display_name}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">所属企业</dt>
                <dd className="text-right font-semibold text-ink">{profile.account.tenant_name}</dd>
              </div>
              {profile.candidate && (
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-muted">档案来源</dt>
                  <dd>
                    <Badge tone={profile.candidate.is_synthetic ? 'muted' : 'brand'}>
                      {profile.candidate.is_synthetic ? '招聘方导入' : '本人创建'}
                    </Badge>
                  </dd>
                </div>
              )}
            </dl>
            <p className="mt-4 flex items-start gap-1.5 text-[10px] leading-relaxed text-muted">
              <Lock size={11} className="mt-0.5 shrink-0" />
              登录密码由平台保存为不可逆哈希，客服也无法查看明文。
            </p>
          </section>

          <section className="card p-6">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
                <ClipboardList size={16} />
              </span>
              <h2 className="section-title">数据权利请求</h2>
            </div>
            <p className="mt-1 text-[10.5px] leading-relaxed text-muted">
              依据个人信息保护要求，你可以申请查阅、更正、撤回或删除你的数据。请求会转给企业招聘方处理。
            </p>

            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {PRIVACY_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setRequestType(type)}
                  className={`rounded-xl border px-3 py-2 text-left text-[11px] font-semibold transition ${
                    requestType === type
                      ? 'border-brand/40 bg-brand-soft text-brand-deep'
                      : 'border-line bg-white/70 text-muted hover:border-brand/25'
                  }`}
                >
                  {PRIVACY_TYPE[type]}
                </button>
              ))}
            </div>

            <label className="label mt-3" htmlFor="privacy-reason">补充说明（可选）</label>
            <textarea
              id="privacy-reason"
              className="input min-h-[76px] resize-y"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
              placeholder="例如：希望确认系统保留了哪些简历字段。"
            />

            <button
              type="button"
              className="btn-primary mt-3 w-full"
              disabled={submitting || !hasProfile}
              onClick={() => void handlePrivacySubmit()}
            >
              {submitting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {submitting ? '提交中…' : '提交请求'}
            </button>
            {!hasProfile && (
              <p className="mt-2 text-[10px] text-amber-700">建立求职档案后才能提交数据权利请求。</p>
            )}
            {privacyNotice && <p className="mt-2 text-[11px] text-muted">{privacyNotice}</p>}
          </section>

          <section className="card p-6">
            <h2 className="section-title">请求记录</h2>
            {profile.privacy_requests.length === 0 ? (
              <p className="mt-2 text-xs text-muted">还没有提交过数据权利请求。</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {profile.privacy_requests.map((request) => {
                  const meta = PRIVACY_STATUS[request.status]
                  return (
                    <li
                      key={request.id}
                      className="rounded-xl border border-line bg-white/70 px-3 py-2.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink">
                          {request.request_type === 'delete' ? (
                            <Trash2 size={12} />
                          ) : (
                            <ClipboardList size={12} />
                          )}
                          {PRIVACY_TYPE[request.request_type] ?? request.request_type}
                        </span>
                        {meta ? <Badge tone={meta.tone}>{meta.label}</Badge> : null}
                      </div>
                      <p className="mt-1 text-[10px] text-muted">
                        提交于 {formatDateTime(request.created_at)}
                        {request.completed_at ? ` · 完成于 ${formatDateTime(request.completed_at)}` : ''}
                      </p>
                      {request.payload?.reason && (
                        <p className="mt-1 text-[10.5px] leading-relaxed text-muted">
                          「{request.payload.reason}」
                        </p>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section className="card p-6">
            <div className="flex items-start gap-2">
              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-jade-deep" />
              <p className="text-[10.5px] leading-relaxed text-muted">
                删除请求会移除简历文本与匹配评估，已发出的面试纪要会同步失效。企业侧处理完成后，
                本页的状态会更新为「已完成」。
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
