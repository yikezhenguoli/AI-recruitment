import { API_PREFIX, api } from './client'
import type { MemberItem, MemberRole, MemberStatus, PermissionMatrix } from '../types'

export async function listMembers(): Promise<MemberItem[]> {
  const response = await api.get(`${API_PREFIX}/admin/members`)
  return response.data.items as MemberItem[]
}

export async function createMember(body: {
  email: string
  display_name: string
  role: MemberRole
  password?: string
}): Promise<MemberItem & { temporary_password: string | null }> {
  const response = await api.post(`${API_PREFIX}/admin/members`, body)
  return response.data
}

export async function updateMember(
  memberId: string,
  body: { display_name?: string; role?: MemberRole; status?: MemberStatus },
): Promise<MemberItem> {
  const response = await api.patch(`${API_PREFIX}/admin/members/${memberId}`, body)
  return response.data as MemberItem
}

export async function getPermissions(): Promise<PermissionMatrix> {
  const response = await api.get(`${API_PREFIX}/admin/permissions`)
  return response.data as PermissionMatrix
}

export async function updatePermissions(
  role: Exclude<MemberRole, 'admin'>,
  permissions: string[],
): Promise<{ role: string; permissions: string[] }> {
  const response = await api.put(`${API_PREFIX}/admin/permissions`, { role, permissions })
  return response.data
}
