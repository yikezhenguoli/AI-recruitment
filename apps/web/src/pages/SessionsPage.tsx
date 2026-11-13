import {
  AlertTriangle,
  AudioLines,
  Bot,
  Info,
  Loader2,
  Lock,
  MessageSquare,
  Mic,
  MicOff,
  Radio,
  ServerOff,
  ShieldCheck,
  Square,
  Waves,
} from 'lucide-react'
import {
  useMicrophone,
  usePrefersReducedMotion,
  VoiceWaveform,
} from '../components/voice/VoiceWaveform'
import type { MicrophoneStatus } from '../components/voice/VoiceWaveform'

type BadgeTone = 'muted' | 'ok' | 'warn' | 'danger'

const STATUS_META: Record<MicrophoneStatus, { label: string; tone: BadgeTone }> = {
  idle: { label: '未开启', tone: 'muted' },
  requesting: { label: '等待授权', tone: 'warn' },
  active: { label: '采集中', tone: 'ok' },
  stopped: { label: '已停止', tone: 'muted' },
  unsupported: { label: '浏览器不支持', tone: 'danger' },
  denied: { label: '权限被拒绝', tone: 'danger' },
  'no-device': { label: '无麦克风设备', tone: 'danger' },
  busy: { label: '设备被占用', tone: 'danger' },
  error: { label: '采集失败', tone: 'danger' },
}

function getStageEmptyCopy(status: MicrophoneStatus): readonly [string, string] {
  switch (status) {
    case 'requesting':
      return ['正在等待麦克风授权', '请在浏览器提示中允许麦克风访问']
    case 'denied':
      return ['麦克风权限被拒绝', '在站点设置中允许麦克风后重新尝试']
    case 'no-device':
      return ['未检测到麦克风', '连接输入设备后重新开启']
    case 'busy':
      return ['麦克风被占用', '关闭其他占用麦克风的应用后重试']
    case 'unsupported':
      return ['浏览器不支持麦克风采集', '请使用最新版 Chrome / Edge，并通过 HTTPS 或 localhost 访问']
    case 'error':
      return ['麦克风采集失败', '查看下方说明后重新尝试']
    case 'stopped':
      return ['麦克风已停止', '音频轨道已释放，可重新开启本地预览']
    default:
      return ['麦克风未开启', '点击“开启麦克风”开始本地波形预览']
  }
}

const SUPPORT_ERROR =
  '当前浏览器不支持麦克风采集（navigator.mediaDevices 不可用）。请使用最新版 Chrome / Edge，并通过 localhost 或 HTTPS 访问。'

const SESSION_ROWS = [
  {
    icon: Lock,
    label: '音频上传 / 存储',
    detail: '不录音、不上传、不保存',
    badge: '未启用',
    tone: 'muted' as BadgeTone,
  },
  {
    icon: MessageSquare,
    label: '实时转写',
    detail: '需要 M6 语音会话后端',
    badge: '未接入',
    tone: 'warn' as BadgeTone,
  },
  {
    icon: Bot,
    label: 'AI 面试官 / 评价',
    detail: '不生成模拟问答或评分',
    badge: '未接入',
    tone: 'warn' as BadgeTone,
  },
]

