import { useEffect, useRef, useState } from 'react'
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

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['notifications'],
    queryFn: () => listNotifications(false),
    refetchInterval: 30_000,
    retry: 1,
  })

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [open])

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

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="ttc-icon-btn"
        aria-label={`通知${unread ? `（${unread} 条未读）` : ''}`}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={17} />
        {unread > 0 && <span className="ttc-badge-dot">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div className="ttc-notify-panel" role="dialog" aria-label="通知">
          <div className="ttc-notify-head">
            <strong style={{ fontSize: 12 }}>通知</strong>
            <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              disabled={unread === 0 || readAllMutation.isPending}
              onClick={() => readAllMutation.mutate()}>
              全部已读
            </button>
          </div>
          {items.map((item) => (
            <button key={item.id} type="button"
              className={`ttc-notify-item ${item.read_at ? '' : 'is-unread'}`}
              onClick={() => {
                if (!item.read_at) readMutation.mutate(item)
                const path = targetPath(item)
                if (path) {
                  setOpen(false)
                  navigate(path)
                }
              }}>
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
        </div>
      )}
    </div>
  )
}
