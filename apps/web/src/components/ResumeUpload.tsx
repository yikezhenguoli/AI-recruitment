import React, { useCallback, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Loader2, Upload, X } from 'lucide-react'
import { processResumes } from '../api/resumes'
import { getApiErrorMessage } from '../lib/apiError'
import type { GraduationYearFilterConfig, JDStructured, ScoringSchema } from '../types'

const MAX_FILE_SIZE = 20 * 1024 * 1024
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.webp']

interface Props {
  jdText: string
  jdStructured: JDStructured
  scoringSchema: ScoringSchema
  graduationFilter: GraduationYearFilterConfig
  onProcessingStarted: (sessionId: string, totalFiles: number) => void
}

interface RejectedFile {
  name: string
  reason: string
}

export const ResumeUpload: React.FC<Props> = ({
  jdText,
  jdStructured,
  scoringSchema,
  graduationFilter,
  onProcessingStarted,
}) => {
  const [files, setFiles] = useState<File[]>([])
  const [rejected, setRejected] = useState<RejectedFile[]>([])
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return

    const nextRejected: RejectedFile[] = []
    const nextAccepted: File[] = []
    const existing = new Set(files.map((file) => `${file.name}:${file.size}`))

    Array.from(incoming).forEach((file) => {
      const lower = file.name.toLowerCase()
      if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        nextRejected.push({ name: file.name, reason: '仅支持 PDF / DOCX / TXT 与 PNG/JPEG/WebP' })
        return
      }
      if (file.size === 0) {
        nextRejected.push({ name: file.name, reason: '文件为空' })
        return
      }
      if (file.size > MAX_FILE_SIZE) {
        nextRejected.push({ name: file.name, reason: '超过 20 MB 限制' })
        return
      }
      const key = `${file.name}:${file.size}`
      if (existing.has(key)) {
        nextRejected.push({ name: file.name, reason: '重复文件' })
        return
      }
      existing.add(key)
      nextAccepted.push(file)
    })

    if (nextAccepted.length > 0) {
      setFiles((prev) => [...prev, ...nextAccepted])
    }
    if (nextRejected.length > 0) {
      setRejected((prev) => [...prev, ...nextRejected])
    }
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    setDragging(false)
    addFiles(event.dataTransfer.files)
  }, [files])

  const handleSubmit = async () => {
    if (files.length === 0 || loading || submitted) return
    setLoading(true)
    setError(null)
    try {
      const res = await processResumes(jdText, files, scoringSchema, graduationFilter)
      setSubmitted(true)
      onProcessingStarted(res.session_id, res.total_files)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '无法启动简历处理，请稍后重试。'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="ttc-upload-panel">
      <div className="ttc-upload-head">
        <div>
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            RESUME INTAKE
            <span className="hero-eyebrow-line" />
            <span>02 / 03</span>
          </div>
          <h2>上传简历</h2>
          <p>支持 PDF / DOCX / TXT 与图片批量上传；扫描件自动走视觉 OCR 转写。</p>
          <div className="ttc-upload-role">
            <span>当前岗位</span>
            <strong>{jdStructured.role_title}</strong>
          </div>
          {graduationFilter.enabled && graduationFilter.accepted_years.length > 0 && (
            <div className="ttc-badge ttc-badge-amber">
              毕业年份：{graduationFilter.accepted_years.join('、')}
            </div>
          )}
        </div>
        <div className="ttc-upload-count">
          <strong>{files.length}</strong>
          <span>个文件待处理</span>
        </div>
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`ttc-dropzone ${dragging ? 'is-dragging' : ''}`}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(event) => {
            addFiles(event.target.files)
            event.target.value = ''
          }}
        />
        <span className="ttc-dropzone-icon">
          <Upload size={24} />
        </span>
        <strong>拖拽简历到这里，或点击选择文件</strong>
        <span>PDF · DOCX · TXT · PNG/JPEG/WebP · 单文件不超过 20 MB</span>
      </div>

      {files.length > 0 && (
        <div className="ttc-file-block">
          <div className="ttc-file-block-head">
            <strong>待处理文件</strong>
            <button
              type="button"
              className="ttc-text-link"
              onClick={() => {
                setFiles([])
                setRejected([])
                setSubmitted(false)
              }}
            >
              清空
            </button>
          </div>
          <div className="ttc-file-list">
            {files.map((file) => (
              <div key={`${file.name}:${file.size}`} className="ttc-file-row">
                <span className="ttc-file-icon">
                  <FileText size={16} />
                </span>
                <div className="ttc-file-meta">
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024).toFixed(0)} KB</span>
                </div>
                <span className={`ttc-file-status ${submitted ? 'is-submitted' : ''}`}>
                  {submitted ? '已提交' : '待处理'}
                </span>
                {!submitted && (
                  <button
                    type="button"
                    className="ttc-icon-btn"
                    aria-label={`移除 ${file.name}`}
                    onClick={() => removeFile(files.indexOf(file))}
                  >
                    <X size={15} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {rejected.length > 0 && (
        <div className="ttc-rejected-block">
          <div className="ttc-rejected-head">
            <AlertCircle size={15} />
            <strong>{rejected.length} 个文件未加入队列</strong>
            <button type="button" className="ttc-text-link" onClick={() => setRejected([])}>
              清除提示
            </button>
          </div>
          <ul>
            {rejected.map((item, index) => (
              <li key={`${item.name}-${index}`}>
                <span>{item.name}</span>
                <b>{item.reason}</b>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <div className="ttc-inline-error">
          <AlertCircle size={16} />
          <div>
            <strong>无法启动处理</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      <div className="ttc-upload-actions">
        <span className="ttc-muted">处理进度来自 WebSocket 与后端结果接口，不使用前端模拟数据。</span>
        <button
          type="button"
          className="ttc-btn ttc-btn-primary"
          onClick={() => void handleSubmit()}
          disabled={loading || submitted || files.length === 0}
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              正在创建处理会话…
            </>
          ) : (
            <>
              <CheckCircle2 size={16} />
              开始 AI 筛选（{files.length}）
            </>
          )}
        </button>
      </div>
    </section>
  )
}
