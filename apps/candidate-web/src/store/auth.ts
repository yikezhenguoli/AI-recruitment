import { create } from 'zustand'
import { fetchMe } from '../api/auth'
import {
  clearTokens,
  getAccessToken,
  getStoredUser,
  setStoredUser,
} from '../lib/tokenStorage'
import type { Me } from '../api/types'

interface AuthState {
  user: Me | null
  loading: boolean
  setUser: (user: Me | null) => void
  refreshUser: () => Promise<Me | null>
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: getStoredUser(),
  loading: false,
  setUser: (user) => {
    if (user) setStoredUser(user)
    set({ user })
  },
  refreshUser: async () => {
    if (!getAccessToken()) return null
    set({ loading: true })
    try {
      const user = await fetchMe()
      setStoredUser(user)
      set({ user })
      return user
    } catch {
      return null
    } finally {
      set({ loading: false })
    }
  },
  clear: () => {
    clearTokens()
    set({ user: null })
  },
}))

if (typeof window !== 'undefined') {
  window.addEventListener('ttc-careers:unauthorized', () => {
    useAuthStore.setState({ user: null })
  })
}
