import { API_PREFIX, api } from './client'
import type {
  AvailabilityResult,
  InterviewMode,
  InterviewSlot,
  InterviewStatus,
} from '../types'

export interface ScheduleInput {
  candidate_id: string
  job_id: string
  application_id?: string
  interviewer_id?: string
  scheduled_at: string
  duration_min?: number
  mode?: InterviewMode
  location?: string
  note?: string
}

export async function listSchedules(params: {
  from?: string
  to?: string
  status?: InterviewStatus
  interviewer_id?: string
  candidate_id?: string
  job_id?: string
  limit?: number
} = {}): Promise<InterviewSlot[]> {
  const response = await api.get(`${API_PREFIX}/interviews`, { params })
  return response.data.items as InterviewSlot[]
}

export async function createSchedule(body: ScheduleInput): Promise<InterviewSlot> {
  const response = await api.post(`${API_PREFIX}/interviews`, body)
  return response.data as InterviewSlot
}

export async function reschedule(
  slotId: string,
  body: {
    scheduled_at?: string
    duration_min?: number
    mode?: InterviewMode
    location?: string
    note?: string
    interviewer_id?: string
  },
): Promise<InterviewSlot> {
  const response = await api.patch(`${API_PREFIX}/interviews/${slotId}`, body)
  return response.data as InterviewSlot
}

export async function setScheduleStatus(
  slotId: string,
  status: 'confirmed' | 'completed' | 'canceled' | 'no_show',
  note?: string,
): Promise<InterviewSlot> {
  const response = await api.post(`${API_PREFIX}/interviews/${slotId}/status`, { status, note })
  return response.data as InterviewSlot
}

export async function getAvailability(params: {
  interviewer_id: string
  day: string
  timezone?: string
  duration_min?: number
}): Promise<AvailabilityResult> {
  const response = await api.get(`${API_PREFIX}/interviews/availability`, { params })
  return response.data as AvailabilityResult
}

export interface InterviewerOption {
  id: string
  email: string
  display_name: string
  role: string
}

export async function listInterviewers(): Promise<InterviewerOption[]> {
  const response = await api.get(`${API_PREFIX}/interviewers`)
  return response.data.items as InterviewerOption[]
}
