import { useEffect, useId, useState } from 'react'
import { CaseWorkTypePicker } from '../containers/CaseWorkTypePicker'
import type { WorkTypeSelectHandler } from '../types/workCatalog.types'

interface WorkTypeCommandPaletteProps {
  caseStatus: string
  onSelect: WorkTypeSelectHandler
  title?: string | undefined
  description?: string | undefined
  triggerLabel?: string | undefined
  triggerPlaceholder?: string | undefined
  disabled?: boolean | undefined
}

export function WorkTypeCommandPalette({
  caseStatus,
  onSelect,
  title = 'Pridat typ prace',
  description = 'Vyberte zasah z katalogu. Na desktopu muzete otevrit picker i zkratkou Ctrl/Cmd + K.',
  triggerLabel = 'Typ prace',
  triggerPlaceholder = 'Kliknete a hledejte podle nazvu, oblasti nebo elementu',
  disabled = false,
}: WorkTypeCommandPaletteProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    if (disabled) {
      return
    }

    function onKeyDown(event: KeyboardEvent) {
      const target = event.target
      const isEditable =
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          target instanceof HTMLInputElement ||
          target instanceof HTMLTextAreaElement ||
          target instanceof HTMLSelectElement)

      if (
        (event.key === 'k' || event.key === 'K') &&
        (event.metaKey || event.ctrlKey) &&
        !event.altKey
      ) {
        if (isEditable && !isOpen) {
          return
        }

        event.preventDefault()
        setIsOpen(true)
        return
      }

      if (event.key === 'Escape' && isOpen) {
        event.preventDefault()
        setIsOpen(false)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [disabled, isOpen])

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [isOpen])

  async function handleSelectWorkType(wtCode: string) {
    if (isSubmitting) {
      return
    }

    setIsSubmitting(true)
    try {
      await onSelect(wtCode)
      setIsOpen(false)
    } catch {
      // The caller surfaces the error and we keep the picker open.
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        disabled={disabled}
        className="group flex w-full items-center justify-between gap-4 rounded-[1.5rem] border border-slate-200 bg-white px-4 py-3 text-left shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
      >
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {triggerLabel}
          </p>
          <p className="mt-1 truncate text-sm text-slate-600">{triggerPlaceholder}</p>
        </div>

        <div className="hidden shrink-0 items-center gap-1.5 sm:flex">
          <kbd className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-500">
            Ctrl
          </kbd>
          <kbd className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-500">
            K
          </kbd>
        </div>
      </button>

      {isOpen ? (
        <div
          className="fixed inset-0 z-50 bg-slate-950/45 sm:p-6"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !isSubmitting) {
              setIsOpen(false)
            }
          }}
        >
          <div className="flex h-full items-stretch justify-center sm:items-start">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              aria-describedby={descriptionId}
              className="flex h-full w-full flex-col overflow-hidden bg-slate-50 sm:mt-[8vh] sm:h-auto sm:max-h-[82vh] sm:max-w-4xl sm:rounded-[2rem] sm:border sm:border-slate-200 sm:shadow-2xl"
            >
              <div className="border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p
                      id={titleId}
                      className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-600"
                    >
                      {title}
                    </p>
                    <p id={descriptionId} className="mt-2 max-w-2xl text-sm text-slate-600">
                      {description}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => setIsOpen(false)}
                    disabled={isSubmitting}
                    className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
                  >
                    Zavrit
                  </button>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-500">
                    Ctrl/Cmd + K
                  </span>
                  <span>Na mobilu se picker otevre pres celou obrazovku.</span>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5">
                <CaseWorkTypePicker
                  caseStatus={caseStatus}
                  autoFocusSearch
                  onSelect={(wtCode) => {
                    void handleSelectWorkType(wtCode)
                  }}
                />
              </div>

              {isSubmitting ? (
                <div className="border-t border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 sm:px-5">
                  Zakladam work item...
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
