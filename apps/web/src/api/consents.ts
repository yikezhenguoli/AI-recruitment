import { API_PREFIX, api } from './client'
import type { ConsentItem, ConsentPurpose } from '../types'

export async function listConsents(candidateId: string): Promise<ConsentItem[]> {
  const response = await api.get(`${API_PREFIX}/consents`, { params: { candidate_id: candidateId } })
  return response.data.items as ConsentItem[]
}

/**
 * 授权只能由候选人本人授予/撤回；招聘端只读取状态。
 * 这里保留封装是为了让候选人门户复用同一模块。
 */
export async function grantConsent(body: {
  candidate_id: string
  purpose: ConsentPurpose
  text_version: string
  acknowledged: boolean
  scope?: Record<string, unknown>
}): Promise<ConsentItem> {
  const response = await api.post(`${API_PREFIX}/consents`, body)
  return response.data as ConsentItem
}

export async function revokeConsent(consentId: string): Promise<void> {
  await api.post(`${API_PREFIX}/consents/${consentId}/revoke`)
}
