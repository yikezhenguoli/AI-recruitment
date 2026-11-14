import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowUpRight,
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
import { fetchMe, login, logout, roleLabel } from '../../api/auth'
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
      { label: '管理后台', path: '/admin', icon: Settings, adminOnly: true },
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
  const [isDrawerViewport, setIsDrawerViewport] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return false
    }
    return window.matchMedia('(max-width: 1023px)').matches
  })
  const [scrolled, setScrolled] = useState(false)
  const scrolledRef = useRef(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const mainShellRef = useRef<HTMLDivElement>(null)
  const menuBtnRef = useRef<HTMLButtonElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const clearUser = useAuthStore((state) => state.clear)
  const [switchingRole, setSwitchingRole] = useState<'admin' | 'hr' | null>(null)
  const title = resolvePageTitle(location.pathname)
  const displayName = user?.display_name || '招聘用户'
  const avatarText = displayName.slice(0, 1).toUpperCase()
  const candidatePortalHref =
    typeof window === 'undefined'
      ? 'http://localhost:5175/login?autologin=1'
      : `${window.location.protocol}//${window.location.hostname}:5175/login${import.meta.env.DEV ? '?autologin=1' : ''}`

  async function handleLogout() {
    await logout()
    clearUser()
    window.location.assign('/login')
  }

  async function handleSwitchRole(targetRole: 'admin' | 'hr') {
    if (!import.meta.env.DEV || switchingRole || user?.role === targetRole) return
    const targetEmail = targetRole === 'admin' ? 'web.test.hr@ttc.local' : 'hr.demo@ttc.local'
    setSwitchingRole(targetRole)
    try {
      await login('demo', targetEmail, 'SeedDemo#2026')
      const me = await fetchMe()
      setUser(me)
      await queryClient.invalidateQueries()
      if (targetRole === 'hr' && (location.pathname.startsWith('/team') || location.pathname.startsWith('/admin'))) {
        navigate('/')
      }
    } catch {
      navigate(`/login?role=${targetRole}`)
    } finally {
      setSwitchingRole(null)
    }
  }
  const isSessions = location.pathname === '/sessions' || location.pathname.startsWith('/sessions/')

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(max-width: 1023px)')
    const sync = () => {
      setIsDrawerViewport(query.matches)
      if (!query.matches) setMobileOpen(false)
    }
    sync()
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', sync)
      return () => query.removeEventListener('change', sync)
    }
    query.addListener(sync)
    return () => query.removeListener(sync)
  }, [])

  useEffect(() => {
    if (
      user &&
      user.role !== 'admin' &&
      (location.pathname === '/admin' || location.pathname === '/team')
    ) {
      navigate('/', { replace: true })
    }
  }, [location.pathname, navigate, user])

  useEffect(() => {
    const sidebar = sidebarRef.current as (HTMLElement & { inert: boolean }) | null
    const mainShell = mainShellRef.current as (HTMLDivElement & { inert: boolean }) | null
    const drawerActive = isDrawerViewport && mobileOpen
    if (mainShell) mainShell.inert = drawerActive
    if (sidebar) sidebar.inert = isDrawerViewport && !mobileOpen
    return () => {
      if (mainShell) mainShell.inert = false
      if (sidebar) sidebar.inert = false
    }
  }, [isDrawerViewport, mobileOpen])

  useEffect(() => {
    if (!isDrawerViewport || !mobileOpen) return
    const frame = window.requestAnimationFrame(() => closeBtnRef.current?.focus())
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileOpen(false)
        window.requestAnimationFrame(() => menuBtnRef.current?.focus())
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [isDrawerViewport, mobileOpen])

  // Passive scroll listener with rAF coalescing; only a boolean re-render.
  // Never intercepts or hijacks scrolling.
  useEffect(() => {
    const prefersMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: no-preference)').matches
    const supportsNativeScrollHeader =
      prefersMotion &&
      typeof CSS !== 'undefined' &&
      typeof CSS.supports === 'function' &&
      CSS.supports('(animation-timeline: scroll()) and (animation-range: 0% 100%)')

    if (supportsNativeScrollHeader) {
      if (scrolledRef.current) {
        scrolledRef.current = false
        setScrolled(false)
      }
      return
    }

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
  const closeDrawerAndRestoreFocus = () => {
    setMobileOpen(false)
    if (isDrawerViewport) {
      window.requestAnimationFrame(() => menuBtnRef.current?.focus())
    }
  }

  return (
    <div className="ttc-app">
      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-sm lg:hidden"
          aria-label="关闭导航"
          onClick={closeDrawerAndRestoreFocus}
        />
      )}

      <aside
        ref={sidebarRef}
        id="ttc-nav-drawer"
        role={isDrawerViewport ? 'dialog' : undefined}
        aria-modal={isDrawerViewport && mobileOpen ? true : undefined}
        aria-label={isDrawerViewport ? '主导航菜单' : undefined}
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
            <button
              ref={closeBtnRef}
              type="button"
              className="ttc-icon-btn lg:hidden"
              onClick={closeDrawerAndRestoreFocus}
              aria-label="关闭导航"
            >
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
            <div className="ttc-role-switcher" aria-label="视角与角色入口">
              <div className="ttc-role-switcher-head">
                <span>角色切换</span>
                <span>{roleLabel(user?.role ?? '')}</span>
              </div>
              <div className="ttc-role-pills">
                {import.meta.env.DEV && (
                  <>
                    <button
                      type="button"
                      className={`ttc-role-pill ${user?.role === 'admin' ? 'is-active' : ''}`}
                      disabled={switchingRole !== null}
                      onClick={() => void handleSwitchRole('admin')}
                    >
                      {switchingRole === 'admin' ? '切换中…' : '管理员'}
                    </button>
                    <button
                      type="button"
                      className={`ttc-role-pill ${user?.role === 'hr' ? 'is-active' : ''}`}
                      disabled={switchingRole !== null}
                      onClick={() => void handleSwitchRole('hr')}
                    >
                      {switchingRole === 'hr' ? '切换中…' : '招聘专员'}
                    </button>
                  </>
                )}
                <a className="ttc-role-pill" href={candidatePortalHref}>
                  求职者 ↗
                </a>
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

      <div ref={mainShellRef} className="ttc-main">
        <header className={`ttc-topbar ${scrolled ? 'is-scrolled' : ''}`}>
          <div className="ttc-topbar-inner">
            <div className="ttc-topbar-left">
              <button
                ref={menuBtnRef}
                type="button"
                className="ttc-icon-btn lg:hidden"
                onClick={() => setMobileOpen(true)}
                aria-expanded={isDrawerViewport ? mobileOpen : undefined}
                aria-controls="ttc-nav-drawer"
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
              <a
                className="ttc-btn ttc-btn-ghost ttc-btn-sm"
                href={candidatePortalHref}
                title="切换至求职者中心"
              >
                <span>求职者端</span>
                <ArrowUpRight size={14} aria-hidden="true" />
              </a>
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
