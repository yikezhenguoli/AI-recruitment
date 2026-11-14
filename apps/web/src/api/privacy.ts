import { API_PREFIX, api } from './client'

export interface ConsentRecord {
  id: string
  candidate_id: string
  purpose: string
  status: string
  scope: Record<string, unknown>
  text_version: string
  accepted_at: string
}

export async function createConsent(payload: {
  candidate_id: string
  purpose: 'resume_process' | 'voice_interview' | 'recording' | 'model_training'
  scope?: Record<string, unknown>
  text_version: string
  acknowledged: boolean
}): Promise<ConsentRecord> {
  const response = await api.post(`${API_PREFIX}/consents`, {
    ...payload,
    scope: payload.scope ?? {},
  })
  return response.data as ConsentRecord
}

export async function revokeConsent(consentId: string): Promise<void> {
  await api.post(`${API_PREFIX}/consents/${consentId}/revoke`)
}

export async function requestPrivacy(payload: {
  request_type: 'export' | 'delete' | 'rectify'
  scope: Record<string, unknown>
  reason?: string
}): Promise<{ id: string; status: string }> {
  const response = await api.post(`${API_PREFIX}/privacy/requests`, payload)
  return response.data
}

export async function getPrivacyRequest(
  requestId: string,
): Promise<Record<string, unknown>> {
  const response = await api.get(`${API_PREFIX}/privacy/requests/${requestId}`)
  return response.data
}

export async function processPrivacyRequest(
  requestId: string,
  decision: 'approved' | 'rejected',
): Promise<void> {
  await api.post(`${API_PREFIX}/admin/privacy/requests/${requestId}/process`, {
    decision,
  })
}
