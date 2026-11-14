/**
 * TTC `/api/v1` 契约类型。
 *
 * 所有字段保持后端返回的 snake_case 原样，避免前端再维护一套映射；
 * 可选字段按“后端可能不返回”处理，UI 负责显示「未提供」。
 */

export type Role = 'admin' | 'hr' | 'candidate'

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUser {
  id: string
  tenant_id: string
  role: Role
  display_name: string
}

export interface HealthStatus {
  status: string
  database?: string
}

/* ────────────────────────────── 岗位 / JD ────────────────────────────── */

export type JobStatus = 'draft' | 'published' | 'locked' | 'archived'

export interface JdStructured {
  role_title?: string
  responsibilities?: string[]
  required_skills?: string[]
  preferred_skills?: string[]
  seniority_level?: string
  min_years_experience?: number
  preferred_years_experience?: number
  education_requirements?: {
    level?: string
    field?: string
    required?: boolean
  }
  keywords?: string[]
  [key: string]: unknown
}

export interface JdWarning {
  field?: string
  message?: string
  [key: string]: unknown
}

export interface JobVersion {
  id: string
  version_no: number
  jd_text: string
  structured: JdStructured
  source: string
  is_saved?: boolean
  created_at?: string
}

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

export interface JobDetail extends JobSummary {
  tenant_id: string
  owner_id: string
  published_at?: string | null
  archived_at?: string | null
  current_version: JobVersion | null
}

export interface JobStats {
  candidates: number
  assessments: number
  voice_sessions: number
}

export interface WeightDimension {
  key: string
  label: string
  weight_pct: number
  description?: string | null
}

export interface WeightTemplate {
  name: string
  mode: string
  dimensions: WeightDimension[]
}

export interface InterviewPlan {
  id: string
  name: string
  duration_min: number
  rounds: number
  dimensions: unknown
}

export interface GeneratedJobVersion {
  id: string
  version_no: number
  jd_text: string
  structured: JdStructured
  source: string
  is_saved: boolean
}

export interface JdGenerationResult {
  generation_id: string | null
  versions: GeneratedJobVersion[]
  suggestions?: string[]
}

/* ────────────────────────────── 候选人 / 简历 ────────────────────────────── */

export type CandidateSource = 'demo' | 'invite' | 'upload'

export interface Candidate {
  id: string
  tenant_id?: string
  user_id?: string | null
  display_name: string
  contact_masked?: string | null
  source: CandidateSource
  job_id: string | null
  is_synthetic: boolean
  created_at: string
}

export type ParseStatus = 'queued' | 'parsing' | 'done' | 'failed'

export interface ResumeSummary {
  id: string
  candidate_id?: string
  file_name: string
  mime?: string
  size_bytes?: number
  parse_status: ParseStatus
  page_count?: number | null
  created_at: string
}

export interface UploadedResume {
  resume_id: string
  task_id: string
  parse_status: ParseStatus
  duplicate?: boolean
  checks?: {
    mime_ok: boolean
    size_ok: boolean
    hash: string
  }
}

export type ClaimType =
  | 'education'
  | 'work'
  | 'project'
  | 'publication'
  | 'patent'
  | 'award'
  | 'skill'
  | 'contact'
  | 'summary'

export interface ResumeClaim {
  id: string
  type: ClaimType
  ordinal: number
  raw_text: string
  normalized: Record<string, unknown>
  page_no: number | null
  char_start: number | null
  char_end: number | null
  confidence: number
  needs_review: boolean
}

export interface ClaimsResponse {
  resume_id: string
  version: number | null
  status?: ParseStatus
  claims: ResumeClaim[]
}

export interface TimelineItem {
  claim_id?: string
  type?: string
  kind?: string
  title?: string
  start?: string | null
  end?: string | null
  needs_review?: boolean
  raw?: string
  [key: string]: unknown
}

export interface TimelineConflict {
  type: string
  claim_ids: string[]
  start_month?: number
  end_month?: number
  note?: string
}

export interface TimelineResponse {
  items: TimelineItem[]
  conflicts: TimelineConflict[]
  gaps: TimelineConflict[]
}

/* ────────────────────────────── 评估 / 匹配 ────────────────────────────── */

export type EvidenceState =
  | 'strong'
  | 'partial'
  | 'self_claim'
  | 'missing'

export interface AssessmentDimension {
  key: string
  label: string
  weight_pct: number
  score: number | null
  evidence_state: EvidenceState
  evidence_ids?: string[]
  source_claim_ids?: string[]
  reasoning: string
  status?: string
}

export interface MatchExplanation {
  status: string
  summary?: string | null
  strengths?: string[]
  gaps?: string[]
  suggestions?: string[]
  risk_notes?: string[]
  reason?: string | null
}

