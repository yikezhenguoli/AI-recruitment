import { API_BASE, api } from './client'

export async function processResumes(
  jdText: string,
  files: File[],
  scoringSchema?: unknown,
  graduationFilter?: unknown,
): Promise<{ session_id: string; total_files: number; message: string }> {
  const form = new FormData()
  form.append('jd_text', jdText)
  if (scoringSchema) form.append('scoring_schema_json', JSON.stringify(scoringSchema))
  if (graduationFilter) form.append('graduation_filter_json', JSON.stringify(graduationFilter))
  files.forEach((file) => form.append('files', file))

  // Let the browser/Axios set the multipart boundary.
  const response = await api.post('/api/resumes/process', form)
  return response.data
}

export function getResumePreviewUrl(sessionId: string, candidateId: string): string {
  return `${API_BASE}/api/resumes/preview-file/${sessionId}/${candidateId}`
}

export async function closeResumeSession(sessionId: string): Promise<void> {
  await api.delete(`/api/resumes/session/${sessionId}`)
}
