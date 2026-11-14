import { API_PREFIX, api } from './client'
import type { OfferDetail, OfferStatus, OfferSummary } from '../types'

export interface OfferInput {
  application_id: string
  position_title?: string
  salary_monthly?: string
  salary_months?: number
  start_date?: string
  expires_at?: string
  note?: string
}

export async function listOffers(params: {
  status?: OfferStatus
  job_id?: string
  limit?: number
} = {}): Promise<OfferSummary[]> {
  const response = await api.get(`${API_PREFIX}/offers`, { params })
  return response.data.items as OfferSummary[]
}

export async function getOffer(offerId: string): Promise<OfferDetail> {
  const response = await api.get(`${API_PREFIX}/offers/${offerId}`)
  return response.data as OfferDetail
}

export async function createOffer(body: OfferInput): Promise<OfferSummary> {
  const response = await api.post(`${API_PREFIX}/offers`, body)
  return response.data as OfferSummary
}

export async function updateOffer(
  offerId: string,
  body: Partial<Omit<OfferInput, 'application_id'>>,
): Promise<OfferSummary> {
  const response = await api.patch(`${API_PREFIX}/offers/${offerId}`, body)
  return response.data as OfferSummary
}

export async function sendOffer(offerId: string): Promise<OfferSummary> {
  const response = await api.post(`${API_PREFIX}/offers/${offerId}/send`)
  return response.data as OfferSummary
}

export async function withdrawOffer(offerId: string): Promise<OfferSummary> {
  const response = await api.post(`${API_PREFIX}/offers/${offerId}/withdraw`)
  return response.data as OfferSummary
}

export async function recordDecision(
  offerId: string,
  decision: 'accepted' | 'declined',
  note?: string,
): Promise<OfferSummary> {
  const response = await api.post(`${API_PREFIX}/offers/${offerId}/decision`, { decision, note })
  return response.data as OfferSummary
}
