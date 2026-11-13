import { api } from './client'
import type { CandidateDetailResponse, SessionResultsResponse } from '../types'

export async function getSessionResults(sessionId: string): Promise<SessionResultsResponse> {
  const response = await api.get(`/api/resumes/results/${sessionId}`)
  return response.data as SessionResultsResponse
}

export async function getCandidateDetail(
  sessionId: string,
  candidateId: string,
): Promise<CandidateDetailResponse> {
  const response = await api.get(`/api/resumes/detail/${sessionId}/${candidateId}`)
  return response.data as CandidateDetailResponse
}
