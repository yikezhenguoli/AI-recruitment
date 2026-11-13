import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

interface PageTransitionProps {
  children: ReactNode
}

/**
 * Route-level entrance animation: fade + 8px rise, ~360ms.
 *
 * - No exit delay; navigation replaces content immediately.
 * - Keyed by pathname so each route remounts the wrapper exactly once.
 * - The `/sessions` bypass lives in AppLayout because the voice workstream
 *   must keep its existing mount/lifecycle behaviour.
 */
export function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation()

  return (
    <div className="ttc-page-transition" key={location.pathname}>
      {children}
    </div>
  )
}
