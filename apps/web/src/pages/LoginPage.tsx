import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { FileText, LogIn, ShieldCheck, Sparkles } from 'lucide-react'
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
      <aside className="ttc-login-aside">
        <div className="ttc-login-aside-brand">
          <img src="/ttc-mark.svg" alt="" width={42} height={42} />
          <div>
            <strong>TTC 才多对</strong>
            <span>TALENT TRUST &amp; CONNECT</span>
          </div>
        </div>

        <div className="ttc-login-aside-copy">
          <h2>
            把招聘的每一步
            <br />
            都<em>留下依据</em>。
          </h2>
          <p>
            岗位解析、简历证据、语音面试与评估报告，在同一条链路上完成。
            招聘方看到的每个结论，都能回到原始材料。
          </p>
          <ul className="ttc-login-points">
            <li>
              <ShieldCheck size={16} aria-hidden="true" />
              真实候选人需先取得授权，数据可随时撤回。
            </li>
            <li>
              <Sparkles size={16} aria-hidden="true" />
              AI 给出结构化判断依据，人工保留最终复核权。
            </li>
            <li>
              <FileText size={16} aria-hidden="true" />
              每一步产物都可追溯到简历原文与面试转写。
            </li>
          </ul>
        </div>

        <div className="ttc-login-aside-foot">© 2026 TTC · AI 辅助决策，人工最终复核</div>
      </aside>

      <form className="ttc-login-card" onSubmit={handleSubmit} aria-labelledby="login-title">
        <div className="ttc-login-brand">
          <img src="/ttc-mark.svg" alt="" width={40} height={40} />
          <div>
            <strong id="login-title">招聘工作台</strong>
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
