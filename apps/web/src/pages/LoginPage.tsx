import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { fetchMe, login } from '../api/auth'
import { getApiErrorMessage } from '../lib/apiError'
import { useAuthStore } from '../store/authStore'

export default function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const setUser = useAuthStore((state) => state.setUser)
  const [tenantSlug, setTenantSlug] = useState('demo')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(tenantSlug.trim(), email.trim(), password)
      const user = await fetchMe()
      setUser(user)
      const next = params.get('next')
      navigate(next && next.startsWith('/') ? next : '/', { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err, '登录失败，请检查账号与密码。'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="ttc-login">
      <form className="ttc-login-card" onSubmit={handleSubmit}>
        <div className="ttc-login-brand">
          <img src="/ttc-mark.svg" alt="" width={40} height={40} />
          <div>
            <strong>招聘工作台</strong>
            <span>TTC Talent Workbench</span>
          </div>
        </div>

        <label className="ttc-login-field">
          <span>租户</span>
          <input
            value={tenantSlug}
            onChange={(event) => setTenantSlug(event.target.value)}
            autoComplete="organization"
            required
          />
        </label>

        <label className="ttc-login-field">
          <span>邮箱</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
            placeholder="you@example.com"
            required
          />
        </label>

        <label className="ttc-login-field">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error ? <p className="ttc-login-error" role="alert">{error}</p> : null}

        <button className="ttc-btn ttc-btn-primary ttc-login-submit" type="submit" disabled={submitting}>
          <LogIn size={16} aria-hidden="true" />
          {submitting ? '登录中…' : '登录'}
        </button>

        <p className="ttc-login-note">
          仅招聘方账号可进入工作台。候选人请使用候选人门户。
        </p>
      </form>
    </div>
  )
}
