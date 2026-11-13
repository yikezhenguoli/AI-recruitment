import { useEffect, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { fetchMe } from '../api/auth'
import { getTokens } from '../lib/tokenStorage'
import { useAuthStore } from '../store/authStore'

export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const status = useAuthStore((state) => state.status)
  const setUser = useAuthStore((state) => state.setUser)
  const setStatus = useAuthStore((state) => state.setStatus)
  const clear = useAuthStore((state) => state.clear)

  useEffect(() => {
    if (!getTokens()) {
      setStatus('anonymous')
      return
    }
    if (user) return
    setStatus('loading')
    fetchMe()
      .then(setUser)
      .catch(() => clear())
  }, [user, setUser, setStatus, clear])

  if (!getTokens()) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }

  if (!user) {
    if (status === 'anonymous') return <Navigate to="/login" replace />
    return <div className="ttc-boot">正在验证登录状态…</div>
  }

  return <>{children}</>
}
