import { api } from './client'
import type {
  ApplicationDetail,
  ApplicationSummary,
  Candidate,
  Consent,
  ConsentPurpose,
  InterviewDetail,
  InterviewSummary,
  JobCard,
  JobDetail,
  MatchResult,
  PrivacyRequest,
  ProfileResponse,
  UploadResult,
} from './types'

export async function getProfile(): Promise<ProfileResponse> {
  const response = await api.get<ProfileResponse>('/portal/profile')
  return response.data
}

export async function saveProfile(displayName: string): Promise<Candidate> {
  const response = await api.post<Candidate>('/portal/profile', { display_name: displayName })
  return response.data
}

export async function getJobs(): Promise<JobCard[]> {
  const response = await api.get<{ items: JobCard[] }>('/portal/jobs')
  return response.data.items
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const response = await api.get<JobDetail>(`/portal/jobs/${jobId}`)
  return response.data
}

export async function createApplication(
  jobId: string,
  file: File,
  acknowledged: boolean,
  onProgress?: (percent: number) => void,
): Promise<UploadResult> {
  const form = new FormData()
  form.append('job_id', jobId)
  form.append('acknowledged', String(acknowledged))
  form.append('consent_version', 'portal-v1')
  form.append('file', file)
  const response = await api.post<UploadResult>('/portal/applications', form, {
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return
      onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return response.data
}

export async function getApplications(): Promise<ApplicationSummary[]> {
  const response = await api.get<{ items: ApplicationSummary[] }>('/portal/applications')
  return response.data.items
}

export async function getApplication(applicationId: string): Promise<ApplicationDetail> {
  const response = await api.get<ApplicationDetail>(`/portal/applications/${applicationId}`)
  return response.data
}

export async function runMatch(applicationId: string): Promise<MatchResult> {
  const response = await api.post<MatchResult>(
    `/portal/applications/${applicationId}/match`,
    undefined,
    { timeout: 180_000 },
  )
  return response.data
}

export async function getInterviews(): Promise<InterviewSummary[]> {
  const response = await api.get<{ items: InterviewSummary[] }>('/portal/interviews')
  return response.data.items
}

export async function getInterview(sessionId: string): Promise<InterviewDetail> {
  const response = await api.get<InterviewDetail>(`/portal/interviews/${sessionId}`)
  return response.data
}

export interface InterviewTurn {
  index: number
  role: 'interviewer' | 'candidate' | 'system'
  text: string
}

export async function finishInterview(
  sessionId: string,
  turns: InterviewTurn[],
): Promise<{ report_id: string; status: string }> {
  const response = await api.post<{ report_id: string; status: string }>(
    `/voice-sessions/${sessionId}/finish`,
    { reason: 'candidate_end', turns },
  )
  return response.data
}

export async function listConsents(): Promise<Consent[]> {
  const response = await api.get<{ items: Consent[] }>('/consents')
  return response.data.items
}

export async function grantConsent(
  candidateId: string,
  purpose: ConsentPurpose,
): Promise<Consent> {
  const response = await api.post<Consent>('/consents', {
    candidate_id: candidateId,
    purpose,
    scope: {},
    text_version: 'portal-v1',
    acknowledged: true,
  })
  return response.data
}

export async function revokeConsent(consentId: string): Promise<void> {
  await api.post(`/consents/${consentId}/revoke`)
}

export async function createPrivacyRequest(
  candidateId: string,
  requestType: PrivacyRequest['request_type'],
  reason: string,
): Promise<{ id: string; status: string; sla_hours: number }> {
  const response = await api.post('/privacy/requests', {
    candidate_id: candidateId,
    request_type: requestType,
    reason: reason.trim() || null,
  })
  return response.data
}
