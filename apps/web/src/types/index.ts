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
  extractor_model?: string | null
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
  is_paused: boolean
  conduct_score: number | null
  conduct_status: 'assessed' | 'unassessed' | 'vetoed' | null
  conduct_veto: boolean
  capability_score: number | null
  capability_status: CapabilityStatus | null
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
    questions?: {
      id: string
      section: string
      text: string
      focus?: string
      job_relevance?: string
      resume_anchor?: string
      source?: 'hr' | 'ai'
      required?: boolean
    }[]
    sections_order?: string[]
    language_mode?: { primary: string; mixed: boolean }
    strategy?: string
  }
  created_at: string
  started_at: string | null
  ended_at: string | null
  end_reason: string | null
  is_paused: boolean
}

export interface VoiceTurn {
  id: string
  turn_index: number
  role: 'interviewer' | 'candidate' | 'hr' | 'system'
  text: string
  question_id: string | null
  started_at: string
}

export interface CallReportQuote {
  turn_id: string
  question_id: string | null
  text: string
}

export type ConductStatus = 'assessed' | 'unassessed' | 'vetoed'

export interface ConductEvidenceQuote {
  turn_id: string
  text: string
}

export interface ConductDimension {
  key: string
  label: string
  weight_pct: number
  score: number | null
  reason: string
  evidence_turn_ids: string[]
}

export interface ConductIncident {
  category: 'disruption' | 'intentional_non_answer' | 'hostility' | 'inappropriate_speech'
  category_label: string
  severity: 'minor' | 'moderate' | 'severe'
  description: string
  evidence_turn_ids: string[]
  quotes: ConductEvidenceQuote[]
  source: 'model' | 'rule'
}

export interface CandidateConductAssessment {
  status: ConductStatus
  score: number | null
  veto: boolean
  review_required: boolean
  summary: string
  dimensions: ConductDimension[]
  incidents: ConductIncident[]
  veto_reasons: string[]
  limitations: string[]
}

export type CapabilityStatus = 'assessed' | 'unassessed'

export interface CapabilityDimension {
  key: string
  label: string
  weight_pct: number
  score: number | null
  reason: string
  evidence_turn_ids: string[]
}

export interface CapabilityEvidence {
  turn_id: string
  text: string
}

export interface CandidateCapabilityAssessment {
  status: CapabilityStatus
  score: number | null
  review_required: boolean
  summary: string
  dimensions: CapabilityDimension[]
  evidence: CapabilityEvidence[]
  evidence_coverage: {
    cited_turns: number
    candidate_turns: number
    ratio: number
  }
  strengths: string[]
  gaps: string[]
  verification_questions: string[]
  limitations: string[]
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
  conduct: CandidateConductAssessment
  conduct_status: ConductStatus
  conduct_score: number | null
  conduct_veto: boolean
  conduct_model_version: string | null
  capability: CandidateCapabilityAssessment
  capability_status: CapabilityStatus
  capability_score: number | null
  capability_model_version: string | null
  markdown_ready: boolean
  markdown_generated_at: string | null
  markdown_sha256: string | null
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
  conduct: CandidateConductAssessment
  conduct_status: ConductStatus
  conduct_score: number | null
  conduct_veto: boolean
  conduct_model_version: string | null
  capability: CandidateCapabilityAssessment
  capability_status: CapabilityStatus
  capability_score: number | null
  capability_model_version: string | null
  markdown_ready: boolean
  markdown_generated_at: string | null
  markdown_sha256: string | null
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

// ------------------------------------------------------------ Offer / 排期 / 人才库

export interface ApplicationItem {
  id: string
  status: string
  created_at: string
  updated_at: string
  candidate_id: string
  candidate_name: string
  source: string
  job_id: string
  job_title: string
  department: string | null
  match_score: number | null
  offer_id: string | null
  offer_status: OfferStatus | null
}

export type OfferStatus = 'draft' | 'sent' | 'accepted' | 'declined' | 'withdrawn' | 'expired'

export interface OfferSummary {
  id: string
  status: OfferStatus
  position_title: string
  salary_monthly: string | number | null
  salary_months: number | null
  start_date: string | null
  expires_at: string | null
  sent_at: string | null
  decided_at: string | null
  created_at: string
  updated_at: string
  candidate_id: string
  candidate_name: string
  job_id: string
  job_title: string
  application_id: string
}

export interface OfferEvent {
  id: string
  actor_id: string | null
  from_status: string | null
  to_status: string
  note: string | null
  created_at: string
}

export interface OfferDetail extends OfferSummary {
  events: OfferEvent[]
}

export type InterviewStatus =
  | 'scheduled'
  | 'confirmed'
  | 'completed'
  | 'canceled'
  | 'no_show'

export type InterviewMode = 'onsite' | 'video' | 'phone'

export interface InterviewSlot {
  id: string
  status: InterviewStatus
  scheduled_at: string
  duration_min: number
  mode: InterviewMode
  location: string | null
  note: string | null
  candidate_id: string
  candidate_name: string
  job_id: string
  job_title: string
  interviewer_id: string | null
  interviewer_name: string | null
  application_id: string | null
  created_at: string
  updated_at: string
}

export interface AvailabilityResult {
  interviewer_id: string
  date: string
  timezone: string
  duration_min: number
  slots: { start: string; end: string }[]
  note: string
}

export interface TalentHit {
  candidate_id: string
  display_name: string
  score: number
  backend: string
  model: string
  resume_version_id: string
  snippets?: string[]
}

export interface TalentSearchResult {
  query: string
  backend: string
  model: string
  indexed: number
  items: TalentHit[]
  warning?: string | null
  hint?: string
}

export interface TalentReindexResult {
  indexed: number
  scanned: number
  skipped: { candidate_id: string; reason: string }[]
  warnings: string[]
}

export type MemberRole = 'admin' | 'hr' | 'candidate' | 'guest'
export type MemberStatus = 'active' | 'disabled' | 'pending'

export interface MemberItem {
  id: string
  email: string
  display_name: string
  role: MemberRole
  status: MemberStatus
  last_login_at: string | null
  created_at: string
}

export interface PermissionMatrix {
  permissions: string[]
  matrix: Record<string, string[]>
}

export interface NotificationItem {
  id: string
  kind: string
  title: string
  body: string | null
  link: string | null
  read_at: string | null
  created_at: string
}

export interface NotificationList {
  items: NotificationItem[]
  unread: number
}

export interface BackupItem {
  id: string
  uri: string
  table_counts: Record<string, number>
  checksum: string
  size_bytes: number
  created_at: string
}

export interface BackupList {
  items: BackupItem[]
}

export interface BackupCreateResult extends BackupItem {
  note: string
}

export interface BackupVerifyResult {
  tenant_id: string
  tables: Record<string, { rows: number }>
  problems: string[]
  ok: boolean
  snapshot_id?: string
  checksum_ok?: boolean
}

export interface BackupRestoreResult extends BackupVerifyResult {
  applied: boolean
  written?: Record<string, number>
}
