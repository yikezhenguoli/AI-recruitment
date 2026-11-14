import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthTokens, CurrentUser } from '../types'

interface AuthState {
  tokens: AuthTokens | null
  user: CurrentUser | null
  setAuth: (tokens: AuthTokens, user: CurrentUser) => void
  setTokens: (tokens: AuthTokens) => void
  setUser: (user: CurrentUser) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      tokens: null,
      user: null,
      setAuth: (tokens, user) => set({ tokens, user }),
      setTokens: (tokens) => set({ tokens }),
      setUser: (user) => set({ user }),
      clear: () => set({ tokens: null, user: null }),
    }),
    { name: 'ttc-auth-v1' },
  ),
)

export function accessToken(): string | null {
  return useAuthStore.getState().tokens?.access_token ?? null
}

export function refreshToken(): string | null {
  return useAuthStore.getState().tokens?.refresh_token ?? null
}

export function clearAuth(): void {
  useAuthStore.getState().clear()
}
