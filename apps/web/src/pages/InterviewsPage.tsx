import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CalendarClock, Plus, RefreshCw } from 'lucide-react'
import { ModalDialog } from '../components/layout/ModalDialog'
import { listApplications } from '../api/applications'
import {
  createSchedule,
  getAvailability,
  listInterviewers,
  listSchedules,
  reschedule,
  setScheduleStatus,
} from '../api/interviews'
import { getApiErrorMessage } from '../lib/apiError'
import { formatDateTime } from '../lib/format'
import type { InterviewMode, InterviewStatus } from '../types'

const STATUS_LABEL: Record<InterviewStatus, string> = {
  scheduled: '待进行',
  confirmed: '已确认',
  completed: '已完成',
  canceled: '已取消',
  no_show: '未到场',
}

const STATUS_CLASS: Record<InterviewStatus, string> = {
  scheduled: 'ttc-badge-amber',
  confirmed: 'ttc-badge-green',
  completed: 'ttc-badge-blue',
  canceled: 'ttc-badge-red',
  no_show: 'ttc-badge-red',
}

const MODE_LABEL: Record<InterviewMode, string> = {
  onsite: '现场',
  video: '视频',
  phone: '电话',
}

function toLocalInput(iso: string): string {
  const date = new Date(iso)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export default function InterviewsPage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<'all' | InterviewStatus>('all')
  const [scope, setScope] = useState<'upcoming' | 'all'>('upcoming')
  const [formOpen, setFormOpen] = useState(false)
  const [error, setError] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [interviewerId, setInterviewerId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [duration, setDuration] = useState('45')
  const [mode, setMode] = useState<InterviewMode>('video')
  const [location, setLocation] = useState('')
  const [note, setNote] = useState('')
  const [availabilityDay, setAvailabilityDay] = useState(() =>
    new Date().toISOString().slice(0, 10),
  )
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [rescheduleAt, setRescheduleAt] = useState('')

  const schedulesQuery = useQuery({
    queryKey: ['schedules', status, scope],
    queryFn: () =>
      listSchedules({
        status: status === 'all' ? undefined : status,
        from: scope === 'upcoming' ? new Date(Date.now() - 3_600_000).toISOString() : undefined,
      }),
  })
  const applicationsQuery = useQuery({
    queryKey: ['applications', 'for-interview'],
    queryFn: () => listApplications({ limit: 200 }),
  })
  const interviewersQuery = useQuery({ queryKey: ['interviewers'], queryFn: listInterviewers })
  const availabilityQuery = useQuery({
    queryKey: ['availability', interviewerId, availabilityDay, duration],
    queryFn: () =>
      getAvailability({
        interviewer_id: interviewerId,
        day: availabilityDay,
        duration_min: Number(duration) || 45,
      }),
    enabled: Boolean(interviewerId),
  })

  const applications = applicationsQuery.data ?? []
  const interviewers = interviewersQuery.data ?? []
  const selectedApplication = useMemo(
    () => applications.find((item) => item.id === applicationId),
    [applications, applicationId],
  )

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['schedules'] })
    void queryClient.invalidateQueries({ queryKey: ['availability'] })
  }

  const createMutation = useMutation({
    mutationFn: () => {
      if (!selectedApplication) throw new Error('请选择投递')
      return createSchedule({
        candidate_id: selectedApplication.candidate_id,
        job_id: selectedApplication.job_id,
        application_id: selectedApplication.id,
        interviewer_id: interviewerId || undefined,
        scheduled_at: new Date(scheduledAt).toISOString(),
        duration_min: Number(duration) || 45,
        mode,
        location: location || undefined,
        note: note || undefined,
      })
    },
    onSuccess: () => {
      setError('')
      setFormOpen(false)
      setApplicationId('')
      setScheduledAt('')
      setNote('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '创建排期失败。')),
  })

  const statusMutation = useMutation({
    mutationFn: (input: { id: string; status: 'confirmed' | 'completed' | 'canceled' | 'no_show' }) =>
      setScheduleStatus(input.id, input.status),
    onSuccess: () => {
      setError('')
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '更新状态失败。')),
  })

  const rescheduleMutation = useMutation({
    mutationFn: (input: { id: string; at: string }) =>
      reschedule(input.id, { scheduled_at: new Date(input.at).toISOString() }),
    onSuccess: () => {
      setError('')
      setRescheduleId(null)
      invalidate()
    },
    onError: (err) => setError(getApiErrorMessage(err, '改期失败。')),
  })

  const schedules = schedulesQuery.data ?? []
  const availability = availabilityQuery.data

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            INTERVIEW OPS
            <span className="hero-eyebrow-line" />
            <span>CALENDAR</span>
          </div>
          <h1>面试排期</h1>
          <p>安排面试、检测面试官与候选人的时间冲突，并把结果同步到候选人日程。</p>
        </div>
        <div className="ttc-heading-actions">
          <button type="button" className="ttc-btn ttc-btn-secondary" onClick={() => void schedulesQuery.refetch()}>
            <RefreshCw size={15} className={schedulesQuery.isFetching ? 'animate-spin' : ''} />
            刷新
          </button>
          <button type="button" className="ttc-btn ttc-btn-primary" onClick={() => setFormOpen((value) => !value)}>
            <Plus size={16} />
            安排面试
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

      <ModalDialog
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="安排面试"
        subtitle="时间必须带时区；与已有排期重叠会被拒绝并列出冲突项。"
        icon={<CalendarClock size={18} className="ttc-accent-icon" />}
        maxWidth={760}
      >
        <div className="ttc-launch-form">
          <label className="ttc-login-field">
            <span>投递</span>
            <select value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>
              <option value="">请选择投递</option>
              {applications.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.candidate_name} · {item.job_title}
                </option>
              ))}
            </select>
          </label>
          <label className="ttc-login-field">
            <span>面试官</span>
            <select value={interviewerId} onChange={(event) => setInterviewerId(event.target.value)}>
              <option value="">暂不指定</option>
              {interviewers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name}（{item.role}）
                </option>
              ))}
            </select>
          </label>
          <label className="ttc-login-field">
            <span>开始时间</span>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(event) => setScheduledAt(event.target.value)}
            />
          </label>
          <label className="ttc-login-field">
            <span>时长（分钟）</span>
            <input
              value={duration}
              inputMode="numeric"
              onChange={(event) => setDuration(event.target.value)}
            />
          </label>
          <label className="ttc-login-field">
            <span>形式</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as InterviewMode)}>
              <option value="video">视频</option>
              <option value="onsite">现场</option>
              <option value="phone">电话</option>
            </select>
          </label>
          <label className="ttc-login-field">
            <span>地点 / 会议链接</span>
            <input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="线上会议链接或会议室"
            />
          </label>
          <label className="ttc-login-field">
            <span>备注</span>
            <input value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
        </div>

        {interviewerId && (
          <div className="ttc-slot-grid" style={{ marginTop: 12 }}>
            <label className="ttc-login-field" style={{ flexBasis: 150 }}>
              <span>查看面试官空闲日</span>
              <input
                type="date"
                value={availabilityDay}
                onChange={(event) => setAvailabilityDay(event.target.value)}
              />
            </label>
            <div style={{ flex: 1 }}>
              <span className="ttc-muted" style={{ fontSize: 10 }}>
                {availabilityQuery.isFetching
                  ? '计算中…'
                  : availability
                    ? `${availability.date} 可用 ${availability.slots.length} 个时段（${availability.note}）`
                    : '选择日期后显示可用时段'}
              </span>
              <div className="ttc-slot-grid" style={{ marginTop: 6 }}>
                {(availability?.slots ?? []).slice(0, 24).map((slot) => (
                  <button
                    key={slot.start}
                    type="button"
                    className="ttc-chip"
                    onClick={() => setScheduledAt(toLocalInput(slot.start))}
                  >
                    {new Date(slot.start).toLocaleTimeString('zh-CN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="ttc-card-actions ttc-dialog-actions">
          <button
            type="button"
            className="ttc-btn ttc-btn-secondary"
            onClick={() => setFormOpen(false)}
          >
            取消
          </button>
          <button
            type="button"
            className="ttc-btn ttc-btn-primary"
            disabled={!applicationId || !scheduledAt || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? '提交中…' : '确认排期'}
          </button>
        </div>
      </ModalDialog>

      <search className="ttc-filter-chips" aria-label="按排期状态与范围筛选">
        {(
          [
            ['all', '全部'],
            ['scheduled', '待进行'],
            ['confirmed', '已确认'],
            ['completed', '已完成'],
            ['canceled', '已取消'],
            ['no_show', '未到场'],
          ] as const
        ).map(([value, label]) => (
          <button key={value} type="button"
            className={`ttc-chip ${status === value ? 'ttc-chip-blue' : ''}`}
            onClick={() => setStatus(value)}>
            {label}
          </button>
        ))}
        <span className="ttc-topbar-divider" />
        <button type="button" className={`ttc-chip ${scope === 'upcoming' ? 'ttc-chip-blue' : ''}`}
          onClick={() => setScope('upcoming')}>
          即将开始
        </button>
        <button type="button" className={`ttc-chip ${scope === 'all' ? 'ttc-chip-blue' : ''}`}
          onClick={() => setScope('all')}>
          含历史
        </button>
      </search>

      {schedulesQuery.isError && (
        <div className="ttc-error-panel">
          <AlertCircle size={18} />
          <div>
            <strong>无法读取排期</strong>
            <span>{getApiErrorMessage(schedulesQuery.error, '请确认后端服务已启动。')}</span>
          </div>
        </div>
      )}

      <div className="ttc-table-scroll ttc-table-container" tabIndex={0} role="region" aria-label="面试排期列表">
        <table className="ttc-result-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>候选人 / 岗位</th>
              <th>面试官</th>
              <th>形式</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {schedules.map((slot) => (
              <tr key={slot.id}>
                <td data-label="时间">
                  <strong>{formatDateTime(slot.scheduled_at)}</strong>
                  <span className="ttc-muted" style={{ display: 'block', fontSize: 10 }}>
                    {slot.duration_min} 分钟
                  </span>
                </td>
                <td data-label="候选人 / 岗位">
                  {slot.candidate_name}
                  <span className="ttc-muted" style={{ display: 'block', fontSize: 10 }}>
                    {slot.job_title}
                  </span>
                </td>
                <td data-label="面试官" className="ttc-muted">{slot.interviewer_name ?? '未指定'}</td>
                <td data-label="形式" className="ttc-muted">
                  {MODE_LABEL[slot.mode]}
                  {slot.location ? ` · ${slot.location}` : ''}
                </td>
                <td data-label="状态">
                  <span className={`ttc-badge ${STATUS_CLASS[slot.status]}`}>
                    {STATUS_LABEL[slot.status]}
                  </span>
                </td>
                <td data-label="操作">
                  <div className="ttc-card-actions">
                    {(slot.status === 'scheduled' || slot.status === 'confirmed') && (
                      <>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => {
                            setRescheduleId(slot.id)
                            setRescheduleAt(toLocalInput(slot.scheduled_at))
                          }}>
                          改期
                        </button>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => statusMutation.mutate({ id: slot.id, status: 'completed' })}>
                          完成
                        </button>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => statusMutation.mutate({ id: slot.id, status: 'canceled' })}>
                          取消
                        </button>
                        <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                          onClick={() => statusMutation.mutate({ id: slot.id, status: 'no_show' })}>
                          未到场
                        </button>
                      </>
                    )}
                    {slot.status === 'scheduled' && (
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        onClick={() => statusMutation.mutate({ id: slot.id, status: 'confirmed' })}>
                        确认
                      </button>
                    )}
                  </div>
                  {rescheduleId === slot.id && (
                    <div className="ttc-inline-form" style={{ marginTop: 6 }}>
                      <input type="datetime-local" value={rescheduleAt}
                        onChange={(event) => setRescheduleAt(event.target.value)} />
                      <button type="button" className="ttc-btn ttc-btn-primary ttc-btn-sm"
                        disabled={!rescheduleAt || rescheduleMutation.isPending}
                        onClick={() => rescheduleMutation.mutate({ id: slot.id, at: rescheduleAt })}>
                        保存
                      </button>
                      <button type="button" className="ttc-btn ttc-btn-secondary ttc-btn-sm"
                        onClick={() => setRescheduleId(null)}>
                        取消
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {!schedulesQuery.isLoading && schedules.length === 0 && (
              <tr>
                <td colSpan={6} className="ttc-muted">
                  这个筛选下没有面试安排。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
