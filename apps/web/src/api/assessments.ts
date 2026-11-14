import { API_PREFIX, api } from './client'
import type { Assessment, MatchResult } from '../types'

export async function createAssessment(
  candidateId: string,
  jobId: string,
): Promise<Assessment> {
  const response = await api.post(
    `${API_PREFIX}/candidates/${candidateId}/assessments`,
    { job_id: jobId },
  )
  return response.data as Assessment
}

export async function getAssessment(assessmentId: string): Promise<Assessment> {
  const response = await api.get(`${API_PREFIX}/assessments/${assessmentId}`)
  return response.data as Assessment
}

export async function downloadAssessment(assessmentId: string): Promise<void> {
  const response = await api.get(
    `${API_PREFIX}/assessments/${assessmentId}/export`,
    { responseType: 'blob' },
  )
  const blob = new Blob([response.data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `assessment-${assessmentId}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function reviseAssessment(
  assessmentId: string,
  payload: { note: string; dimensions: Record<string, string> },
): Promise<Assessment> {
  const response = await api.patch(
    `${API_PREFIX}/assessments/${assessmentId}`,
    payload,
  )
  return response.data as Assessment
}

export async function matchResume(
  resumeId: string,
  payload: { job_id: string; explain?: boolean; top_k?: number },
): Promise<MatchResult> {
  const response = await api.post(
    `${API_PREFIX}/resumes/${resumeId}/match`,
    payload,
    { timeout: 180_000 },
  )
  return response.data as MatchResult
}
