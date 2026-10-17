import { Link, useParams } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useCaseDetail } from 'features/cases'
import { usePhotos, CASE_KEYS } from 'features/cases/api/caseQueries'
import { saveAnalysisSelection, confirmMeasurement } from 'features/cases/api/caseApi'
import { useToast } from 'app/providers/ToastProvider'
import type { AnalysisResult, OverlaySelection, PolygonPoint } from 'shared/types/photo.types'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MaskOverlay({
  polygon,
  width,
  height,
  isRefreshing,
}: {
  polygon: PolygonPoint[]
  width: number
  height: number
  isRefreshing: boolean
}) {
  const points = polygon.map((p) => `${p.x},${p.y}`).join(' ')
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
      preserveAspectRatio="xMidYMid meet"
      style={{ opacity: isRefreshing ? 0.5 : 1, transition: 'opacity 0.2s' }}
    >
      <polygon
        points={points}
        fill="rgba(239, 68, 68, 0.22)"
        stroke="rgb(239, 68, 68)"
        strokeWidth="3"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function UserSelectionOverlay({
  polygon,
  width,
  height,
}: {
  polygon: PolygonPoint[]
  width: number
  height: number
}) {
  const points = polygon.map((p) => `${p.x},${p.y}`).join(' ')
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
      preserveAspectRatio="xMidYMid meet"
    >
      <polygon
        points={points}
        fill="rgba(16, 185, 129, 0.20)"
        stroke="rgb(16, 185, 129)"
        strokeWidth="3"
        strokeDasharray="8 4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function AnalysisField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="font-medium text-slate-900">{value}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PhotoViewerPage() {
  const { caseId, imageId } = useParams({ strict: false })
  const { data: photosData, isLoading, isError } = usePhotos(caseId ?? '')
  const { data: caseDetail, isFetching: isDetailFetching } = useCaseDetail(caseId ?? '')
  const { toast } = useToast()
  const queryClient = useQueryClient()

  // ---------------------------------------------------------------------------
  // P3: OverlaySelection — anchored to latestAnalysis.id.
  //
  // Invariant: if latestAnalysis.id changes (new analysis run), the user's
  // local selection is automatically stale and must be cleared.  This holds
  // across: overlay refresh, reconnect, proposal recompute, replay.
  // The selection anchor is compared on every render — no manual cleanup needed.
  //
  // Qt parity: C++ viewer must implement the same anchor check before committing
  // a selectedRepairPolygon to the backend.
  // ---------------------------------------------------------------------------
  const [userSelection, setUserSelection] = useState<OverlaySelection | null>(null)

  // Stable ref so the analysis-change effect can read the latest selection
  // without being declared as a dependency (avoids spurious effect re-runs).
  const userSelectionRef = useRef<OverlaySelection | null>(null)
  userSelectionRef.current = userSelection

  // Declared before the effects below: both read it, and a dependency array is
  // evaluated during render, so a later `const` would be in the temporal dead
  // zone and throw on every render.
  const latestAnalysisId = caseDetail?.latestAnalysis?.id

  // Clear selection when the displayed photo or analysis changes, and restore
  // a confirmed manual selection from the backend if one exists for this photo.
  // Runs on mount (imageId known, latestAnalysisId undefined → no hydration),
  // then again when data loads (latestAnalysisId becomes defined → hydration),
  // and again on photo navigation or new analysis arrival.
  useEffect(() => {
    setUserSelection(null)
    setSaveStatus('idle')
    const analysis = caseDetail?.latestAnalysis
    if (
      analysis?.finalAreaSource === 'manual' &&
      analysis.selectedRepairPolygon != null &&
      analysis.selectedRepairPolygon.length >= 3 &&
      analysis.referencePhotoId === imageId
    ) {
      setUserSelection({
        analysisId: analysis.id,
        polygon: analysis.selectedRepairPolygon,
        confirmedAreaSqm: analysis.manualAreaSqm,
      })
      setSaveStatus('confirmed')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageId, latestAnalysisId])

  // P3 (multi-user): when another user's analysis run completes, the overlay
  // identity changes.  If the local user had a selection anchored to the old
  // analysis ID, it is now stale (selectionIsLive will become false this render).
  // Notify them so they understand why their drawing disappeared.
  const prevAnalysisIdRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    const prev = prevAnalysisIdRef.current
    prevAnalysisIdRef.current = latestAnalysisId
    if (prev !== undefined && prev !== latestAnalysisId && latestAnalysisId !== undefined) {
      if (userSelectionRef.current?.analysisId === prev) {
        toast.warning('Analysis updated — your selection was reset.')
      }
    }
  // toast is stable (useCallback in ToastProvider); latestAnalysisId is the
  // only value that gates when this fires.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestAnalysisId])

  // ---------------------------------------------------------------------------
  // Selection persistence.
  //
  // When userSelection is non-null, auto-save to the backend with a 400ms
  // debounce (ready for future drawing UX where the selection can change
  // rapidly).  An AbortController cancels the in-flight request whenever the
  // selection changes or the component unmounts.
  //
  // 409 ANALYSIS_STALE: the backend rejected our write because a newer
  // analysis result exists.  Clear the local selection, show a warning, and
  // invalidate so the UI refetches the latest overlay.
  // ---------------------------------------------------------------------------
  // 'confirmed' = domain commit complete (manualAreaSqm set, finalAreaSource = 'manual')
  type SaveStatus = 'idle' | 'saving' | 'saved' | 'confirmed' | 'error'
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const saveAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!userSelection || !caseId) {
      setSaveStatus('idle')
      return
    }

    // setTimeout expects a void-returning callback, so the async work is a named
    // function the timer fires with an explicit `void`.
    const runSave = async () => {
      saveAbortRef.current?.abort()
      const controller = new AbortController()
      saveAbortRef.current = controller

      setSaveStatus('saving')
      try {
        // Step 1: save polygon (+ manualAreaSqm when the user confirmed the
        // AI area — this makes the selection a pricing artefact).
        await saveAnalysisSelection(
          caseId,
          userSelection.analysisId,
          {
            polygon: userSelection.polygon,
            ...(userSelection.confirmedAreaSqm != null
              ? { manualAreaSqm: userSelection.confirmedAreaSqm }
              : {}),
          },
          controller.signal,
        )
        if (controller.signal.aborted) {
          if (saveAbortRef.current === controller) setSaveStatus('idle')
          return
        }

        // Step 2 (domain commit): confirm when the area was explicitly set.
        // Marks finalAreaSource = 'manual' so the selection feeds into pricing.
        if (userSelection.confirmedAreaSqm != null) {
          await confirmMeasurement(userSelection.analysisId, controller.signal)
          if (controller.signal.aborted) {
            if (saveAbortRef.current === controller) setSaveStatus('idle')
            return
          }
          setSaveStatus('confirmed')
        } else {
          setSaveStatus('saved')
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) {
          if (saveAbortRef.current === controller) setSaveStatus('idle')
          return
        }
        const httpStatus = (err as { response?: { status?: number } })?.response?.status
        const errorCode = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        if (httpStatus === 409 && errorCode === 'CASE_FINALIZED') {
          setSaveStatus('idle')
          setUserSelection(null)
          toast.warning('Case is finalized — selection can no longer be changed.')
        } else if (httpStatus === 409) {
          setUserSelection(null)
          setSaveStatus('idle')
          void queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(caseId) })
          toast.warning('Analysis was updated — please review the new result.')
        } else {
          setSaveStatus('error')
          toast.error('Failed to save selection. Please try again.')
        }
      }
    }
    const timerId = setTimeout(() => { void runSave() }, 400)

    return () => {
      clearTimeout(timerId)
      saveAbortRef.current?.abort()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userSelection])

  if (!caseId || !imageId) return null

  if (isLoading) {
    return (
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <div className="aspect-video w-full animate-pulse rounded-2xl bg-slate-200" />
      </section>
    )
  }

  if (isError || !photosData) {
    return (
      <section className="rounded-[2rem] border border-red-100 bg-red-50 p-6">
        <p className="text-sm text-red-600">Failed to load photo.</p>
      </section>
    )
  }

  const photos = photosData.items
  const photo = photos.find((p) => p.id === imageId)

  if (!photo) {
    return (
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <p className="text-sm text-slate-500">Photo not found.</p>
        <Link
          to="/cases/$caseId/photos"
          params={{ caseId }}
          className="mt-4 inline-block text-sm text-emerald-700 underline-offset-2 hover:underline"
        >
          ← Back to photos
        </Link>
      </section>
    )
  }

  const latestAnalysis: AnalysisResult | null | undefined = caseDetail?.latestAnalysis
  const aiInput = photo.variants.aiInput

  // ---------------------------------------------------------------------------
  // P1 + P2: Stale-safe overlay guard.
  //
  // The overlay is ONLY projected when all four conditions hold:
  //   1. maskPolygon is present and non-empty
  //   2. referencePhotoId matches the currently-displayed imageId  ← stale guard
  //   3. aiInput dimensions are known (needed for viewBox)
  //
  // This guard is deterministic regardless of when analysis.completed arrives,
  // when the user navigates, or when the cache refetches.  No ghost overlays
  // are possible as long as referencePhotoId and imageId are both correct.
  //
  // P2 (overlay lifecycle): keying the SVG on latestAnalysis.id forces React to
  // fully unmount/remount the overlay when the analysis identity changes
  // (new run, polygon changed, reference photo changed).  No residual state.
  // ---------------------------------------------------------------------------
  const overlayGuardPasses =
    latestAnalysis?.maskPolygon != null &&
    latestAnalysis.maskPolygon.length >= 3 &&
    latestAnalysis.referencePhotoId === imageId &&
    aiInput.width != null &&
    aiInput.height != null

  // P3: auto-clear user selection when analysis identity changes.
  // If userSelection.analysisId no longer matches the latest analysis id,
  // the selection is stale.  We derive this rather than storing it explicitly.
  const selectionIsLive =
    userSelection !== null &&
    latestAnalysis?.id === userSelection.analysisId &&
    latestAnalysis?.referencePhotoId === imageId

  // Show the user selection (green dashed) when live; otherwise the AI mask (red).
  const showUserSelection = selectionIsLive && userSelection !== null
  const showAiMask = overlayGuardPasses && !showUserSelection

  // Use aiInput image when projecting an overlay — coordinate spaces match exactly.
  // Fall back to preview/original for display-only photos.
  const displayUrl = overlayGuardPasses
    ? (aiInput.url ?? photo.variants.preview.url ?? photo.url)
    : (photo.variants.preview.url ?? photo.url)

  const currentIndex = photos.findIndex((p) => p.id === imageId)
  const prevPhoto = currentIndex > 0 ? photos[currentIndex - 1] : null
  const nextPhoto = currentIndex < photos.length - 1 ? photos[currentIndex + 1] : null

  // P1: isDetailFetching true while a background refetch is in flight after
  // analysis.completed invalidation.  The overlay dims (opacity 0.5) during
  // this window so the user sees the data is being updated.
  const isOverlayRefreshing = isDetailFetching && overlayGuardPasses

  return (
    <section className="space-y-4 rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
      {/* Nav row */}
      <div className="flex items-center justify-between">
        <Link
          to="/cases/$caseId/photos"
          params={{ caseId }}
          className="text-sm font-medium text-slate-600 underline-offset-2 hover:text-emerald-700 hover:underline"
        >
          ← All photos
        </Link>
        <div className="flex gap-2">
          {prevPhoto ? (
            <Link
              to="/cases/$caseId/photos/$imageId"
              params={{ caseId, imageId: prevPhoto.id }}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700"
            >
              ← Prev
            </Link>
          ) : null}
          {nextPhoto ? (
            <Link
              to="/cases/$caseId/photos/$imageId"
              params={{ caseId, imageId: nextPhoto.id }}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700"
            >
              Next →
            </Link>
          ) : null}
        </div>
      </div>

      {/* Image + overlay */}
      <div className="relative overflow-hidden rounded-2xl bg-slate-950">
        <img
          src={displayUrl}
          alt={photo.originalFilename}
          className="mx-auto block max-h-[70vh] w-full object-contain"
        />

        {/* P2: key on latestAnalysis.id forces full remount when analysis changes */}
        {showAiMask &&
          latestAnalysis?.maskPolygon &&
          aiInput.width != null &&
          aiInput.height != null ? (
          <MaskOverlay
            key={latestAnalysis.id ?? 'ai-mask'}
            polygon={latestAnalysis.maskPolygon}
            width={aiInput.width}
            height={aiInput.height}
            isRefreshing={isOverlayRefreshing}
          />
        ) : null}

        {/* P3: user-drawn repair polygon (green dashed) */}
        {showUserSelection &&
          latestAnalysis &&
          aiInput.width != null &&
          aiInput.height != null ? (
          <UserSelectionOverlay
            key={`user-${latestAnalysis.id}`}
            polygon={userSelection.polygon}
            width={aiInput.width}
            height={aiInput.height}
          />
        ) : null}

        {/* P1: refreshing indicator */}
        {isOverlayRefreshing && (
          <div className="absolute right-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
            Refreshing…
          </div>
        )}
      </div>

      {/* Photo badges */}
      <div className="flex flex-wrap items-center gap-2">
        {photo.isPrimary && (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-800">
            Primary
          </span>
        )}
        {photo.isAnalysisReference && (
          <span className="rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-violet-800">
            Analysis reference
          </span>
        )}
        {photo.processingStatus !== 'ready' && (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-800">
            {photo.processingStatus}
          </span>
        )}

        {/* Confirm AI area — visible when the AI mask is shown but no user selection is active.
            Captures estimatedAreaSqm so the save flow can set manualAreaSqm and call
            POST /confirm, making the selection a pricing artefact (domain commit). */}
        {overlayGuardPasses && !showUserSelection && latestAnalysis?.maskPolygon && (
          <button
            type="button"
            className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700 transition hover:bg-violet-100"
            onClick={() => {
              if (latestAnalysis?.id && latestAnalysis.maskPolygon) {
                setUserSelection({
                  analysisId: latestAnalysis.id,
                  polygon: latestAnalysis.maskPolygon,
                  confirmedAreaSqm: latestAnalysis.estimatedAreaSqm,
                })
              }
            }}
          >
            Confirm AI area
          </button>
        )}

        {/* Active selection controls */}
        {showUserSelection && (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-800">
            {saveStatus === 'saving'
              ? 'Saving…'
              : saveStatus === 'confirmed'
                ? 'Confirmed ✓'
                : saveStatus === 'saved'
                  ? 'Saved'
                  : saveStatus === 'error'
                    ? 'Save error'
                    : 'Manual repair area'}
          </span>
        )}
        {showUserSelection && (
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:border-red-300 hover:text-red-600"
            onClick={() => { setUserSelection(null); setSaveStatus('idle') }}
          >
            Reset to AI
          </button>
        )}
      </div>

      {/* Analysis panel — only for the reference photo */}
      {latestAnalysis && latestAnalysis.referencePhotoId === imageId && (
        <div className="rounded-2xl border border-violet-100 bg-violet-50/60 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-violet-600">
              Analysis result
            </p>
            {isDetailFetching && (
              <span className="text-xs text-violet-400">Updating…</span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            {latestAnalysis.objectType ? (
              <AnalysisField label="Object" value={latestAnalysis.objectType} />
            ) : null}
            {latestAnalysis.surfaceCondition ? (
              <AnalysisField label="Condition" value={latestAnalysis.surfaceCondition} />
            ) : null}
            {latestAnalysis.recommendedScope ? (
              <AnalysisField label="Scope" value={latestAnalysis.recommendedScope} />
            ) : null}
            {latestAnalysis.estimatedAreaSqm != null ? (
              <AnalysisField
                label="Est. area"
                value={`${latestAnalysis.estimatedAreaSqm.toFixed(1)} m²`}
              />
            ) : null}
            {latestAnalysis.workTypeCode ? (
              <AnalysisField label="Work type" value={latestAnalysis.workTypeCode} />
            ) : null}
            {latestAnalysis.areaConfidence != null ? (
              <AnalysisField
                label="Confidence"
                value={`${Math.round(latestAnalysis.areaConfidence * 100)}%`}
              />
            ) : null}
          </div>
        </div>
      )}

      <p className="text-xs text-slate-400">{photo.originalFilename}</p>
    </section>
  )
}
