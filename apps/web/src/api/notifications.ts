import { API_PREFIX, api } from './client'
import type { NotificationList } from '../types'

export async function listNotifications(unreadOnly = false): Promise<NotificationList> {
  const response = await api.get(`${API_PREFIX}/notifications`, {
    params: { unread_only: unreadOnly, limit: 30 },
  })
  return response.data as NotificationList
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await api.post(`${API_PREFIX}/notifications/${notificationId}/read`)
}

export async function markAllNotificationsRead(): Promise<number> {
  const response = await api.post(`${API_PREFIX}/notifications/read-all`)
  return response.data.marked as number
}
