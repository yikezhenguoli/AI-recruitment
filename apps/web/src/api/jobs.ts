import { API_PREFIX, api } from './client'
import type {
  InterviewPlan,
  JdGenerationResult,
  JdStructured,
  JdWarning,
  JobDetail,
  JobStats,
  JobStatus,
  JobSummary,
  JobVersion,
  WeightDimension,
  WeightTemplate,
} from '../types'

export async function listJobs(params?: {
  status?: JobStatus
  department?: string
  limit?: number
}): Promise<JobSummary[]> {
  const response = await api.get(`${API_PREFIX}/jobs`, { params })
  return response.data.items as JobSummary[]
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const response = await api.get(`${API_PREFIX}/jobs/${jobId}`)
  return response.data as JobDetail
}

export async function createJob(payload: {
  title: string
  department?: string | null
  headcount?: number | null
  jd_text?: string | null
}): Promise<{ id: string; title: string; status: JobStatus }> {
  const response = await api.post(`${API_PREFIX}/jobs`, payload)
  return response.data
}

export async function patchJob(
  jobId: string,
  payload: { title?: string; department?: string | null; headcount?: number | null },
  updatedAt: string,
): Promise<void> {
  await api.patch(`${API_PREFIX}/jobs/${jobId}`, payload, {
    headers: { 'If-Match': updatedAt },
  })
}

export async function archiveJob(jobId: string): Promise<void> {
  await api.delete(`${API_PREFIX}/jobs/${jobId}`)
}

export async function listJobVersions(jobId: string): Promise<JobVersion[]> {
  const response = await api.get(`${API_PREFIX}/jobs/${jobId}/jd/versions`)
  return response.data.items as JobVersion[]
}

export async function extractJd(
  jobId: string,
  jdText: string,
): Promise<{ structured: JdStructured; warnings: JdWarning[] }> {
  const response = await api.post(`${API_PREFIX}/jobs/${jobId}/jd/extract`, {
    jd_text: jdText,
  })
  return response.data
}

export async function generateJd(
  jobId: string,
  payload: { prompt: string; polish_first?: boolean; variants?: number },
): Promise<JdGenerationResult> {
  const response = await api.post(`${API_PREFIX}/jobs/${jobId}/jd/generate`, payload)
  return response.data as JdGenerationResult
}

export async function createJdVersion(
  jobId: string,
  payload: { jd_text: string; structured: JdStructured },
): Promise<JobVersion> {
  const response = await api.post(`${API_PREFIX}/jobs/${jobId}/jd/versions`, payload)
  return response.data as JobVersion
}

export async function selectJdVersion(
  jobId: string,
  versionId: string,
): Promise<void> {
  await api.post(`${API_PREFIX}/jobs/${jobId}/jd/versions/${versionId}/select`)
}

export async function publishJob(jobId: string): Promise<void> {
  await api.post(`${API_PREFIX}/jobs/${jobId}/publish`)
}

export async function getJobStats(jobId: string): Promise<JobStats> {
  const response = await api.get(`${API_PREFIX}/jobs/${jobId}/stats`)
  return response.data as JobStats
}

export async function listWeightTemplates(): Promise<WeightTemplate[]> {
  const response = await api.get(`${API_PREFIX}/weight-plans/templates`)
  return response.data.items as WeightTemplate[]
}

export async function setWeightPlan(
  jobId: string,
  payload: {
    name: string
    mode: 'auto' | 'template' | 'custom'
    dimensions: WeightDimension[]
  },
): Promise<void> {
  await api.put(`${API_PREFIX}/jobs/${jobId}/weight-plan`, payload)
}

export async function listInterviewPlans(jobId: string): Promise<InterviewPlan[]> {
  const response = await api.get(`${API_PREFIX}/jobs/${jobId}/interview-plans`)
  return response.data.items as InterviewPlan[]
}
