import { API_PREFIX, api } from './client'
import type { EvidenceItem } from '../types'

const P = `${API_PREFIX}/evidence`

export async function listEvidence(candidateId: string): Promise<EvidenceItem[]> {
  const response = await api.get(`${API_PREFIX}/candidates/${candidateId}/evidence`)
  return response.data.items as EvidenceItem[]
}

export async function searchEvidence(
  candidateId: string,
  body?: { claim_ids?: string[]; sources?: string[]; max_per_entity?: number },
): Promise<{ task_id: string; entities: number; status: string }> {
  const response = await api.post(`${API_PREFIX}/candidates/${candidateId}/evidence-search`, {
    claim_ids: [],
    sources: ['crossref'],
    ...body,
  })
  return response.data
}

export async function confirmEvidence(
  evidenceId: string,
): Promise<{ id: string; confirmed_by: string; note: string }> {
  const response = await api.post(`${P}/${evidenceId}/confirm`)
  return response.data
}
