import { create } from 'zustand'
import type { SessionUser } from '../api/auth'

interface AuthState {
  user: SessionUser | null
  status: 'idle' | 'loading' | 'ready' | 'anonymous'
  setUser: (user: SessionUser) => void
  setStatus: (status: AuthState['status']) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  status: 'idle',
  setUser: (user) => set({ user, status: 'ready' }),
  setStatus: (status) => set({ status }),
  clear: () => set({ user: null, status: 'anonymous' }),
}))
