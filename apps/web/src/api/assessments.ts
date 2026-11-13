import { API_PREFIX, api } from './client'
import type { Assessment } from '../types'

const P = `${API_PREFIX}/assessments`

export async function createAssessment(
  candidateId: string,
  jobId: string,
): Promise<Assessment> {
  const response = await api.post(`${API_PREFIX}/candidates/${candidateId}/assessments`, {
    job_id: jobId,
  })
  return response.data as Assessment
}

export async function getAssessment(assessmentId: string): Promise<Assessment> {
  const response = await api.get(`${P}/${assessmentId}`)
  return response.data as Assessment
}

/** 导出接口需要 Authorization 头，所以走 blob 下载而不是裸链接。 */
export async function downloadAssessment(assessmentId: string): Promise<Blob> {
  const response = await api.get(`${P}/${assessmentId}/export`, { responseType: 'blob' })
  return response.data as Blob
}

export async function reviseAssessment(
  assessmentId: string,
  body: { note: string; dimensions: Record<string, string> },
): Promise<Assessment> {
  const response = await api.patch(`${P}/${assessmentId}`, body)
  return response.data as Assessment
}
