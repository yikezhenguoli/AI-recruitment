import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Loader2, UserPlus } from 'lucide-react'
import { fetchMe, register } from '../api/auth'
import { getApiErrorMessage } from '../lib/apiError'
import { setStoredUser, setTokens } from '../lib/tokenStorage'
import { useAuthStore } from '../store/auth'
import { AuthShell } from '../components/AuthShell'

const DEFAULT_TENANT = (import.meta.env.VITE_TENANT_SLUG as string | undefined) || 'demo'

export default function RegisterPage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)

  const [tenantSlug, setTenantSlug] = useState(DEFAULT_TENANT)
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    setError(null)
    if (password.length < 12) {
      setError('密码至少需要 12 个字符，建议混合大小写字母、数字与符号。')
      return
    }
    if (password !== confirm) {
      setError('两次输入的密码不一致。')
      return
    }
    setLoading(true)
    try {
      const result = await register({
        tenant_slug: tenantSlug.trim(),
        email: email.trim(),
        password,
        display_name: displayName.trim(),
      })
      setTokens(result.access_token, result.refresh_token)
      const me = await fetchMe()
      const principal = { ...me, email: email.trim() }
      setStoredUser(principal)
      setUser(principal)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '注册失败，请稍后重试。'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell>
      <form onSubmit={handleSubmit} className="card p-7 sm:p-8">
        <div className="mb-6">
          <span className="chip">新候选人</span>
          <h2 className="mt-4 text-[24px] font-extrabold tracking-tight text-ink">创建求职档案</h2>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            注册后可浏览岗位、上传简历、查看匹配评估。所有数据仅保存在该企业租户内。
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="label">企业标识</span>
            <input
              className="input"
              value={tenantSlug}
              onChange={(event) => setTenantSlug(event.target.value)}
              required
              autoComplete="organization"
            />
          </label>
          <label className="block">
            <span className="label">你的称呼</span>
            <input
              className="input"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              required
              maxLength={80}
              placeholder="例如：林小满"
            />
          </label>
        </div>

        <label className="mb-4 mt-4 block">
          <span className="label">邮箱</span>
          <input
            className="input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="username"
            placeholder="you@example.com"
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="label">密码（至少 12 位）</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={12}
              autoComplete="new-password"
            />
          </label>
          <label className="block">
            <span className="label">确认密码</span>
            <input
              className="input"
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
        </div>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-[11px] leading-relaxed text-rose-700">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <button type="submit" className="btn-primary mt-5 w-full" disabled={loading}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
          {loading ? '正在创建…' : '创建账号并登录'}
        </button>

        <div className="mt-5 flex items-center justify-between text-xs">
          <Link to="/login" className="inline-flex items-center gap-1 font-semibold text-brand-deep hover:underline">
            <ArrowLeft size={13} />
            返回登录
          </Link>
          <span className="text-muted">注册即表示同意简历处理说明</span>
        </div>
      </form>
    </AuthShell>
  )
}
