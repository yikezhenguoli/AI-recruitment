const KEY = 'ttc.tokens'

export interface Tokens {
  access_token: string
  refresh_token: string
  token_type?: string
  expires_in?: number
}

export function getTokens(): Tokens | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Tokens
    return parsed?.access_token && parsed?.refresh_token ? parsed : null
  } catch {
    return null
  }
}

export function setTokens(tokens: Tokens): void {
  sessionStorage.setItem(KEY, JSON.stringify(tokens))
}

export function clearTokens(): void {
  sessionStorage.removeItem(KEY)
}
