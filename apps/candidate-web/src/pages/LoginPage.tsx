import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight, Loader2, LogIn } from 'lucide-react'
import { fetchMe, login } from '../api/auth'
import { getApiErrorMessage } from '../lib/apiError'
import { getEmployerLoginUrl } from '../lib/appLinks'
import { setStoredUser, setTokens } from '../lib/tokenStorage'
import { useAuthStore } from '../store/auth'
import { AuthShell } from '../components/AuthShell'

const DEFAULT_TENANT = (import.meta.env.VITE_TENANT_SLUG as string | undefined) || 'demo'
const DEV_CANDIDATE_EMAIL = import.meta.env.DEV ? 'demo.candidate@ttc.local' : ''
const DEV_CANDIDATE_PASSWORD = import.meta.env.DEV ? 'SeedDemo#2026' : ''

interface LoginState {
  from?: string
  wrongRole?: boolean
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const clear = useAuthStore((state) => state.clear)

  const state = location.state as LoginState | null
  const from = state?.from
  const autoLogin = params.get('autologin') === '1'
  const autoLoginStarted = useRef(false)

  const [tenantSlug, setTenantSlug] = useState(DEFAULT_TENANT)
  const [email, setEmail] = useState(DEV_CANDIDATE_EMAIL)
  const [password, setPassword] = useState(DEV_CANDIDATE_PASSWORD)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(
    state?.wrongRole ? '当前账号不是候选人账号。求职者中心仅向候选人开放，请更换账号登录。' : null,
  )

  const performLogin = useCallback(
    async (slug: string, userEmail: string, userPassword: string) => {
      setLoading(true)
      setError(null)
      try {
        const tokens = await login({
          tenant_slug: slug.trim(),
          email: userEmail.trim(),
          password: userPassword,
        })
        setTokens(tokens.access_token, tokens.refresh_token)
        const me = await fetchMe()
        if (me.role !== 'candidate') {
          clear()
          setError('该账号是招聘方账号，请在企业招聘工作台登录；求职者中心仅支持候选人账号。')
          return
        }
        const principal = { ...me, email: userEmail.trim() }
        setStoredUser(principal)
        setUser(principal)
        navigate(from && from !== '/login' ? from : '/', { replace: true })
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, '登录失败，请检查企业标识、邮箱与密码。'))
      } finally {
        setLoading(false)
      }
    },
    [clear, from, navigate, setUser],
  )

  useEffect(() => {
    if (!import.meta.env.DEV || !autoLogin || user || autoLoginStarted.current) return
    autoLoginStarted.current = true
    void performLogin(DEFAULT_TENANT, DEV_CANDIDATE_EMAIL, DEV_CANDIDATE_PASSWORD)
  }, [autoLogin, performLogin, user])

  if (user) {
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    await performLogin(tenantSlug, email, password)
  }

  return (
    <AuthShell>
      <form onSubmit={handleSubmit} className="card p-7 sm:p-8">
        <div className="mb-6">
          <span className="chip">候选人登录</span>
          <h2 className="mt-4 text-[24px] font-extrabold tracking-tight text-ink">欢迎回来</h2>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            使用企业发给你的账号，或直接注册一个候选人账号开始投递。
          </p>
        </div>

        <label className="mb-4 block">
          <span className="label">企业标识</span>
          <input
            className="input"
            value={tenantSlug}
            onChange={(event) => setTenantSlug(event.target.value)}
            required
            autoComplete="organization"
            placeholder="例如：demo"
          />
        </label>

        <label className="mb-4 block">
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

        <label className="mb-5 block">
          <span className="label">密码</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            placeholder="请输入密码"
          />
        </label>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-[11px] leading-relaxed text-rose-700">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
          {loading ? '正在登录…' : '登录求职者中心'}
        </button>

        <div className="mt-5 flex items-center justify-between text-xs">
          <span className="text-muted">还没有账号？</span>
          <Link
            to="/register"
            className="inline-flex items-center gap-1 font-semibold text-brand-deep hover:underline"
          >
            注册候选人账号
            <ArrowRight size={13} />
          </Link>
        </div>

        <div className="mt-5 border-t border-line/70 pt-4">
          <div className="mb-2.5 text-[11px] font-bold tracking-wide text-muted">
            {import.meta.env.DEV ? '多角色快速入口（切换至企业招聘工作台）' : '企业工作台入口'}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <a
              href={getEmployerLoginUrl(import.meta.env.DEV ? '?role=admin&autologin=1' : '')}
              className="flex flex-col rounded-xl border border-line bg-white/75 px-3 py-2.5 text-left transition hover:border-brand/50 hover:bg-white"
            >
              <span className="text-xs font-bold text-brand-deep">管理员工作台 ↗</span>
              <span className="mt-0.5 text-[11px] text-muted">系统治理、团队与集成</span>
            </a>
            <a
              href={getEmployerLoginUrl(
                import.meta.env.DEV ? '?role=hr&autologin=1' : '?role=hr',
              )}
              className="flex flex-col rounded-xl border border-line bg-white/75 px-3 py-2.5 text-left transition hover:border-brand/50 hover:bg-white"
            >
              <span className="text-xs font-bold text-brand-deep">招聘专员入口 ↗</span>
              <span className="mt-0.5 text-[11px] text-muted">岗位解析与候选人推进</span>
            </a>
          </div>
        </div>
      </form>

      <p className="mt-5 text-center text-[10px] leading-relaxed text-muted">
        登录凭证仅保存在当前浏览器会话，关闭标签页即失效。
      </p>
    </AuthShell>
  )
}
