import { API_PREFIX, api } from './client'
import type {
  CallReport,
  CreateVoiceSessionResult,
  VoiceScenario,
  VoiceSession,
  VoiceTurnInput,
} from '../types'

export async function createVoiceSession(payload: {
  candidate_id: string
  job_id: string
  scenario: VoiceScenario
  provider?: 'qwen_realtime'
  max_seconds?: number
}): Promise<CreateVoiceSessionResult> {
  const response = await api.post(`${API_PREFIX}/voice-sessions`, {
    provider: 'qwen_realtime',
    max_seconds: 600,
    ...payload,
  })
  return response.data as CreateVoiceSessionResult
}

export async function getVoiceSession(sessionId: string): Promise<VoiceSession> {
  const response = await api.get(`${API_PREFIX}/voice-sessions/${sessionId}`)
  return response.data as VoiceSession
}

export async function finishVoiceSession(
  sessionId: string,
  payload: {
    reason: 'completed' | 'timeout' | 'candidate_end'
    turns: VoiceTurnInput[]
  },
): Promise<{ report_id: string; status: string; completed_at: string }> {
  const response = await api.post(
    `${API_PREFIX}/voice-sessions/${sessionId}/finish`,
    payload,
  )
  return response.data
}

export async function addVoiceTurns(
  sessionId: string,
  turns: VoiceTurnInput[],
): Promise<void> {
  await api.post(`${API_PREFIX}/voice-sessions/${sessionId}/turns`, turns)
}

export async function getVoiceReport(sessionId: string): Promise<CallReport> {
  const response = await api.get(`${API_PREFIX}/voice-sessions/${sessionId}/report`)
  return response.data as CallReport
}
