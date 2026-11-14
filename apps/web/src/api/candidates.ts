import { API_PREFIX, api } from './client'
import type { Candidate, ResumeSummary } from '../types'

export async function listCandidates(params?: {
  job_id?: string
  limit?: number
}): Promise<Candidate[]> {
  const response = await api.get(`${API_PREFIX}/candidates`, { params })
  return response.data.items as Candidate[]
}

export async function createCandidate(payload: {
  display_name: string
  job_id?: string | null
  source?: 'demo' | 'invite' | 'upload'
  is_synthetic?: boolean
}): Promise<Candidate> {
  const response = await api.post(`${API_PREFIX}/candidates`, {
    source: 'upload',
    is_synthetic: true,
    ...payload,
  })
  return response.data as Candidate
}

export async function getCandidate(candidateId: string): Promise<Candidate> {
  const response = await api.get(`${API_PREFIX}/candidates/${candidateId}`)
  return response.data as Candidate
}

export async function listCandidateResumes(
  candidateId: string,
): Promise<ResumeSummary[]> {
  const response = await api.get(`${API_PREFIX}/candidates/${candidateId}/resumes`)
  return response.data.items as ResumeSummary[]
}
