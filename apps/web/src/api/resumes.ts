import { API_PREFIX, api } from './client'
import type {
  ClaimsResponse,
  ResumeSummary,
  TimelineResponse,
  UploadedResume,
} from '../types'

const MIME_BY_EXT: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  txt: 'text/plain',
}

function normalizeMime(file: File): File {
  const ext = file.name.toLowerCase().split('.').pop() || ''
  const mime = MIME_BY_EXT[ext]
  // 后端会校验声明 MIME 与扩展名一致；部分 Windows 浏览器返回空或
  // application/octet-stream，这里按扩展名归一化。
  if (!mime || file.type === mime) return file
  return new File([file], file.name, { type: mime })
}

export async function uploadResume(
  candidateId: string,
  jobId: string | null,
  file: File,
): Promise<UploadedResume> {
  const form = new FormData()
  form.append('candidate_id', candidateId)
  if (jobId) form.append('job_id', jobId)
  form.append('file', normalizeMime(file))

  // 浏览器会自动补 multipart boundary；不要手写 Content-Type。
  const response = await api.post(`${API_PREFIX}/resumes`, form, {
    timeout: 180_000,
  })
  return response.data as UploadedResume
}

export async function getResume(resumeId: string): Promise<ResumeSummary> {
  const response = await api.get(`${API_PREFIX}/resumes/${resumeId}`)
  return response.data as ResumeSummary
}

export async function getResumeClaims(resumeId: string): Promise<ClaimsResponse> {
  const response = await api.get(`${API_PREFIX}/resumes/${resumeId}/claims`)
  return response.data as ClaimsResponse
}

export async function getResumeTimeline(resumeId: string): Promise<TimelineResponse> {
  const response = await api.get(`${API_PREFIX}/resumes/${resumeId}/timeline`)
  return response.data as TimelineResponse
}

export async function reparseResume(resumeId: string): Promise<{
  task_id: string
  parse_status: string
}> {
  const response = await api.post(`${API_PREFIX}/resumes/${resumeId}/reparse`)
  return response.data
}

export async function deleteResume(resumeId: string): Promise<void> {
  await api.delete(`${API_PREFIX}/resumes/${resumeId}`)
}
