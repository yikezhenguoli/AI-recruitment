const configuredEmployerUrl = (import.meta.env.VITE_EMPLOYER_URL || '').trim()
const employerPort = (import.meta.env.VITE_EMPLOYER_PORT || '5173').trim()

export function getEmployerOrigin(): string {
  if (configuredEmployerUrl) {
    return configuredEmployerUrl.replace(/\/+$/, '')
  }
  if (typeof window === 'undefined') {
    return `http://localhost:${employerPort}`
  }
  return `${window.location.protocol}//${window.location.hostname}:${employerPort}`
}

export function getEmployerLoginUrl(query = ''): string {
  return `${getEmployerOrigin()}/login${query}`
}
