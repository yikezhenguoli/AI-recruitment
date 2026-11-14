import type { JobStatus, VoiceSessionStatus } from '../types'

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  draft: '草稿',
  published: '已发布',
  locked: '已锁定',
  archived: '已归档',
}

export const VOICE_STATUS_LABELS: Record<VoiceSessionStatus, string> = {
  created: '待接通',
  connecting: '连接中',
  live: '进行中',
  ended: '已结束',
  failed: '失败',
  revoked: '授权撤回',
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

/**
 * Display-only formatting for the first_name/last_name pair returned by the
 * resume parser. CJK names read surname-first; Western names keep first-last.
 */
export function formatPersonName(
  first?: string | null,
  last?: string | null,
): string {
  const given = (first || '').trim()
  const surname = (last || '').trim()

  if (!given) return surname
  if (!surname) return given

  const isCjk = /[㐀-鿿]/
  if (isCjk.test(given) && isCjk.test(surname)) {
    return `${surname}${given}`
  }
  return `${given} ${surname}`
}
