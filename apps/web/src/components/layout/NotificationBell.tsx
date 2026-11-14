import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../../api/notifications'
import { formatDateTime } from '../../lib/format'
import type { NotificationItem } from '../../types'

function targetPath(item: NotificationItem): string | null {
  if (!item.link) return null
  if (item.link.startsWith('/offers')) return '/offers'
  if (item.link.startsWith('/interviews')) return '/interviews'
  return null
}

function hasNativePopover(): boolean {
  return (
    typeof HTMLElement !== 'undefined' &&
    Object.prototype.hasOwnProperty.call(HTMLElement.prototype, 'popover')
  )
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const popoverId = `ttc-notify-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  const supportsPopover = hasNativePopover()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['notifications'],
    queryFn: () => listNotifications(false),
    refetchInterval: 30_000,
    retry: 1,
  })

  useEffect(() => {
    if (!supportsPopover) return
    const el = panelRef.current
    if (!el) return
    const onToggle = (event: Event) => {
      const next = (event as Event & { newState?: string }).newState === 'open'
      setOpen(next)
    }
    el.addEventListener('toggle', onToggle)
    return () => el.removeEventListener('toggle', onToggle)
  }, [supportsPopover])

  useEffect(() => {
    if (supportsPopover || !open) return
    const onMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onMouseDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, supportsPopover])

  const closePanel = useCallback(() => {
    if (supportsPopover) {
      const el = panelRef.current as (HTMLDivElement & { hidePopover?: () => void }) | null
      el?.hidePopover?.()
      return
    }
    setOpen(false)
  }, [supportsPopover])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  const readMutation = useMutation({
    mutationFn: (item: NotificationItem) => markNotificationRead(item.id),
    onSuccess: invalidate,
  })
  const readAllMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: invalidate,
  })

  const unread = query.data?.unread ?? 0
  const items = query.data?.items ?? []

  const panelBody = (
    <>
      <div className="ttc-notify-head">
        <strong style={{ fontSize: 12 }}>通知</strong>
        <button
          type="button"
          className="ttc-btn ttc-btn-secondary ttc-btn-sm"
          disabled={unread === 0 || readAllMutation.isPending}
          onClick={() => readAllMutation.mutate()}
        >
          全部已读
        </button>
      </div>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`ttc-notify-item ${item.read_at ? '' : 'is-unread'}`}
          onClick={() => {
            if (!item.read_at) readMutation.mutate(item)
            const path = targetPath(item)
            if (path) {
              closePanel()
              navigate(path)
            }
          }}
        >
          <strong>{item.title}</strong>
          <span>{item.body ?? ''}</span>
          <span>{formatDateTime(item.created_at)}</span>
        </button>
      ))}
      {items.length === 0 && (
        <p className="ttc-muted" style={{ fontSize: 11 }}>
          {query.isLoading ? '读取中…' : '暂时没有通知。'}
        </p>
      )}
    </>
  )

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="ttc-icon-btn ttc-notify-trigger"
        aria-label={`通知${unread ? `（${unread} 条未读）` : ''}`}
        aria-expanded={open}
        aria-controls={popoverId}
        {...(supportsPopover ? { popovertarget: popoverId } : { onClick: () => setOpen((v) => !v) })}
      >
        <Bell size={17} />
        {unread > 0 && <span className="ttc-badge-dot">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {supportsPopover ? (
        <div
          id={popoverId}
          ref={panelRef}
          className="ttc-notify-panel ttc-notify-popover"
          role="region"
          aria-label="通知"
          {...({ popover: 'auto' } as Record<string, string>)}
        >
          {panelBody}
        </div>
      ) : (
        open && (
          <div id={popoverId} className="ttc-notify-panel" role="dialog" aria-label="通知">
            {panelBody}
          </div>
        )
      )}
    </div>
  )
}
