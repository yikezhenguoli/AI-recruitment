import { API_PREFIX, api } from './client'
import type {
  JDVersion,
  JobDetail,
  JobStats,
  JobStatus,
  JobSummary,
  WeightPlan,
} from '../types'

const P = `${API_PREFIX}/jobs`

export async function listJobs(params?: {
  status?: JobStatus
  department?: string
  limit?: number
}): Promise<JobSummary[]> {
  const response = await api.get(P, { params })
  return response.data.items as JobSummary[]
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const response = await api.get(`${P}/${jobId}`)
  return response.data as JobDetail
}

export async function createJob(body: {
  title: string
  department?: string | null
  headcount?: number | null
  jd_text?: string | null
}): Promise<JobDetail> {
  const response = await api.post(P, body)
  return response.data as JobDetail
}

export async function patchJob(
  jobId: string,
  body: { title?: string; department?: string | null; headcount?: number | null },
  updatedAt: string,
): Promise<void> {
  await api.patch(`${P}/${jobId}`, body, { headers: { 'If-Match': `"${updatedAt}"` } })
}

export async function archiveJob(jobId: string): Promise<void> {
  await api.delete(`${P}/${jobId}`)
}

export async function listVersions(jobId: string): Promise<JDVersion[]> {
  const response = await api.get(`${P}/${jobId}/jd/versions`)
  return response.data.items as JDVersion[]
}

export async function extractJD(jobId: string, jdText: string) {
  const response = await api.post(`${P}/${jobId}/jd/extract`, { jd_text: jdText })
  return response.data as { structured: Record<string, unknown>; warnings: unknown[] }
}

export async function generateJD(
  jobId: string,
  body: { prompt: string; polish_first?: boolean; variants?: number },
): Promise<{ generation_id: string | null; versions: JDVersion[]; suggestions?: string[] }> {
  const response = await api.post(`${P}/${jobId}/jd/generate`, body)
  return response.data
}

export async function createVersion(
  jobId: string,
  body: { jd_text: string; structured: Record<string, unknown> },
): Promise<JDVersion> {
  const response = await api.post(`${P}/${jobId}/jd/versions`, body)
  return response.data as JDVersion
}

export async function selectVersion(jobId: string, versionId: string): Promise<void> {
  await api.post(`${P}/${jobId}/jd/versions/${versionId}/select`)
}

export async function publishJob(jobId: string): Promise<void> {
  await api.post(`${P}/${jobId}/publish`)
}

export async function getJobStats(jobId: string): Promise<JobStats> {
  const response = await api.get(`${P}/${jobId}/stats`)
  return response.data as JobStats
}

export async function getWeightPlan(jobId: string): Promise<WeightPlan | null> {
  const response = await api.get(`${P}/${jobId}/weight-plan`)
  return (response.data.plan ?? null) as WeightPlan | null
}

export async function setWeightPlan(
  jobId: string,
  body: { name: string; mode: 'auto' | 'template' | 'custom'; dimensions: unknown[] },
): Promise<WeightPlan> {
  const response = await api.put(`${P}/${jobId}/weight-plan`, body)
  return response.data as WeightPlan
}

export interface InterviewPlan {
  id: string
  name: string
  duration_min: number | null
  rounds: number | null
  dimensions: unknown
}

export async function listInterviewPlans(jobId: string): Promise<InterviewPlan[]> {
  const response = await api.get(`${P}/${jobId}/interview-plans`)
  return response.data.items as InterviewPlan[]
}
