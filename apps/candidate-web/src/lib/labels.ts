import type { ConsentPurpose } from '../api/types'

export const PARSE_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  queued: { label: '排队解析', tone: 'warn' },
  parsing: { label: '解析中', tone: 'warn' },
  done: { label: '已解析', tone: 'ok' },
  failed: { label: '解析失败', tone: 'danger' },
}

export const ASSESSMENT_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  generating: { label: '生成中', tone: 'warn' },
  ready: { label: '已生成', tone: 'ok' },
  failed: { label: '生成失败', tone: 'danger' },
  revised: { label: '已修订', tone: 'ok' },
}

export const INTERVIEW_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  created: { label: '待开始', tone: 'warn' },
  live: { label: '进行中', tone: 'ok' },
  ended: { label: '已结束', tone: 'muted' },
  failed: { label: '连接失败', tone: 'danger' },
  revoked: { label: '已撤回', tone: 'danger' },
}

export const END_REASON: Record<string, string> = {
  candidate_end: '你主动结束',
  completed: '正常结束',
  timeout: '达到时长上限',
  revoked: '授权已撤回',
  upstream_closed: '语音服务断开',
  error: '连接异常',
  closed: '会话已关闭',
}

export const PRIVACY_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  submitted: { label: '已提交', tone: 'warn' },
  processing: { label: '处理中', tone: 'warn' },
  completed: { label: '已完成', tone: 'ok' },
  rejected: { label: '未通过', tone: 'danger' },
}

export const PRIVACY_TYPE: Record<string, string> = {
  access: '查阅我的数据',
  correct: '更正我的数据',
  revoke: '撤回授权',
  delete: '删除我的数据',
}

export const CONSENT_LABEL: Record<ConsentPurpose, string> = {
  resume_process: '简历解析与岗位匹配',
  voice_interview: 'AI 语音面试',
  recording: '面试录音留存',
  model_training: '用于模型训练',
}

export const CONSENT_DESCRIPTION: Record<ConsentPurpose, string> = {
  resume_process: '允许系统解析你上传的简历文本，并据此生成岗位匹配评估。撤回后不再发起新的解析与匹配。',
  voice_interview: '允许在一次 AI 初筛沟通中与你进行实时语音对话。撤回授权会立即切断进行中的通话。',
  recording: '允许保留面试音频用于回听与复核。当前系统默认不保存原始音频。',
  model_training: '允许将你的数据用于模型训练。默认关闭，不影响投递流程。',
}

export const SCENARIO_LABEL: Record<string, string> = {
  screen: 'AI 初筛沟通',
  deep_dive: '经历深挖',
  compensation: '期望沟通',
}
