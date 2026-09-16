/** Shared presentational primitives. Every page composes these. */
import clsx from 'clsx'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

/* ------------------------------------------------------------------ panels */

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={clsx('panel', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-100">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-slate-400">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-400">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ badges */

const TONES = {
  neutral: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  info: 'bg-azure-500/15 text-azure-200 border-azure-500/30',
  success: 'bg-ok/15 text-emerald-300 border-ok/30',
  warning: 'bg-warn/15 text-amber-300 border-warn/30',
  danger: 'bg-danger/15 text-red-300 border-danger/30',
  accent: 'bg-cyanx/15 text-cyan-200 border-cyanx/30',
} as const

export type Tone = keyof typeof TONES

export function Badge({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode
  tone?: Tone
  title?: string
}) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
        TONES[tone],
      )}
    >
      {children}
    </span>
  )
}

export function toneForStatus(status: string): Tone {
  const value = status.toLowerCase()
  if (['succeeded', 'active', 'indexed', 'healthy', 'ok', 'available', 'pass', 'resolved'].includes(value))
    return 'success'
  if (['failed', 'blocked', 'unhealthy', 'critical', 'exceeded', 'error'].includes(value)) return 'danger'
  if (['running', 'processing', 'pending', 'degraded', 'warning', 'flagged', 'paused'].includes(value))
    return 'warning'
  if (['draft', 'not_configured', 'archived', 'deprecated', 'retired'].includes(value)) return 'neutral'
  return 'info'
}

export function StatusDot({ status }: { status: string }) {
  const tone = toneForStatus(status)
  const colour = {
    success: 'bg-ok',
    danger: 'bg-danger',
    warning: 'bg-warn',
    info: 'bg-azure-400',
    accent: 'bg-cyanx',
    neutral: 'bg-slate-500',
  }[tone]
  return <span className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', colour)} aria-hidden />
}

/* -------------------------------------------------------------- data states */

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton h-4 w-full', className)} />
}

export function LoadingPanel({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className={index === 0 ? 'h-5 w-1/3' : 'h-4 w-full'} />
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-200">{title}</p>
      {description && <p className="max-w-md text-xs text-slate-400">{description}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div
      role="alert"
      className="rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-red-200"
    >
      <p className="font-medium">Request failed</p>
      <p className="mt-1 text-xs text-red-300/90">{message}</p>
      {onRetry && (
        <button type="button" className="btn-ghost mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- table */

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
  sortable?: boolean
}

export function DataTable<T>({
  columns,
  rows,
  keyOf,
  onRowClick,
  sortBy,
  sortDir,
  onSort,
  emptyMessage = 'No records found.',
}: {
  columns: Column<T>[]
  rows: T[]
  keyOf: (row: T) => string
  onRowClick?: (row: T) => void
  sortBy?: string
  sortDir?: 'asc' | 'desc'
  onSort?: (key: string) => void
  emptyMessage?: string
}) {
  if (rows.length === 0) return <EmptyState title={emptyMessage} />

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-[11px] uppercase tracking-wide text-slate-400">
            {columns.map((column) => (
              <th key={column.key} scope="col" className={clsx('px-4 py-2 font-medium', column.className)}>
                {column.sortable && onSort ? (
                  <button
                    type="button"
                    onClick={() => onSort(column.key)}
                    className="inline-flex items-center gap-1 hover:text-slate-200"
                  >
                    {column.header}
                    {sortBy === column.key && <span aria-hidden>{sortDir === 'asc' ? '▲' : '▼'}</span>}
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={keyOf(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === 'Enter') onRowClick(row)
                    }
                  : undefined
              }
              tabIndex={onRowClick ? 0 : undefined}
              className={clsx(
                'border-b border-border/60 last:border-0',
                onRowClick && 'cursor-pointer hover:bg-elevated',
              )}
            >
              {columns.map((column) => (
                <td key={column.key} className={clsx('table-cell', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number
  pages: number
  total: number
  onChange: (page: number) => void
}) {
  if (total === 0) return null
  return (
    <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-400">
      <span>
        Page {page} of {pages} · {total.toLocaleString()} record{total === 1 ? '' : 's'}
      </span>
      <div className="flex gap-2">
        <button type="button" className="btn-ghost px-2 py-1" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button
          type="button"
          className="btn-ghost px-2 py-1"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <input
      type="search"
      className="field max-w-xs"
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

/* ------------------------------------------------------------------- modal */

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className={clsx('panel w-full', wide ? 'max-w-4xl' : 'max-w-lg')}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
          <button type="button" className="btn-ghost px-2 py-1" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-border px-4 py-3">{footer}</footer>}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  onConfirm,
  onCancel,
  busy,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
  busy?: boolean
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <p className="text-sm text-slate-300">{message}</p>
    </Modal>
  )
}

/* ------------------------------------------------------------------ toasts */

interface Toast {
  id: number
  message: string
  tone: Tone
}

const ToastContext = createContext<{ notify: (message: string, tone?: Tone) => void }>({
  notify: () => undefined,
})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const notify = useCallback((message: string, tone: Tone = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, message, tone }])
    setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 5000)
  }, [])

  const value = useMemo(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={clsx(
              'pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-panel backdrop-blur',
              TONES[toast.tone],
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}

/* ------------------------------------------------------------------- misc */

export function KpiCard({
  label,
  value,
  hint,
  tone = 'info',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: Tone
}) {
  return (
    <div className="panel px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{value}</p>
      {hint && (
        <p className="mt-1 text-[11px] text-slate-400">
          <Badge tone={tone}>{hint}</Badge>
        </p>
      )}
    </div>
  )
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string
  hint?: string
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <label className="block" htmlFor={htmlFor}>
      <span className="mb-1 block text-xs font-medium text-slate-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  )
}

export function DemoBanner({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div className="mb-4 rounded-md border border-cyanx/30 bg-cyanx/10 px-3 py-2 text-xs text-cyan-200">
      <strong className="font-semibold">Demo mode.</strong> All agents, documents, runs, costs and
      Azure inventory shown here are synthetic seed data. No live Azure resource is being queried.
    </div>
  )
}
