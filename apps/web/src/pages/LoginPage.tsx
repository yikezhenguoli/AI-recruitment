import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { fetchMe, login } from '../api/auth'
import { getApiErrorMessage } from '../lib/apiError'
import { useAuthStore } from '../store/authStore'

const DEV_ROLE_ACCOUNTS = {
  admin: { email: 'web.test.hr@ttc.local', label: '管理员', hint: '全部后台与团队权限' },
  hr: { email: 'hr.demo@ttc.local', label: '招聘专员', hint: '日常岗位与候选人流' },
} as const
const DEV_DEFAULT_PASSWORD = import.meta.env.DEV ? 'SeedDemo#2026' : ''

export default function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const setUser = useAuthStore((state) => state.setUser)
  const roleParam = params.get('role') === 'hr' ? 'hr' : 'admin'
  const [tenantSlug, setTenantSlug] = useState('demo')
  const [email, setEmail] = useState(import.meta.env.DEV ? DEV_ROLE_ACCOUNTS[roleParam].email : '')
  const [password, setPassword] = useState(DEV_DEFAULT_PASSWORD)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const autoLoginStarted = useRef(false)
  const nextPath = params.get('next')
  const autoLogin = params.get('autologin') === '1'
  const candidatePortalHref =
    typeof window === 'undefined'
      ? 'http://localhost:5175/login?autologin=1'
      : `${window.location.protocol}//${window.location.hostname}:5175/login${import.meta.env.DEV ? '?autologin=1' : ''}`

  const performLogin = useCallback(async (slug: string, userEmail: string, userPassword: string) => {
    setError('')
    setSubmitting(true)
    try {
      await login(slug.trim(), userEmail.trim(), userPassword)
      const user = await fetchMe()
      setUser(user)
      navigate(nextPath && nextPath.startsWith('/') ? nextPath : '/', { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err, '登录失败，请检查账号与密码。'))
    } finally {
      setSubmitting(false)
    }
  }, [navigate, nextPath, setUser])

  useEffect(() => {
    if (!import.meta.env.DEV) return
    setEmail(DEV_ROLE_ACCOUNTS[roleParam].email)
    setPassword(DEV_DEFAULT_PASSWORD)
  }, [roleParam])

  useEffect(() => {
    if (!import.meta.env.DEV || !autoLogin || autoLoginStarted.current) return
    autoLoginStarted.current = true
    void performLogin('demo', DEV_ROLE_ACCOUNTS[roleParam].email, DEV_DEFAULT_PASSWORD)
  }, [autoLogin, performLogin, roleParam])

  function handleQuickRoleLogin(role: 'admin' | 'hr') {
    if (!import.meta.env.DEV) return
    const nextEmail = DEV_ROLE_ACCOUNTS[role].email
    setTenantSlug('demo')
    setEmail(nextEmail)
    setPassword(DEV_DEFAULT_PASSWORD)
    void performLogin('demo', nextEmail, DEV_DEFAULT_PASSWORD)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void performLogin(tenantSlug, email, password)
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

        <div className="ttc-login-roles">
          <span className="ttc-login-roles-title">
            {import.meta.env.DEV ? '多角色快速入口（点击即进入对应工作台）' : '其他角色门户'}
          </span>
          <div className="ttc-login-role-grid">
            {import.meta.env.DEV && (
              <>
                <button
                  type="button"
                  className="ttc-login-role-btn"
                  disabled={submitting}
                  onClick={() => handleQuickRoleLogin('admin')}
                >
                  <strong>{DEV_ROLE_ACCOUNTS.admin.label}</strong>
                  <span>{DEV_ROLE_ACCOUNTS.admin.hint}</span>
                </button>
                <button
                  type="button"
                  className="ttc-login-role-btn"
                  disabled={submitting}
                  onClick={() => handleQuickRoleLogin('hr')}
                >
                  <strong>{DEV_ROLE_ACCOUNTS.hr.label}</strong>
                  <span>{DEV_ROLE_ACCOUNTS.hr.hint}</span>
                </button>
              </>
            )}
            <a className="ttc-login-role-btn" href={candidatePortalHref}>
              <strong>求职者门户 ↗</strong>
              <span>候选人投递与面试进度</span>
            </a>
          </div>
        </div>

        <p className="ttc-login-note">
          仅招聘方账号可进入工作台。候选人请使用候选人门户。
        </p>
      </form>
    </div>
  )
}
