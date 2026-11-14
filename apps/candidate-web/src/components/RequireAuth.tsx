import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getAccessToken } from '../lib/tokenStorage'
import { useAuthStore } from '../store/auth'
import { LoadingBlock } from './ui'

export function RequireAuth() {
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const loading = useAuthStore((state) => state.loading)
  const refreshUser = useAuthStore((state) => state.refreshUser)
  const hasToken = Boolean(getAccessToken())

  useEffect(() => {
    if (hasToken && !user) void refreshUser()
  }, [hasToken, user, refreshUser])

  if (!hasToken) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  if (!user) {
    if (loading) {
      return (
        <div className="mx-auto max-w-6xl px-4 py-16">
          <LoadingBlock text="正在恢复登录状态…" />
        </div>
      )
    }
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  if (user.role !== 'candidate') {
    return <Navigate to="/login" replace state={{ wrongRole: true }} />
  }

  return <Outlet />
}
