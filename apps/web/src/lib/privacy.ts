export function maskEmail(value?: string | null): string {
  if (!value) return '—'
  const [local, domain] = value.split('@')
  if (!domain) return '***'
  const visible = local.slice(0, Math.min(2, local.length))
  return `${visible}${'*'.repeat(Math.max(3, local.length - visible.length))}@${domain}`
}

export function maskPhone(value?: string | null): string {
  if (!value) return '—'
  const digits = value.replace(/[^\d+]/g, '')
  if (digits.length < 7) return '***'
  return `${digits.slice(0, 3)}****${digits.slice(-4)}`
}

const SENSITIVE_KEY_PATTERNS = [
  /phone/i,
  /mobile/i,
  /email/i,
  /contact/i,
  /wechat/i,
  /qq/i,
  /student_?id/i,
  /identity/i,
  /gender/i,
  /sex/i,
  /age/i,
  /birth/i,
  /address/i,
  /political/i,
  /身份证/,
  /手机/,
  /电话/,
  /邮箱/,
  /性别/,
]

function redactText(value: string): string {
  return value
    .replace(/[\w.+-]+@[\w-]+\.[\w.-]+/g, (email) => maskEmail(email))
    .replace(/(?<!\d)1[3-9]\d{9}(?!\d)/g, (phone) => maskPhone(phone))
}

function redactValue(value: unknown): unknown {
  if (typeof value === 'string') return redactText(value)
  if (Array.isArray(value)) return value.map(redactValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        redactValue(item),
      ]),
    )
  }
  return value
}

/**
 * Extra parser fields may contain phone numbers, email addresses, student IDs,
 * gender, or other personal data. Hide sensitive keys and redact contact values
 * before rendering them in the candidate detail/report.
 */
export function sanitizeAdditionalInfo(
  info: Record<string, unknown>,
): Record<string, unknown> {
  const safe: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(info)) {
    if (SENSITIVE_KEY_PATTERNS.some((pattern) => pattern.test(key))) continue
    safe[key] = redactValue(value)
  }
  return safe
}
