import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
  id: string
  type: ToastType
  message: string
}

interface ToastContextValue {
  toasts: Toast[]
  toast: {
    success: (message: string) => void
    error: (message: string) => void
    info: (message: string) => void
    warning: (message: string) => void
  }
  dismiss: (id: string) => void
}

const ToastContext = createContext<ToastContextValue>({
  toasts: [],
  toast: {
    success: () => undefined,
    error: () => undefined,
    info: () => undefined,
    warning: () => undefined,
  },
  dismiss: () => undefined,
})

export function useToast(): ToastContextValue {
  return useContext(ToastContext)
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

let counter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const add = useCallback((type: ToastType, message: string) => {
    const id = String(++counter)
    setToasts((prev) => [...prev, { id, type, message }])
    // Auto-dismiss after 5 s
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = {
    success: (message: string) => add('success', message),
    error: (message: string) => add('error', message),
    info: (message: string) => add('info', message),
    warning: (message: string) => add('warning', message),
  }

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss }}>
      {children}
      <ToastArea toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Visual toast area (minimal — no animation library dependency)
// ---------------------------------------------------------------------------

const TYPE_STYLES: Record<ToastType, string> = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  info: 'bg-blue-600',
  warning: 'bg-amber-500',
}

function ToastArea({
  toasts,
  dismiss,
}: {
  toasts: Toast[]
  dismiss: (id: string) => void
}) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 rounded px-4 py-3 text-sm text-white shadow-lg ${TYPE_STYLES[t.type]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => dismiss(t.id)}
            className="shrink-0 opacity-70 hover:opacity-100"
            aria-label="Zavřít"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
