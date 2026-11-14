import { FormEvent, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Activity, AlertCircle, Loader2, LockKeyhole, LogIn } from 'lucide-react'
import { login, me } from '../api/auth'
import { getApiErrorMessage } from '../lib/apiError'
import { useAuthStore } from '../store/authStore'

const DEV = import.meta.env.DEV

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const tokens = useAuthStore((state) => state.tokens)
  const setTokens = useAuthStore((state) => state.setTokens)
  const setAuth = useAuthStore((state) => state.setAuth)
  const clear = useAuthStore((state) => state.clear)

  const [tenantSlug, setTenantSlug] = useState('ttc')
  const [email, setEmail] = useState(DEV ? 'hr@ttc.local' : '')
  const [password, setPassword] = useState(DEV ? 'TtcDemo!2026' : '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (tokens?.access_token) {
    return <Navigate to="/" replace />
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const nextTokens = await login({
        tenant_slug: tenantSlug.trim(),
        email: email.trim(),
        password,
      })
      setTokens(nextTokens)
      const currentUser = await me()
      setAuth(nextTokens, currentUser)
      const state = location.state as { from?: string } | null
      navigate(state?.from || '/', { replace: true })
    } catch (err: unknown) {
      clear()
      setError(
        getApiErrorMessage(
          err,
          '登录失败，请检查租户、邮箱与密码，或确认后端已启动。',
        ),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="ttc-login">
      <div className="ttc-login-glow" aria-hidden="true" />
      <section className="ttc-login-card">
        <div className="ttc-login-brand">
          <span className="ttc-login-mark">
            <Activity size={22} strokeWidth={2.2} />
          </span>
          <div>
            <strong>
              TTC <span>才多对</span>
            </strong>
            <small>TALENT TRUST &amp; CONNECT</small>
          </div>
        </div>

        <div className="ttc-login-head">
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            AUTHENTICATED WORKSPACE
            <span className="hero-eyebrow-line" />
            <span>/api/v1</span>
          </div>
          <h1>登录招聘工作台</h1>
          <p>
            岗位、候选人、评估与语音会话都绑定到当前租户与登录身份；未登录无法读取真实数据。
          </p>
        </div>

        <form className="ttc-login-form" onSubmit={onSubmit}>
          <label>
            <span>租户标识</span>
            <input
              value={tenantSlug}
              onChange={(event) => setTenantSlug(event.target.value)}
              autoComplete="organization"
              required
            />
          </label>
          <label>
            <span>邮箱</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          {error && (
            <div className="ttc-inline-error" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            className="ttc-btn ttc-btn-primary ttc-login-submit"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                正在验证…
              </>
            ) : (
              <>
                <LogIn size={16} />
                登录
              </>
            )}
          </button>
        </form>

        {DEV && (
          <div className="ttc-login-hint">
            <LockKeyhole size={15} />
            <div>
              <strong>本地演示账号（仅开发模式显示）</strong>
              <span>HR：hr@ttc.local · 管理员：admin@ttc.local · 候选人：candidate@ttc.local</span>
              <span>密码：TtcDemo!2026 · 租户：ttc</span>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
