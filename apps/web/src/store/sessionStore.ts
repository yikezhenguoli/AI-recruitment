import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface ScreeningSessionSnapshot {
  sessionId: string
  jobName?: string
  jobRoleTitle?: string
  totalFiles: number
  startedAt: string
}

interface SessionState {
  session: ScreeningSessionSnapshot | null
  setSession: (session: ScreeningSessionSnapshot) => void
  clearSession: () => void
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      session: null,
      setSession: (session) => set({ session }),
      clearSession: () => set({ session: null }),
    }),
    { name: 'ttc-screening-session' },
  ),
)
