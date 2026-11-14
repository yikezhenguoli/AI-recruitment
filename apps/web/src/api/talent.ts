import { API_PREFIX, api } from './client'
import type { TalentHit, TalentReindexResult, TalentSearchResult } from '../types'

export async function reindexTalent(limit = 200): Promise<TalentReindexResult> {
  const response = await api.post(`${API_PREFIX}/talent/reindex`, null, { params: { limit } })
  return response.data as TalentReindexResult
}

export async function searchTalent(
  query: string,
  topK = 10,
): Promise<TalentSearchResult> {
  const response = await api.post(`${API_PREFIX}/talent/search`, { query, top_k: topK })
  return response.data as TalentSearchResult
}

export async function similarCandidates(candidateId: string, limit = 5): Promise<{
  candidate_id: string
  backend: string
  model: string
  items: TalentHit[]
}> {
  const response = await api.get(`${API_PREFIX}/talent/candidates/${candidateId}/similar`, {
    params: { limit },
  })
  return response.data
}
