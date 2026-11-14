export type Role = 'admin' | 'hr' | 'candidate' | 'guest'

export interface Me {
  id: string
  tenant_id: string
  role: Role
  display_name: string
  email?: string
}

export interface Tokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface RegisterResponse extends Tokens {
  tenant_slug: string
  candidate_id: string
}

export interface Candidate {
  id: string
  tenant_id: string
  user_id: string
  display_name: string
  contact_masked: string | null
  source: string
  job_id: string | null
  is_synthetic: boolean
  created_at: string
}

export interface Consent {
  id: string
  purpose: ConsentPurpose
  status: 'granted' | 'revoked' | 'expired'
  accepted_at: string | null
  revoked_at: string | null
  expires_at: string | null
}

export type ConsentPurpose =
  | 'resume_process'
  | 'voice_interview'
  | 'recording'
  | 'model_training'

export interface PrivacyRequest {
  id: string
  request_type: 'access' | 'correct' | 'revoke' | 'delete'
  status: 'submitted' | 'processing' | 'completed' | 'rejected'
  payload: { reason?: string | null } | null
  result: Record<string, unknown> | null
  created_at: string
  completed_at: string | null
}

export interface ProfileResponse {
  account: {
    email: string
    display_name: string
    tenant_slug: string
    tenant_name: string
  }
  candidate: Candidate | null
  consents: Consent[]
  privacy_requests: PrivacyRequest[]
}

export interface JobCard {
  id: string
  title: string
  department: string | null
  headcount: number | null
  published_at: string | null
  summary: string
  skills: string[]
  applied: boolean
}

export interface JobDetail {
  id: string
  title: string
  department: string | null
  headcount: number | null
  published_at: string | null
  jd_text: string
  structured: Record<string, unknown>
  application_id: string | null
  has_profile: boolean
}

export interface ApplicationSummary {
  id: string
  status: string
  created_at: string
  updated_at: string
  job_id: string
  title: string
  department: string | null
  resume_id: string | null
  file_name: string | null
  parse_status: string | null
  match_score: number | null
  assessment_status: string | null
  interview_id: string | null
  interview_status: string | null
}

export interface MatchExplanation {
  status: string
  summary: string
  strengths: string[]
  gaps: string[]
  suggestions: string[]
  risk_notes: string[]
  reason: string | null
}

export interface AssessmentReport extends Partial<MatchExplanation> {
  explanation?: MatchExplanation
  meta?: Record<string, unknown>
  limitations?: string[]
  match_ledger?: Record<string, unknown>
}

export interface Assessment {
  id: string
  match_score: number | null
  evidence_score: number | null
  status: string
  report_json: AssessmentReport | null
  model_version: string | null
  updated_at: string
}

export interface DimensionScore {
  dimension_key: string
  label: string
  weight_pct: number
  score: number | null
  evidence_state: string
  reasoning: string
  status: string
}

export interface InterviewSummary {
  id: string
  status: string
  scenario: string
  created_at: string
  started_at: string | null
  ended_at: string | null
  end_reason: string | null
  max_seconds: number
  job_id: string
  title: string
  question_count: number
}

export interface ApplicationDetail {
  id: string
  status: string
  created_at: string
  updated_at: string
  candidate_id: string
  job_id: string
  title: string
  department: string | null
  published_at: string | null
  resume_id: string | null
  file_name: string | null
  parse_status: string | null
  size_bytes: number | null
  uploaded_at: string | null
  assessment: Assessment | null
  dimensions: DimensionScore[]
  interviews: Array<{
    id: string
    status: string
    scenario: string
    created_at: string
    started_at: string | null
    ended_at: string | null
    end_reason: string | null
  }>
}

export interface InterviewPlan {
  questions: Array<{ id: string; text: string; focus?: string }>
  [key: string]: unknown
}

export interface InterviewDetail {
  id: string
  job_id: string
  scenario: string
  status: string
  plan: InterviewPlan
  max_seconds: number
  created_at: string
  started_at: string | null
  ended_at: string | null
  end_reason: string | null
  live_ready: boolean
  live_transport: 'sdp' | 'relay' | null
}

export interface UploadResult {
  application_id: string
  resume_id: string
  task_id: string
  parse_status: string
  duplicate?: boolean
  checks?: Record<string, unknown>
}

export interface MatchResult {
  assessment_id: string
  match_score: number | null
  category: string
  confidence: number
  jd_match_score: number | null
  top_k: Array<{ code: string; score: number }>
  explanation: MatchExplanation
  model_version: string
}
