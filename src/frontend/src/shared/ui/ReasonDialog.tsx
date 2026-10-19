import type { ReactNode } from 'react'

const BASE_BUTTON_CLASS =
  'inline-flex items-center justify-center rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50'

interface ReasonDialogProps {
  open: boolean
  title: string
  description?: ReactNode
  value: string
  placeholder?: string
  confirmLabel?: string
  cancelLabel?: string
  isPending?: boolean
  onChange: (value: string) => void
  onConfirm: () => void
  onClose: () => void
}

export function ReasonDialog({
  open,
  title,
  description,
  value,
  placeholder = 'Add context for this transition',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isPending = false,
  onChange,
  onConfirm,
  onClose,
}: ReasonDialogProps) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="reason-dialog-title"
        className="w-full max-w-lg rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-2xl"
      >
        <div className="space-y-1">
          <h2 id="reason-dialog-title" className="text-lg font-semibold text-slate-950">
            {title}
          </h2>
          {description ? <div className="text-sm text-slate-500">{description}</div> : null}
        </div>

        <textarea
          className="mt-4 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          rows={4}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={isPending}
          autoFocus
        />

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className={`${BASE_BUTTON_CLASS} border border-slate-200 bg-white text-slate-600 hover:bg-slate-50`}
            disabled={isPending}
            onClick={onClose}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`${BASE_BUTTON_CLASS} bg-emerald-600 text-white hover:bg-emerald-700`}
            disabled={isPending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
