import { API_PREFIX, api } from './client'
import { openAuthedSocket } from './ws'
import type {
  CallReport,
  VoiceSessionDetail,
  VoiceSessionStatus,
  VoiceSessionSummary,
  VoiceSummary,
  VoiceTurn,
} from '../types'

const P = `${API_PREFIX}/voice-sessions`

export async function listVoiceSessions(params?: {
  candidate_id?: string
  status?: VoiceSessionStatus
  limit?: number
}): Promise<VoiceSessionSummary[]> {
  const response = await api.get(P, { params })
  return response.data.items as VoiceSessionSummary[]
}

export async function getVoiceSession(sessionId: string): Promise<VoiceSessionDetail> {
  const response = await api.get(`${P}/${sessionId}`)
  return response.data as VoiceSessionDetail
}

export async function createVoiceSession(body: {
  candidate_id: string
  job_id: string
  scenario?: 'screen' | 'verify' | 'skill' | 'mock'
  max_seconds?: number
  custom_questions?: string[]
}): Promise<{
  id: string
  status: string
  consent_checked: boolean
  plan: VoiceSessionDetail['plan_json']
}> {
  const response = await api.post(P, body)
  return response.data
}

export async function listVoiceTurns(sessionId: string): Promise<VoiceTurn[]> {
  const response = await api.get(`${P}/${sessionId}/turns`)
  return response.data.items as VoiceTurn[]
}

export async function finishVoiceSession(
  sessionId: string,
  body: {
    reason?: 'completed' | 'timeout' | 'candidate_end'
    turns?: { index: number; role: 'interviewer' | 'candidate' | 'hr' | 'system'; text: string; question_id?: string | null }[]
  },
): Promise<{ report_id: string; status: string; completed_at: string }> {
  const response = await api.post(`${P}/${sessionId}/finish`, body)
  return response.data
}

export async function getVoiceReport(sessionId: string): Promise<CallReport> {
  const response = await api.get(`${P}/${sessionId}/report`)
  return response.data as CallReport
}

export async function controlVoiceInterview(
  sessionId: string,
  action: 'pause' | 'resume',
): Promise<{
  session_id: string
  status: string
  interview_paused: boolean
  ai_active: boolean
}> {
  const response = await api.post(`${P}/${sessionId}/flow-control`, { action })
  return response.data
}

/** HR 端沟通纪要（只含模型整理后的字段）。 */
export async function getVoiceSummary(sessionId: string): Promise<VoiceSummary> {
  const response = await api.get(`${P}/${sessionId}/summary`)
  return response.data as VoiceSummary
}

export async function regenerateVoiceReport(  sessionId: string,
): Promise<{ session_id: string; status: string; model_version: string }> {
  const response = await api.post(`${P}/${sessionId}/report/regenerate`)
  return response.data
}

/** 实时语音中转：连上后由调用方先等 open，再发首帧 token（openAuthedSocket 已代发）。 */
export function openRealtimeRelay(sessionId: string): WebSocket {
  return openAuthedSocket(`/voice-sessions/${sessionId}/realtime`)
}

/** 只推送会话状态变化（created/live/ended/revoked…）的轻量连接。 */
export function openVoiceStatusSocket(sessionId: string): WebSocket {
  return openAuthedSocket(`/ws/voice/${sessionId}`)
}
