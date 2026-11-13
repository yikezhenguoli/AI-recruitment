import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import {
  BriefcaseBusiness,
  FileText,
  Home,
  LogOut,
  Menu,
  PhoneCall,
  UserRound,
  X,
} from 'lucide-react'
import { logout } from '../api/auth'
import { getRefreshToken } from '../lib/tokenStorage'
import { useAuthStore } from '../store/auth'

const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: '/', label: '首页', icon: Home, end: true },
  { to: '/jobs', label: '岗位机会', icon: BriefcaseBusiness },
  { to: '/applications', label: '我的投递', icon: FileText },
  { to: '/interviews', label: '我的面试', icon: PhoneCall },
  { to: '/profile', label: '我的', icon: UserRound },
]

export function AppLayout() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const clear = useAuthStore((state) => state.clear)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('resize', close)
    return () => window.removeEventListener('resize', close)
  }, [open])

  const handleLogout = async () => {
    const refreshToken = getRefreshToken()
    try {
      if (refreshToken) await logout(refreshToken)
    } catch {
      // A failed revoke must not trap the user in a dead session.
    }
    clear()
    navigate('/login', { replace: true })
  }

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold transition ${
      isActive
        ? 'nav-pill-active bg-white text-brand-deep shadow-soft'
        : 'text-muted hover:bg-white/60 hover:text-ink'
    }`

  return (
    <div className="min-h-screen">
      <header className="glass-nav sticky top-0 z-30">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <NavLink to="/jobs" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
            <img src="/ttc-mark.svg" alt="" className="h-9 w-9 rounded-xl shadow-soft" />
            <div className="leading-tight">
              <div className="brand-jitter text-[15px] font-extrabold tracking-tight text-ink">
                TTC <span className="text-brand-deep">才多对</span>
              </div>
              <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted">
                求职者中心
              </div>
            </div>
          </NavLink>

          <nav className="ml-6 hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                <item.icon size={15} />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-bold text-ink">{user?.display_name ?? '求职者'}</div>
              <div className="text-[10px] text-muted">候选人账号</div>
            </div>
            <button
              type="button"
              onClick={() => void handleLogout()}
              className="btn-quiet"
              title="退出登录"
            >
              <LogOut size={15} />
              <span className="hidden sm:inline">退出</span>
            </button>
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              className="btn-quiet md:hidden"
              aria-label="切换导航"
            >
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>

        {open && (
          <nav className="border-t border-line/70 bg-white/85 px-3 py-2 md:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={navClass}
                onClick={() => setOpen(false)}
              >
                <item.icon size={16} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-8 pt-4 sm:px-6">
        <div className="divider mb-4" />
        <p className="text-center text-[11px] leading-relaxed text-muted">
          TTC 才多对 · AI 辅助匹配，最终录用决定由人工做出。你的简历仅在本企业租户内处理，
          可随时在「我的 → 授权与隐私」中查看或撤回。
        </p>
      </footer>
    </div>
  )
}
