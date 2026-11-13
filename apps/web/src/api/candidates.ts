import { API_PREFIX, api } from './client'
import type { CandidateSummary, ResumeSummary } from '../types'

const P = `${API_PREFIX}/candidates`

export async function listCandidates(params?: {
  job_id?: string
  limit?: number
}): Promise<CandidateSummary[]> {
  const response = await api.get(P, { params })
  return response.data.items as CandidateSummary[]
}

export async function getCandidate(candidateId: string): Promise<CandidateSummary> {
  const response = await api.get(`${P}/${candidateId}`)
  return response.data as CandidateSummary
}

export async function createCandidate(body: {
  display_name: string
  job_id?: string | null
  source?: 'demo' | 'invite' | 'upload'
  is_synthetic?: boolean
}): Promise<CandidateSummary> {
  const response = await api.post(P, body)
  return response.data as CandidateSummary
}

export async function listCandidateResumes(candidateId: string): Promise<ResumeSummary[]> {
  const response = await api.get(`${P}/${candidateId}/resumes`)
  return response.data.items as ResumeSummary[]
}
