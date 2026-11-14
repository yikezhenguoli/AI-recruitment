import { API_PREFIX, api } from './client'
import type { ResumeClaimsResponse, ResumeSummary, ResumeVersionInfo } from '../types'

const P = `${API_PREFIX}/resumes`

export interface UploadResumeResult {
  resume_id: string
  task_id?: string
  parse_status: string
  duplicate?: boolean
}

export async function uploadResume(
  candidateId: string,
  file: File,
  jobId?: string | null,
): Promise<UploadResumeResult> {
  const form = new FormData()
  form.append('candidate_id', candidateId)
  if (jobId) form.append('job_id', jobId)
  form.append('file', file)
  const response = await api.post(P, form)
  return response.data as UploadResumeResult
}

export async function getResume(resumeId: string): Promise<ResumeSummary & { mime?: string }> {
  const response = await api.get(`${P}/${resumeId}`)
  return response.data
}

export async function getResumeClaims(resumeId: string): Promise<ResumeClaimsResponse> {
  const response = await api.get(`${P}/${resumeId}/claims`)
  return response.data as ResumeClaimsResponse
}

export interface ResumeText {
  version: number
  extractor_model: string | null
  text: string
}

export async function getResumeText(resumeId: string): Promise<ResumeText> {
  const response = await api.get(`${P}/${resumeId}/text`)
  return response.data as ResumeText
}

export async function getResumeTimeline(resumeId: string): Promise<{ items: unknown[] }> {
  const response = await api.get(`${P}/${resumeId}/timeline`)
  return response.data
}

export async function reparseResume(
  resumeId: string,
): Promise<{ task_id: string; parse_status: string }> {
  const response = await api.post(`${P}/${resumeId}/reparse`)
  return response.data
}

export async function deleteResume(resumeId: string): Promise<void> {
  await api.delete(`${P}/${resumeId}`)
}

export type { ResumeVersionInfo }
