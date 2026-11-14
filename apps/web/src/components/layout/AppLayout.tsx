import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Bell,
  Briefcase,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  Menu,
  Mic,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import { getHealth, getReadiness } from '../../api/client'
import { logout, me } from '../../api/auth'
import { refreshToken, useAuthStore } from '../../store/authStore'
import type { Role } from '../../types'
import { CursorTrail } from '../visual/CursorTrail'
import { ErrorBoundary } from './ErrorBoundary'
import { PageTransition } from './PageTransition'

const ROLE_LABEL: Record<Role, string> = {
  admin: '管理员',
  hr: '招聘管理员',
  candidate: '候选人',
}

function resolvePageTitle(pathname: string): string {
  if (pathname === '/') return '工作台首页'
  if (pathname === '/jobs') return '岗位管理'
  if (pathname === '/jobs/new') return '新建岗位'
  if (/^\/jobs\/[^/]+$/.test(pathname)) return '岗位详情'
  if (pathname === '/candidates') return '候选人'
  if (/^\/candidates\/[^/]+\/evidence$/.test(pathname)) return '证据中心'
  if (/^\/candidates\/[^/]+\/report$/.test(pathname)) return '评估报告'
  if (/^\/candidates\/[^/]+$/.test(pathname)) return '候选人详情'
  if (pathname === '/sessions') return '语音会话'
  if (pathname === '/admin') return '管理后台'
  return '招聘工作台'
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const scrolledRef = useRef(false)
  const location = useLocation()
  const navigate = useNavigate()
  const storedUser = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const clear = useAuthStore((state) => state.clear)
  const title = resolvePageTitle(location.pathname)
  const isSessions = location.pathname === '/sessions'

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: me,
    retry: 0,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (meQuery.data) setUser(meQuery.data)
  }, [meQuery.data, setUser])

  const user = meQuery.data ?? storedUser
  const role = user?.role ?? 'hr'
  const displayName = user?.display_name ?? '招聘管理员'
  const roleLabel = ROLE_LABEL[role]
  const initials = displayName.slice(0, 2).toUpperCase()

  const navGroups = [
    {
      label: '工作空间',
      items: [
        { label: '工作台首页', path: '/', icon: LayoutDashboard, end: true },
        { label: '岗位管理', path: '/jobs', icon: Briefcase },
        { label: '候选人', path: '/candidates', icon: Users },
      ],
    },
    {
      label: '评估与治理',
      items: [
        { label: '语音会话', path: '/sessions', icon: Mic },
        ...(role === 'admin'
          ? [{ label: '管理后台', path: '/admin', icon: Settings }]
          : []),
      ],
    },
  ]

  useEffect(() => {
    let frame = 0
    const sync = () => {
      frame = 0
      const next = window.scrollY > 8
      if (next !== scrolledRef.current) {
        scrolledRef.current = next
        setScrolled(next)
      }
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(sync)
    }
    sync()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  const healthQuery = useQuery({
    queryKey: ['health', 'live'],
    queryFn: getHealth,
    retry: 1,
    refetchInterval: 30_000,
  })
  const readyQuery = useQuery({
    queryKey: ['health', 'ready'],
    queryFn: getReadiness,
    retry: 1,
    refetchInterval: 30_000,
  })

  const healthState = healthQuery.isLoading
    ? { label: '检测后端…', tone: 'neutral' }
    : healthQuery.isError
      ? { label: '后端未连接', tone: 'danger' }
      : readyQuery.isError
        ? { label: '后端在线 · 数据库异常', tone: 'warn' }
        : { label: '后端就绪 · /api/v1', tone: 'ok' }

  const closeMobile = () => setMobileOpen(false)

  const onLogout = async () => {
    await logout(refreshToken())
    clear()
    navigate('/login', { replace: true })
  }

  return (
    <div className="ttc-app">
      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-sm lg:hidden"
          aria-label="关闭导航"
          onClick={closeMobile}
        />
      )}

      <aside
        className={`ttc-sidebar fixed inset-y-0 left-0 z-50 w-[272px] transition-transform duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="ttc-sidebar-inner">
          <div className="ttc-brand">
            <img src="/ttc-mark.svg" alt="" className="ttc-brand-mark" />
            <div className="ttc-brand-copy">
              <div className="ttc-brand-name">
                TTC <span>才多对</span>
              </div>
              <div className="ttc-brand-sub">TALENT TRUST &amp; CONNECT</div>
            </div>
            <button
              type="button"
              className="ttc-icon-btn lg:hidden"
              onClick={closeMobile}
              aria-label="关闭导航"
            >
              <X size={18} />
            </button>
          </div>

          <div className="ttc-workspace-label">招聘管理中心</div>

          <nav className="ttc-nav" aria-label="主导航">
            {navGroups.map((group) => (
              <section className="ttc-nav-group" key={group.label}>
                <div className="ttc-nav-group-title">{group.label}</div>
                {group.items.map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.end}
                      onClick={closeMobile}
                      className={({ isActive }) =>
                        `ttc-nav-link ${isActive ? 'is-active' : ''}`
                      }
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
                    </NavLink>
                  )
                })}
              </section>
            ))}
          </nav>

          <div className="ttc-sidebar-footer">
            <div className="ttc-stage-card">
              <span className="ttc-stage-icon">
                <Sparkles size={15} />
              </span>
              <div>
                <strong>P0 · AI 招聘闭环</strong>
                <span>岗位 → 简历解析 → 匹配评估</span>
              </div>
            </div>
            <div className="ttc-profile">
              <span className="ttc-avatar">{initials}</span>
              <div>
                <strong>{displayName}</strong>
                <span>{roleLabel} · {user?.tenant_id?.slice(0, 8) ?? 'ttc'}</span>
              </div>
              <button
                type="button"
                className="ttc-icon-btn"
                onClick={() => void onLogout()}
                aria-label="退出登录"
                title="退出登录"
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <div className="ttc-main">
        <header className={`ttc-topbar ${scrolled ? 'is-scrolled' : ''}`}>
          <div className="ttc-topbar-inner">
            <div className="ttc-topbar-left">
              <button
                type="button"
                className="ttc-icon-btn lg:hidden"
                onClick={() => setMobileOpen(true)}
                aria-label="打开导航"
              >
                <Menu size={19} />
              </button>
              <div className="ttc-breadcrumb">
                <span>工作空间</span>
                <ChevronRight size={14} />
                <strong>{title}</strong>
              </div>
            </div>

            <div className="ttc-topbar-actions">
              <span className={`ttc-status ttc-status-${healthState.tone}`}>
                <i />
                {healthState.label}
              </span>
              <button type="button" className="ttc-icon-btn" aria-label="通知">
                <Bell size={17} />
              </button>
              <div className="ttc-topbar-divider" />
              <span className="ttc-avatar ttc-avatar-sm">{initials}</span>
              <div className="ttc-topbar-user">
                <strong>{displayName}</strong>
                <span>{roleLabel}</span>
              </div>
              <button
                type="button"
                className="ttc-icon-btn"
                onClick={() => void onLogout()}
                aria-label="退出登录"
                title="退出登录"
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </header>

        <main className="ttc-content">
          <ErrorBoundary>
            {isSessions ? (
              <Outlet />
            ) : (
              <PageTransition>
                <Outlet />
              </PageTransition>
            )}
          </ErrorBoundary>
        </main>

        <footer className="ttc-footer">
          <span>© 2026 TTC · Talent Trust &amp; Connect</span>
          <span>AI 辅助决策 · 人工最终复核</span>
        </footer>
      </div>
      <CursorTrail />
    </div>
  )
}
