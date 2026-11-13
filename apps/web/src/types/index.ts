export type Stage =
  | 'queued'
  | 'parsing'
  | 'extracting'
  | 'screening'
  | 'evaluating'
  | 'done'
  | 'error'
  | 'skipped'
  | 'filtered'
  | 'review'

export type ScreeningOutcome =
  | 'ranked'
  | 'filtered'
  | 'review'
  | 'duplicate'
  | 'error'

export interface GraduationYearInfo {
  selected_degree?: string
  graduation_year?: number
  source: 'explicit' | 'inferred' | 'unknown' | 'not_applicable'
}

export interface GraduationYearFilterConfig {
  enabled: boolean
  accepted_years: number[]
  unknown_year_behavior: 'manual_review'
  degree_selection: 'highest_relevant_degree'
}

export interface DimensionScore {
  name: string
  score: number
  reason: string
}

export interface CandidateProgress {
  candidateId: string
  fileName: string
  name?: string
  email?: string
  phone?: string
  score?: number
  explanation?: string[]
  dimensionScores?: DimensionScore[]
  stage: Stage
  error?: string
  parseMethod?: string
  screeningOutcome: ScreeningOutcome
  screeningReason?: string
  graduationYearInfo: GraduationYearInfo
  previewAvailable: boolean
}

export interface WSProgressMsg {
  type: 'progress'
  session_id: string
  candidate_id: string
  stage: Stage
  message: string
  data?: Record<string, unknown>
}

export interface WSResultMsg {
  type: 'result'
  session_id: string
  candidate_id: string
  result: {
    candidate_id: string
    file_name: string
    name?: string
    email?: string
    phone?: string
    score?: number
    explanation?: string[]
    dimension_scores?: DimensionScore[]
    stage: Stage
    error?: string
    parse_method?: string
    screening_outcome: ScreeningOutcome
    screening_reason?: string
    graduation_year_info?: GraduationYearInfo
    preview_available?: boolean
  }
}

export interface WSCompleteMsg {
  type: 'complete'
  session_id: string
  total: number
  completed: number
  failed: number
  skipped?: number
}

export type WSMessage = WSProgressMsg | WSResultMsg | WSCompleteMsg

export interface JDStructured {
  role_title: string
  seniority_level?: string
  required_skills: string[]
  preferred_skills: string[]
  min_years_experience?: number
  preferred_years_experience?: number
  education_requirements?: {
    level?: string
    field?: string
    required?: boolean
  }
  responsibilities: string[]
  keywords: string[]
}

export interface ScoringDimension {
  name: string
  label: string
  description: string
  max_points: number
}

export interface ScoringSchema {
  dimensions: ScoringDimension[]
}

export interface SavedJobSummary {
  name: string
  role_title: string
  updated_at: string
}

export interface SavedJobProfile {
  name: string
  jd_text: string
  structured: JDStructured
  scoring_schema: ScoringSchema
  created_at: string
  updated_at: string
}

export interface CandidateResult {
  candidate_id: string
  file_name: string
  name?: string
  email?: string
  phone?: string
  score?: number
  explanation: string[]
  dimension_scores?: DimensionScore[]
  stage: Stage
  error?: string
  parse_method?: string
  screening_outcome: ScreeningOutcome
  screening_reason?: string
  graduation_year_info?: GraduationYearInfo
  preview_available?: boolean
}

export interface PersonalInfo {
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  phone?: string | null
  location?: string | null
}

export interface EducationEntry {
  institution?: string | null
  degree?: string | null
  field?: string | null
  score_gpa?: string | null
  start_date?: string | null
  end_date?: string | null
}

export interface WorkExperienceEntry {
  organization?: string | null
  role?: string | null
  start_date?: string | null
  end_date?: string | null
  responsibilities: string[]
}

export interface ProjectEntry {
  name?: string | null
  description?: string | null
  technologies: string[]
}

export interface PublicationEntry {
  title?: string | null
  journal?: string | null
  year?: string | null
}

export interface CertificationEntry {
  name?: string | null
  issuer?: string | null
  date?: string | null
}

export interface ResumeStructured {
  personal_info: PersonalInfo
  skills: string[]
  education: EducationEntry[]
  work_experience: WorkExperienceEntry[]
  projects: ProjectEntry[]
  publications: PublicationEntry[]
  certifications: CertificationEntry[]
  additional_info: Record<string, unknown>
}

export interface CandidateDetailResponse {
  candidate: CandidateResult
  resume_structured: ResumeStructured
}

export interface SessionResultsResponse {
  session_id: string
  status: string
  total: number
  completed: number
  failed: number
  results: CandidateResult[]
}

export interface HealthResponse {
  status: string
  app: string
  provider: string
  model: string
  llm_configured: boolean
}

export type AppStep = 'jd' | 'upload' | 'processing' | 'results'
