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
