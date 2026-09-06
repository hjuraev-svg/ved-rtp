import { useEffect, type ReactNode } from 'react'
import { progressClass } from '../util'

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal card" style={wide ? { maxWidth: 900 } : undefined}>
        <div className="panel-head">
          <h3>{title}</h3>
          <div className="spacer" />
          <button className="btn ghost sm" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="panel-body">{children}</div>
        {footer && (
          <div className="panel-body" style={{ borderTop: '1px solid var(--border)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

export function Progress({ pct, label }: { pct: number; label?: boolean }) {
  return (
    <div className="row" style={{ gap: 7 }}>
      <div className={progressClass(pct)} style={{ flex: 1 }}>
        <i style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
      </div>
      {label && (
        <span className="small faint num" style={{ minWidth: 32 }}>
          {pct}%
        </span>
      )}
    </div>
  )
}

export function Field({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

export function Loading() {
  return <div className="empty">Загрузка…</div>
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error-box">{message}</div>
}

export function Panel({
  title,
  actions,
  children,
  tight,
}: {
  title: string
  actions?: ReactNode
  children: ReactNode
  tight?: boolean
}) {
  return (
    <div className="card">
      <div className="panel-head">
        <h3>{title}</h3>
        <div className="spacer" />
        {actions}
      </div>
      <div className={tight ? 'panel-body tight' : 'panel-body'}>{children}</div>
    </div>
  )
}