export interface AssessmentReport {
  meta?: {
    assessed_at?: string
    model_version?: string
    source?: string
    [key: string]: unknown
  }
  evidence_ledger?: {
    score?: number
    grade?: string
    coverage?: { supported?: number; verifiable?: number }
    breakdown?: Record<string, number>
  }
  match_ledger?: {
    score?: number | null
    category?: string
    confidence?: number
    top_k?: Array<{ code: string; score: number }>
    dimensions?: AssessmentDimension[]
  }
  explanation?: MatchExplanation
  limitations?: string[]
  human_review?: { status?: string }
  [key: string]: unknown
}

export interface Assessment {
  id: string
  candidate_id: string
  job_id: string
  status: string
  report: AssessmentReport
}

export interface MatchResult {
  assessment_id: string
  match_score: number
  category: string
  confidence: number
  jd_match_score?: number | null
  top_k: Array<{ code: string; score: number }>
  explanation: MatchExplanation
  model_version: string
  fallback_reason?: string | null
  created_at: string
}

/* ────────────────────────────── 证据 ────────────────────────────── */

export interface EvidenceItem {
  id: string
  claim_id: string
  entity_id?: string
  source_name: string
  source_url: string
  title: string
  snippet: string
  grade: string
  match_method?: string
  match_confidence?: number
  accessed_at: string
  verified_by?: string | null
}

export interface EvidenceSearchResult {
  task_id: string
  entities: number
  status: string
}

/* ────────────────────────────── 语音会话 ────────────────────────────── */

export type VoiceScenario = 'screen' | 'verify' | 'skill' | 'mock'
export type VoiceStatus =
  | 'created'
  | 'connecting'
  | 'live'
  | 'ended'
  | 'failed'
  | 'revoked'

export interface VoiceQuestion {
  id: string
  section: string
  text: string
}

export interface VoicePlan {
  sections_order?: string[]
  questions: VoiceQuestion[]
  language_mode?: { primary?: string; mixed?: boolean }
}

export interface VoiceSession {
  id: string
  candidate_id: string
  job_id: string
  scenario: VoiceScenario
  status: VoiceStatus
  provider: string
  max_seconds: number
  plan_json: VoicePlan | string
  created_at: string
  started_at?: string | null
  ended_at?: string | null
  end_reason?: string | null
}

export interface CreateVoiceSessionResult {
  id: string
  status: VoiceStatus
  consent_checked: boolean
  plan: VoicePlan
}

export interface VoiceTurnInput {
  index: number
  role: 'interviewer' | 'candidate' | 'system'
  text: string
  question_id?: string | null
}

export interface CallReport {
  session: {
    id: string
    scenario: VoiceScenario
    status: VoiceStatus
    provider: string
  }
  status: string
  summary: Record<string, unknown>
  dimensions: unknown
  quotes: Array<{
    turn_id: string
    question_id?: string | null
    text: string
  }>
  crosscheck: Record<string, unknown>
  followups: unknown
  model_version: string
}

/* ────────────────────────────── 进度 / 管理 ────────────────────────────── */

export type ProgressType = 'progress' | 'done' | 'error'

export interface TaskProgressEvent {
  type: ProgressType
  task_id: string
  stage: string
  resource_id: string
  attempts?: number
  message?: string | null
}

export interface DataSource {
  id: string | null
  name: string
  enabled: boolean
  rate_limit: number
}

export interface AuditLogItem {
  id: string
  actor_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  request_id: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

export interface TaskMetrics {
  tasks: Record<string, number>
  scope: string
}

export interface IntegrationStatus {
  openats: { configured: boolean; status: string }
  vekt: { configured: boolean; status: string; fallback?: string }
}

/* ────────────────────────────── UI 辅助 ────────────────────────────── */

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  draft: '草稿',
  published: '已发布',
  locked: '已锁定',
  archived: '已归档',
}

export const PARSE_STATUS_LABEL: Record<ParseStatus, string> = {
  queued: '排队中',
  parsing: '解析中',
  done: '已完成',
  failed: '解析失败',
}

export const CLAIM_TYPE_LABEL: Record<ClaimType, string> = {
  education: '教育',
  work: '工作',
  project: '项目',
  publication: '论文',
  patent: '专利',
  award: '奖项',
  skill: '技能',
  contact: '联系方式',
  summary: '概述',
}

export const EVIDENCE_STATE_LABEL: Record<EvidenceState, string> = {
  strong: '强证据',
  partial: '部分证据',
  self_claim: '简历自述',
  missing: '缺少证据',
}

export const VOICE_STATUS_LABEL: Record<VoiceStatus, string> = {
  created: '已创建',
  connecting: '连接中',
  live: '通话中',
  ended: '已结束',
  failed: '失败',
  revoked: '授权已撤回',
}