export default function SessionsPage() {
  const reducedMotion = usePrefersReducedMotion()
  const { status, error, analyser, isActive, isSupported, start, stop } = useMicrophone()

  const meta = STATUS_META[status]
  const isRequesting = status === 'requesting'
  const errorText = error ?? (isSupported ? null : SUPPORT_ERROR)
  const [emptyTitle, emptyHint] = getStageEmptyCopy(status)

  return (
    <div className="ttc-page">
      <section className="ttc-page-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            VOICE SESSION
            <span className="hero-eyebrow-line" />
            <span>LOCAL MIC PREVIEW</span>
          </div>
          <h1>语音会话</h1>
          <p>
            使用浏览器麦克风与 Web Audio AnalyserNode 绘制真实输入波形。真正的语音面试、实时转写与通话分析属于
            M6/M7 范围，后端尚未接入，本页面不会模拟这些能力。
          </p>
        </div>
        <div className="ttc-heading-actions">
          <span className="ttc-status ttc-status-warn">
            <i />
            M6 后端未接入
          </span>
        </div>
      </section>

      <section className="ttc-voice-stats" aria-label="语音会话能力概览">
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon">
            <Mic size={17} />
          </span>
          <div>
            <span>麦克风状态</span>
            <strong>{meta.label}</strong>
          </div>
        </article>
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon ttc-voice-stat-icon-blue">
            <AudioLines size={17} />
          </span>
          <div>
            <span>音频处理</span>
            <strong>仅浏览器本地</strong>
          </div>
        </article>
        <article className="ttc-voice-stat">
          <span className="ttc-voice-stat-icon ttc-voice-stat-icon-amber">
            <ServerOff size={17} />
          </span>
          <div>
            <span>实时会话后端</span>
            <strong>M6 尚未接入</strong>
          </div>
        </article>
      </section>

      <div className="ttc-notice ttc-notice-warn ttc-voice-notice">
        <AlertTriangle size={16} />
        <span>
          <strong>M6 语音面试后端尚未接入 · 当前仅展示本地麦克风波形。</strong>
          此页面不包含真实 AI 面试官、通话状态、实时转写或 AI 评分，也不会伪造上述内容。
        </span>
      </div>

      <section className="ttc-voice-grid">
        <article className="ttc-card ttc-voice-main">
          <div className="ttc-voice-main-head">
            <div>
              <div className="ttc-mini-heading">
                <AudioLines size={14} />
                LOCAL MIC WAVEFORM
              </div>
              <h2>本地麦克风波形</h2>
              <p>点击按钮后请求一次麦克风权限，实时绘制你对着麦克风说话时的输入信号。</p>
            </div>
            <span className={`ttc-voice-pill ttc-voice-pill-${meta.tone}`}>
              <i />
              {meta.label}
            </span>
          </div>

          <div className={`ttc-voice-stage ${isActive ? 'is-live' : ''}`}>
            <VoiceWaveform
              analyser={analyser}
              active={isActive}
              reducedMotion={reducedMotion}
            />

            {!isActive && (
              <div className="ttc-voice-idle">
                <span className="ttc-voice-idle-icon">
                  {isRequesting ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <MicOff size={18} />
                  )}
                </span>
                <strong>{emptyTitle}</strong>
                <span>{emptyHint}</span>
              </div>
            )}

            {isActive && (
              <span className="ttc-voice-live-tag">
                <i />
                {reducedMotion ? '静态波形' : '本地输入'}
              </span>
            )}
          </div>

          {errorText && (
            <div className="ttc-inline-error ttc-voice-error">
              <AlertTriangle size={16} />
              <div>
                <strong>
                  {status === 'denied' ? '麦克风权限被拒绝' : '无法使用麦克风'}
                </strong>
                <span>{errorText}</span>
              </div>
            </div>
          )}

          <div className="ttc-voice-controls">
            <div className="ttc-voice-actions">
              <button
                type="button"
                className="ttc-btn ttc-btn-primary"
                onClick={start}
                disabled={!isSupported || isActive || isRequesting}
                aria-busy={isRequesting}
              >
                {isRequesting ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Mic size={16} />
                )}
                开启麦克风
              </button>
              <button
                type="button"
                className="ttc-btn ttc-btn-secondary"
                onClick={stop}
                disabled={!isActive}
              >
                <Square size={14} />
                停止
              </button>
            </div>
            <p className="ttc-voice-permission">
              <ShieldCheck size={13} />
              仅在点击后申请权限；页面加载时不会自动请求麦克风。
            </p>
          </div>

          {reducedMotion && (
            <div className="ttc-voice-motion-note">
              <Waves size={14} />
              已遵循系统“减少动态效果”设置：波形使用静态预览，不进行持续重绘。
            </div>
          )}
        </article>

        <div className="ttc-voice-side">
          <article className="ttc-card ttc-voice-panel">
            <div className="ttc-voice-panel-head">
              <div>
                <div className="ttc-mini-heading">
                  <Radio size={14} />
                  SESSION STATUS
                </div>
                <h2>会话状态</h2>
              </div>
              <span className={`ttc-voice-badge ttc-voice-badge-${meta.tone}`}>
                {meta.label}
              </span>
            </div>

            <div className="ttc-voice-meta">
              <div className="ttc-voice-meta-row">
                <span className="ttc-voice-meta-icon">
                  <Mic size={15} />
                </span>
                <div className="ttc-voice-meta-copy">
                  <strong>本地麦克风采集</strong>
                  <span>Web Audio · AnalyserNode</span>
                </div>
                <span className={`ttc-voice-badge ttc-voice-badge-${meta.tone}`}>
                  {meta.label}
                </span>
              </div>

              {SESSION_ROWS.map((row) => {
                const Icon = row.icon
                return (
                  <div className="ttc-voice-meta-row" key={row.label}>
                    <span className="ttc-voice-meta-icon">
                      <Icon size={15} />
                    </span>
                    <div className="ttc-voice-meta-copy">
                      <strong>{row.label}</strong>
                      <span>{row.detail}</span>
                    </div>
                    <span className={`ttc-voice-badge ttc-voice-badge-${row.tone}`}>
                      {row.badge}
                    </span>
                  </div>
                )
              })}
            </div>
          </article>

          <article className="ttc-card ttc-voice-panel ttc-voice-transcript">
            <div className="ttc-voice-panel-head">
              <div>
                <div className="ttc-mini-heading">
                  <MessageSquare size={14} />
                  TRANSCRIPT
                </div>
                <h2>实时转写</h2>
              </div>
              <span className="ttc-voice-badge ttc-voice-badge-warn">占位</span>
            </div>

            <div className="ttc-voice-transcript-empty">
              <span className="ttc-voice-transcript-icon">
                <AudioLines size={19} />
              </span>
              <strong>等待真实语音会话接入</strong>
              <p>
                M6 后端接入后，经授权的实时转写会显示在这里。当前不生成任何模拟对话、通话状态或
                AI 评价。
              </p>
            </div>
          </article>
        </div>
      </section>

      <article className="ttc-card ttc-voice-scope">
        <div className="ttc-card-header">
          <div>
            <h2 className="ttc-card-title">本地预览边界</h2>
            <p className="ttc-card-sub">
              页面中的每一项能力都对应真实状态；未接入的能力会被明确标注，不用占位数据填充。
            </p>
          </div>
          <ShieldCheck size={18} className="ttc-accent-icon" />
        </div>

        <div className="ttc-voice-scope-grid">
          <div className="ttc-voice-scope-item">
            <Lock size={16} />
            <strong>不录音</strong>
            <span>未使用 MediaRecorder，不保存任何音频数据。</span>
          </div>
          <div className="ttc-voice-scope-item">
            <ServerOff size={16} />
            <strong>不上传</strong>
            <span>麦克风信号只在浏览器内完成分析，不发送到后端。</span>
          </div>
          <div className="ttc-voice-scope-item">
            <Info size={16} />
            <strong>不伪造</strong>
            <span>没有模拟转写、虚构通话状态或 AI 面试评分。</span>
          </div>
        </div>
      </article>
    </div>
  )
}
