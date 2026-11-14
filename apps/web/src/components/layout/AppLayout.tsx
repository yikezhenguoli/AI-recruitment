import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Briefcase,
  CalendarClock,
  ChevronRight,
  FileSignature,
  LayoutDashboard,
  LogOut,
  Menu,
  Mic,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { getHealth } from '../../api/client'
import { logout, roleLabel } from '../../api/auth'
import { useAuthStore } from '../../store/authStore'
import { CursorTrail } from '../visual/CursorTrail'
import { NotificationBell } from './NotificationBell'
import { PageTransition } from './PageTransition'

const NAV_GROUPS: {
  label: string
  items: { label: string; path: string; icon: LucideIcon; end?: boolean; adminOnly?: boolean }[]
}[] = [
  {
    label: '工作空间',
    items: [
      { label: '工作台首页', path: '/', icon: LayoutDashboard, end: true },
      { label: '岗位管理', path: '/jobs', icon: Briefcase },
      { label: '候选人', path: '/candidates', icon: Users },
      { label: 'Offer 管理', path: '/offers', icon: FileSignature },
      { label: '面试排期', path: '/interviews', icon: CalendarClock },
      { label: '人才库', path: '/talent', icon: Search },
    ],
  },
  {
    label: '评估与治理',
    items: [
      { label: '语音会话', path: '/sessions', icon: Mic },
      { label: '团队与权限', path: '/team', icon: ShieldCheck, adminOnly: true },
      { label: '管理后台', path: '/admin', icon: Settings },
    ],
  },
]

function resolvePageTitle(pathname: string): string {
  if (pathname === '/') return '工作台首页'
  if (pathname === '/jobs') return '岗位管理'
  if (pathname === '/jobs/new') return '新建岗位'
  if (/^\/jobs\/[^/]+\/edit$/.test(pathname)) return '编辑岗位'
  if (/^\/jobs\/[^/]+$/.test(pathname)) return '岗位详情'
  if (pathname === '/candidates') return '候选人'
  if (/^\/candidates\/[^/]+\/evidence$/.test(pathname)) return '证据中心'
  if (/^\/candidates\/[^/]+\/report$/.test(pathname)) return '评估报告'
  if (/^\/candidates\/[^/]+$/.test(pathname)) return '候选人详情'
  if (pathname === '/offers') return 'Offer 管理'
  if (pathname === '/interviews') return '面试排期'
  if (pathname === '/talent') return '人才库'
  if (pathname === '/team') return '团队与权限'
  if (pathname === '/sessions') return '语音会话'
  if (/^\/sessions\/[^/]+$/.test(pathname)) return '会话详情'
  if (pathname === '/admin') return '管理后台'
  return '招聘工作台'
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const scrolledRef = useRef(false)
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const clearUser = useAuthStore((state) => state.clear)
  const title = resolvePageTitle(location.pathname)
  const displayName = user?.display_name || '招聘用户'
  const avatarText = displayName.slice(0, 1).toUpperCase()

  async function handleLogout() {
    await logout()
    clearUser()
    window.location.assign('/login')
  }
  const isSessions = location.pathname === '/sessions' || location.pathname.startsWith('/sessions/')

  // Passive scroll listener with rAF coalescing; only a boolean re-render.
  // Never intercepts or hijacks scrolling.
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
    queryKey: ['health'],
    queryFn: getHealth,
    retry: 1,
    refetchInterval: 30_000,
  })

  const healthState = healthQuery.isLoading
    ? { label: '检测后端…', tone: 'neutral' }
    : healthQuery.isError
      ? { label: '后端未连接', tone: 'danger' }
      : healthQuery.data?.status === 'ready'
        ? { label: '后端就绪', tone: 'ok' }
        : { label: '后端异常', tone: 'warn' }

  const closeMobile = () => setMobileOpen(false)

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
              <div className="ttc-brand-sub">TALENT TRUST & CONNECT</div>
            </div>
            <button type="button" className="ttc-icon-btn lg:hidden" onClick={closeMobile} aria-label="关闭导航">
              <X size={18} />
            </button>
          </div>

          <div className="ttc-workspace-label">招聘管理中心</div>

          <nav className="ttc-nav" aria-label="主导航">
            {NAV_GROUPS.map((group) => (
              <section className="ttc-nav-group" key={group.label}>
                <div className="ttc-nav-group-title">{group.label}</div>
                {group.items
                  .filter((item) => !item.adminOnly || user?.role === 'admin')
                  .map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.end}
                      onClick={closeMobile}
                      className={({ isActive }) => `ttc-nav-link ${isActive ? 'is-active' : ''}`}
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
                <span>岗位解析 → 简历筛选 → 评估报告</span>
              </div>
            </div>
            <div className="ttc-profile">
              <span className="ttc-avatar">{avatarText}</span>
              <div>
                <strong>{displayName}</strong>
                <span>{roleLabel(user?.role ?? '')}</span>
              </div>
              <ShieldCheck size={16} className="ttc-profile-shield" />
            </div>
            <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm" onClick={handleLogout}>
              退出登录
            </button>
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
              <NotificationBell />
              <div className="ttc-topbar-divider" />
              <span className="ttc-avatar ttc-avatar-sm">{avatarText}</span>
              <div className="ttc-topbar-user">
                <strong>{displayName}</strong>
                <span>{roleLabel(user?.role ?? '')}</span>
              </div>
              <button type="button" className="ttc-icon-btn" aria-label="退出登录" onClick={handleLogout}>
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </header>

        <main className="ttc-content">
          {isSessions ? <Outlet /> : (
            <PageTransition>
              <Outlet />
            </PageTransition>
          )}
        </main>

        <footer className="ttc-footer">
          <span>© 2026 TTC · Talent Trust & Connect</span>
          <span>AI 辅助决策 · 人工最终复核</span>
        </footer>
      </div>
      <CursorTrail />
    </div>
  )
}
