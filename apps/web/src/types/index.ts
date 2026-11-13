export interface HealthResponse {
  status: string
  database?: string
}

export type JobStatus = 'draft' | 'published' | 'locked' | 'archived'

export interface JobSummary {
  id: string
  title: string
  department: string | null
  status: JobStatus
  headcount: number | null
  current_version_id: string | null
  created_at: string
  updated_at: string
}

export interface JDVersion {
  id: string
  version_no: number
  jd_text: string
  structured: Record<string, unknown>
  source: string
  is_saved?: boolean
  created_at?: string
}

export interface JobDetail extends JobSummary {
  owner_id?: string
  tenant_id?: string
  published_at?: string | null
  archived_at?: string | null
  current_version: JDVersion | null
}

export interface WeightDimension {
  key: string
  label: string
  weight_pct: number
  description?: string | null
}

export interface WeightPlan {
  id: string
  name: string
  mode: 'auto' | 'template' | 'custom'
  dimensions: WeightDimension[]
  created_at?: string
}

export interface JobStats {
  candidates: number
  assessments: number
  voice_sessions: number
}

export interface CandidateSummary {
  id: string
  display_name: string
  job_id: string | null
  source: string
  is_synthetic: boolean
  created_at: string
}

export interface ResumeSummary {
  id: string
  file_name: string
  parse_status: string
  created_at: string
}

export interface ResumeVersionInfo {
  id: string
  version_no: number
  status: string
  error?: string | null
}

export interface ResumeClaim {
  id: string
  type: string
  ordinal: number
  raw_text: string
  normalized: Record<string, unknown>
  page_no: number | null
  char_start: number | null
  char_end: number | null
  confidence: number | null
  needs_review: boolean
}

export interface ResumeClaimsResponse {
  resume_id: string
  version: number | null
  status?: string
  claims: ResumeClaim[]
}

export interface TimelineEntry {
  organization?: string | null
  role?: string | null
  start?: string | null
  end?: string | null
  overlaps?: unknown[]
}

export type EvidenceGrade = 'A' | 'B' | 'C' | 'D'

export interface EvidenceItem {
  id: string
  claim_id: string
  entity_id: string | null
  source_name: string
  source_url: string | null
  title: string | null
  snippet: string | null
  grade: EvidenceGrade
  match_method: string | null
  match_confidence: number | null
  accessed_at: string
  verified_by?: string | null
}

export type ConsentPurpose = 'resume_process' | 'voice_interview' | 'recording' | 'model_training'

export interface ConsentItem {
  id: string
  candidate_id: string
  display_name: string
  purpose: ConsentPurpose
  status: 'granted' | 'revoked'
  accepted_at: string | null
  revoked_at: string | null
  expires_at: string | null
}

export interface AssessmentDimension {
  key: string
  label: string
  weight_pct: number
  score: number | null
  evidence_state: 'strong' | 'partial' | 'self_claim' | 'missing'
  evidence_ids: string[]
  source_claim_ids: string[]
  reasoning: string
  status?: string
}

export interface AssessmentReport {
  meta?: { assessed_at?: string; model_version?: string }
  evidence_ledger?: {
    score: number
    grade: EvidenceGrade
    coverage: { supported: number; verifiable: number }
    breakdown: Record<string, number>
  }
  match_ledger?: { score: number | null; dimensions: AssessmentDimension[] }
  limitations?: string[]
  human_review?: { status: string }
}

export interface Assessment {
  id: string
  candidate_id: string
  job_id: string
  status: string
  report: AssessmentReport
}

export type VoiceSessionStatus =
  | 'created'
  | 'live'
  | 'ended'
  | 'failed'
  | 'revoked'
  | 'connecting'

export interface VoiceSessionSummary {
  id: string
  candidate_id: string
  candidate_name: string
  job_id: string | null
  job_title: string | null
  scenario: string
  status: VoiceSessionStatus
  provider: string
  model: string
  max_seconds: number
  created_at: string
  started_at: string | null
  ended_at: string | null
  end_reason: string | null
  has_report: boolean
}

export interface VoiceSessionDetail {
  id: string
  candidate_id: string
  job_id: string
  scenario: string
  status: VoiceSessionStatus
  provider: string
  max_seconds: number
  plan_json: {
    questions?: { id: string; section: string; text: string }[]
    sections_order?: string[]
    language_mode?: { primary: string; mixed: boolean }
  }
  created_at: string
  started_at: string | null
  ended_at: string | null
  end_reason: string | null
}

export interface VoiceTurn {
  id: string
  turn_index: number
  role: 'interviewer' | 'candidate' | 'system'
  text: string
  question_id: string | null
  started_at: string
}

export interface CallReportQuote {
  turn_id: string
  question_id: string | null
  text: string
}

export interface CallReport {
  session: { id: string; scenario: string; status: string; provider: string }
  status: string
  summary: {
    status?: string
    turn_count?: number
    overview?: string | null
    qa?: { question: string; answer_summary: string }[]
    limitations?: string[]
  }
  dimensions: unknown[]
  quotes: CallReportQuote[]
  crosscheck: Record<string, unknown>
  followups: string[]
  model_version: string
}

/** HR 端沟通纪要：/voice-sessions/{id}/summary。 */
export interface VoiceSummary {
  session_id: string
  candidate_id: string
  scenario: string
  session_status: string
  report_status: string
  model_version: string
  generated_at: string
  turn_count: number
  overview: string | null
  qa: { question: string; answer_summary: string }[]
  followups: string[]
  limitations: string[]
}

export interface DataSource {
  id: string | null
  name: string
  enabled: boolean
  rate_limit: number
}

export interface AuditLogItem {
  id: number
  actor_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  request_id: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

export interface AdminMetrics {
  tasks: Record<string, number>
  scope: string
}

export interface IntegrationsStatus {
  openats: { configured: boolean; status: string }
  vekt: { configured: boolean; status: string; fallback?: string }
}

/** 后端 /api/v1/ws/progress/{task_id} 推送的消息形状。 */
export interface TaskProgressMessage {
  type: 'progress' | 'done' | 'error'
  task_id: string
  stage: string
  resource_id: string
  attempts: number
  message: string | null
}
