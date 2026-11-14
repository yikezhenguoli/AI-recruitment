import { API_PREFIX, api } from './client'
import type { EvidenceItem, EvidenceSearchResult } from '../types'

export async function searchEvidence(
  candidateId: string,
  payload?: { claim_ids?: string[]; sources?: string[]; max_per_entity?: number },
): Promise<EvidenceSearchResult> {
  const response = await api.post(
    `${API_PREFIX}/candidates/${candidateId}/evidence-search`,
    {
      claim_ids: [],
      sources: ['crossref'],
      max_per_entity: 5,
      ...payload,
    },
  )
  return response.data as EvidenceSearchResult
}

export async function listEvidence(candidateId: string): Promise<EvidenceItem[]> {
  const response = await api.get(`${API_PREFIX}/candidates/${candidateId}/evidence`)
  return response.data.items as EvidenceItem[]
}

export async function getEvidence(evidenceId: string): Promise<EvidenceItem> {
  const response = await api.get(`${API_PREFIX}/evidence/${evidenceId}`)
  return response.data as EvidenceItem
}

export async function confirmEvidence(evidenceId: string): Promise<void> {
  await api.post(`${API_PREFIX}/evidence/${evidenceId}/confirm`)
}
