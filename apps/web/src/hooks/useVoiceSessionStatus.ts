import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { openVoiceStatusSocket } from '../api/voice'
import type { VoiceSessionDetail, VoiceSessionStatus } from '../types'

const TERMINAL_STATES = new Set<VoiceSessionStatus>(['ended', 'failed', 'revoked'])
const NON_RETRYABLE_CLOSE_CODES = new Set([4401, 4403, 4404, 4409])

interface VoiceStatusEvent {
  type?: string
  state?: VoiceSessionStatus
}

/**
 * Keep an open session page synchronized while the candidate joins or ends
 * the call. The status socket only carries the small state payload; query
 * invalidation fetches the authoritative session and transcript records.
 */
export function useVoiceSessionStatus(sessionId: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!sessionId) return

    let disposed = false
    let terminal = false
    let lastState = ''
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let retry = 0

    const refresh = (state: VoiceSessionStatus) => {
      terminal = TERMINAL_STATES.has(state)
      if (state === lastState) return
      lastState = state

      queryClient.setQueryData<VoiceSessionDetail>(
        ['voiceSession', sessionId],
        (current) => (current ? { ...current, status: state } : current),
      )
      void queryClient.invalidateQueries({ queryKey: ['voiceSession', sessionId] })
      void queryClient.invalidateQueries({ queryKey: ['voiceSessions'] })
      void queryClient.invalidateQueries({ queryKey: ['voiceTurns', sessionId] })
      if (terminal) {
        void queryClient.invalidateQueries({ queryKey: ['voiceReport', sessionId] })
      }
    }

    const connect = () => {
      if (disposed || terminal) return
      socket = openVoiceStatusSocket(sessionId)
      socket.onmessage = (event) => {
        let payload: VoiceStatusEvent
        try {
          payload = JSON.parse(String(event.data)) as VoiceStatusEvent
        } catch {
          return
        }
        if (payload.type === 'state' && payload.state) {
          retry = 0
          refresh(payload.state)
        }
      }
      socket.onclose = (event) => {
        socket = null
        if (disposed || terminal || NON_RETRYABLE_CLOSE_CODES.has(event.code)) return
        const delay = Math.min(10_000, 1_000 * 2 ** retry)
        retry += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      disposed = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close(1000)
      socket = null
    }
  }, [queryClient, sessionId])
}
