import { api } from './client'
import type {
  JDStructured,
  SavedJobProfile,
  SavedJobSummary,
  ScoringSchema,
} from '../types'

export async function parseJD(jdText: string): Promise<{
  jd_id: string
  structured: JDStructured
  scoring_schema: ScoringSchema
}> {
  const response = await api.post('/api/jobs/parse', { jd_text: jdText })
  return response.data
}

export async function listSavedJobs(): Promise<SavedJobSummary[]> {
  const response = await api.get('/api/jobs/saved')
  return response.data.jobs as SavedJobSummary[]
}

export async function getSavedJob(name: string): Promise<SavedJobProfile> {
  const response = await api.get(`/api/jobs/saved/${encodeURIComponent(name)}`)
  return response.data.job as SavedJobProfile
}

export async function saveJobProfile(payload: {
  name: string
  jd_text: string
  structured: JDStructured
  scoring_schema: ScoringSchema
}): Promise<SavedJobProfile> {
  const response = await api.post('/api/jobs/saved', payload)
  return response.data.job as SavedJobProfile
}
