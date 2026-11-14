import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, KeyRound, RefreshCw, ShieldCheck, UserPlus } from 'lucide-react'
import {
  createMember,
  getPermissions,
  listMembers,
  updateMember,
  updatePermissions,
} from '../api/team'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { MemberRole, MemberStatus } from '../types'

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  hr: '招聘专员',
  candidate: '候选人',
  guest: '访客',
}

const STATUS_LABEL: Record<MemberStatus, string> = {
  active: '在职',
  disabled: '已停用',
  pending: '待激活',
}

const PERMISSION_LABEL: Record<string, string> = {
  'job:manage': '岗位管理',
  'candidate:read': '查看候选人',
  'offer:manage': 'Offer 管理',
  'interview:manage': '面试排期',
  'talent:search': '人才库检索',
  'member:manage': '成员管理',
  'audit:view': '审计查看',
  'backup:manage': '备份管理',
}

export default function TeamPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<Exclude<MemberRole, 'candidate' | 'guest'>>('hr')
  const [tempPassword, setTempPassword] = useState<{ email: string; password: string } | null>(null)
  const [hrPermissions, setHrPermissions] = useState<string[]>([])

  const membersQuery = useQuery({ queryKey: ['members'], queryFn: listMembers })
  const permissionsQuery = useQuery({ queryKey: ['permissions'], queryFn: getPermissions })

  useEffect(() => {
    if (permissionsQuery.data?.matrix.hr) {
      setHrPermissions(permissionsQuery.data.matrix.hr)
    }
  }, [permissionsQuery.data])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['members'] })
    void queryClient.invalidateQueries({ queryKey: ['permissions'] })
  }

  const inviteMutation = useMutation({
    mutationFn: () => createMember({ email, display_name: displayName, role }),
    onSuccess: (member) => {
      setError('')
      setEmail('')
      setDisplayName('')
      setTempPassword(
        member.temporary_password
          ? { email: member.email, password: member.temporary_password }
          : null,
      )
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建成员失败。')),
  })

  const patchMutation = useMutation({
    mutationFn: (input: { id: string; status?: MemberStatus; role?: MemberRole }) =>
      updateMember(input.id, { status: input.status, role: input.role }),
    onSuccess: () => {
      setError('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '更新成员失败。')),
  })

  const permissionMutation = useMutation({
    mutationFn: () => updatePermissions('hr', hrPermissions),
    onSuccess: () => {
      setError('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '保存权限失败。')),
  })

  const members = membersQuery.data ?? []
  const permissionData = permissionsQuery.data
  const forbidden = membersQuery.isError && !members.length

  const togglePermission = (permission: string) => {
    setHrPermissions((current) =>
      current.includes(permission)
        ? current.filter((item) => item !== permission)
        : [...current, permission],
    )
  }

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            TEAM & ACCESS
            <span className="hero-eyebrow-line" />
            <span>RBAC</span>
          </div>
          <h1>团队与权限</h1>
          <p>邀请成员、停用账号，并按角色配置可见能力；管理员权限固定，不可被回收。</p>
        </div>
        <div className="ttc-heading-actions">
          <button type="button" className="ttc-btn ttc-btn-secondary"
            onClick={() => {
              void membersQuery.refetch()
              void permissionsQuery.refetch()
            }}>
            <RefreshCw size={15} className={membersQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </section>

      {error && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>操作未完成</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {forbidden && (
        <div className="ttc-error-panel">
          <ShieldCheck size={18} />
          <div>
            <strong>需要成员管理权限</strong>
            <span>{getApiErrorMessage(membersQuery.error, '只有管理员可以查看团队。')}</span>
          </div>
        </div>
      )}

      {tempPassword && (
        <div className="ttc-card" style={{ padding: '14px 16px' }}>
          <div className="ttc-card-header">
            <div>
              <h2 className="ttc-card-title">临时密码（只显示这一次）</h2>
              <p className="ttc-card-sub">{tempPassword.email}</p>
            </div>
            <KeyRound size={18} className="ttc-accent-icon" />
          </div>
          <code style={{ fontSize: 13, wordBreak: 'break-all' }}>{tempPassword.password}</code>
          <div className="ttc-card-actions">
            <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => setTempPassword(null)}>
              我已保存
            </button>
          </div>
        </div>
      )}

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">邀请成员</h2>
            <p className="ttc-card-sub">不填密码时由系统生成一次性临时密码。</p>
          </div>
          <UserPlus size={18} className="ttc-accent-icon" />
        </div>
        <div className="ttc-inline-form">
          <label className="ttc-login-field">
            <span>邮箱</span>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com" />
          </label>
          <label className="ttc-login-field">
            <span>显示名</span>
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <label className="ttc-login-field" style={{ flexBasis: 130 }}>
            <span>角色</span>
            <select value={role} onChange={(event) => setRole(event.target.value as 'hr' | 'admin')}>
              <option value="hr">招聘专员</option>
              <option value="admin">管理员</option>
            </select>
          </label>
          <button type="button" className="ttc-btn ttc-btn-primary"
            disabled={!email || !displayName || inviteMutation.isPending}
            onClick={() => inviteMutation.mutate()}>
            {inviteMutation.isPending ? '创建中…' : '创建成员'}
          </button>
        </div>
      </article>

      <div className="ttc-table-card">
      <div className="ttc-table-scroll">
        <table className="ttc-result-table">
          <thead>
            <tr>
              <th>成员</th>
              <th>角色</th>
              <th>状态</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td>
                  <strong>{member.display_name}</strong>
                  <span className="ttc-muted" style={{ display: 'block', fontSize: 10 }}>
                    {member.email}
                  </span>
                </td>
                <td className="ttc-muted">{ROLE_LABEL[member.role] ?? member.role}</td>
                <td>
                  <span className={`ttc-badge ${member.status === 'active' ? 'ttc-badge-green' : 'ttc-badge-red'}`}>
                    {STATUS_LABEL[member.status] ?? member.status}
                  </span>
                </td>
                <td className="ttc-muted">
                  {member.last_login_at ? formatDateTime(member.last_login_at) : '从未登录'}
                </td>
                <td>
                  <div className="ttc-card-actions">
                    <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                      disabled={patchMutation.isPending}
                      onClick={() => patchMutation.mutate({
                        id: member.id,
                        status: member.status === 'active' ? 'disabled' : 'active',
                      })}>
                      {member.status === 'active' ? '停用' : '启用'}
                    </button>
                    {member.role !== 'admin' && (
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={patchMutation.isPending}
                        onClick={() => patchMutation.mutate({ id: member.id, role: 'admin' })}>
                        设为管理员
                      </button>
                    )}
                    {member.role === 'admin' && members.filter((item) => item.role === 'admin').length > 1 && (
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        disabled={patchMutation.isPending}
                        onClick={() => patchMutation.mutate({ id: member.id, role: 'hr' })}>
                        降为招聘专员
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!membersQuery.isLoading && members.length === 0 && !forbidden && (
              <tr>
                <td colSpan={5} className="ttc-muted">还没有成员。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </div>

      <article className="ttc-card">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">角色权限矩阵</h2>
            <p className="ttc-card-sub">
              管理员恒拥有全部权限；这里只配置「招聘专员」。
            </p>
          </div>
          <ShieldCheck size={18} className="ttc-accent-icon" />
        </div>
        {permissionData ? (
          <>
            <div className="ttc-perm-grid">
              <div className="ttc-perm-card">
                <h3>招聘专员</h3>
                {permissionData.permissions.map((permission) => (
                  <label key={permission}>
                    <input type="checkbox"
                      checked={hrPermissions.includes(permission)}
                      onChange={() => togglePermission(permission)} />
                    {PERMISSION_LABEL[permission] ?? permission}
                  </label>
                ))}
              </div>
              <div className="ttc-perm-card">
                <h3>管理员（固定）</h3>
                {permissionData.permissions.map((permission) => (
                  <label key={permission}>
                    <input type="checkbox" checked disabled readOnly />
                    {PERMISSION_LABEL[permission] ?? permission}
                  </label>
                ))}
              </div>
            </div>
            <div className="ttc-card-actions">
              <button type="button" className="ttc-btn ttc-btn-primary"
                disabled={permissionMutation.isPending}
                onClick={() => permissionMutation.mutate()}>
                {permissionMutation.isPending ? '保存中…' : '保存权限'}
              </button>
            </div>
          </>
        ) : (
          <p className="ttc-muted">{permissionsQuery.isLoading ? '读取中…' : '没有权限读取矩阵。'}</p>
        )}
      </article>
    </div>
  )
}
