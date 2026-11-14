import { useCallback, useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ModalDialogProps {
  open: boolean
  title: string
  subtitle?: string
  icon?: ReactNode
  onClose: () => void
  maxWidth?: number
  children: ReactNode
}

async function closeTopLayerWithFallback(dialog: HTMLDialogElement): Promise<void> {
  if (!dialog.open) return
  const reduced =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (reduced) {
    dialog.removeAttribute('data-closing')
    dialog.close()
    return
  }

  dialog.setAttribute('data-closing', 'true')
  const animations = typeof dialog.getAnimations === 'function' ? dialog.getAnimations({ subtree: true }) : []
  if (animations.length > 0) {
    await Promise.race([
      Promise.allSettled(animations.map((anim) => anim.finished)),
      new Promise<void>((resolve) => window.setTimeout(resolve, 260)),
    ])
  }
  dialog.removeAttribute('data-closing')
  if (dialog.open) dialog.close()
}

export function ModalDialog({
  open,
  title,
  subtitle,
  icon,
  onClose,
  maxWidth = 680,
  children,
}: ModalDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closingRef = useRef(false)
  const titleId = `ttc-dialog-title-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

  const requestClose = useCallback(() => {
    const dialog = dialogRef.current
    if (!dialog || !dialog.open || closingRef.current) return
    closingRef.current = true
    void closeTopLayerWithFallback(dialog).finally(() => {
      closingRef.current = false
      onClose()
    })
  }, [onClose])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      closingRef.current = false
      dialog.removeAttribute('data-closing')
      dialog.showModal()
    } else if (!open && dialog.open && !closingRef.current) {
      closingRef.current = true
      void closeTopLayerWithFallback(dialog).finally(() => {
        closingRef.current = false
      })
    }
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="ttc-dialog"
      style={{ maxWidth: `min(${maxWidth}px, calc(100vw - 32px))` }}
      aria-labelledby={titleId}
      closedby="any"
      onCancel={(event) => {
        event.preventDefault()
        requestClose()
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          requestClose()
        }
      }}
      onClose={() => {
        dialogRef.current?.removeAttribute('data-closing')
        closingRef.current = false
        if (open) onClose()
      }}
    >
      <div className="ttc-dialog-surface">
        <header className="ttc-dialog-head">
          <div className="ttc-dialog-title-wrap">
            {icon}
            <div>
              <h2 id={titleId} className="ttc-card-title">
                {title}
              </h2>
              {subtitle && <p className="ttc-card-sub">{subtitle}</p>}
            </div>
          </div>
          <button
            type="button"
            className="ttc-icon-btn"
            aria-label={`关闭：${title}`}
            onClick={requestClose}
          >
            <X size={17} />
          </button>
        </header>
        <div className="ttc-dialog-body">{children}</div>
      </div>
    </dialog>
  )
}
