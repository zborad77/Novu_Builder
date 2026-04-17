import { create } from 'zustand'

/**
 * Viewer UI state — zoom, pan, marker interaction modes.
 *
 * RULES (enforced here, not by the type system):
 *  - currentImageId is NOT stored here. Source of truth = route param.
 *    Deep links, browser back/forward, and keyboard next/prev all rely on the URL.
 *  - Marker domain data (list, content) is NOT stored here — it lives in query cache.
 *    Only the UI interaction state (which marker is active, draft coords) lives here.
 */

interface DraftCoords {
  x: number // 0-1 normalised
  y: number // 0-1 normalised
}

interface ViewerState {
  zoom: number
  panX: number
  panY: number
  activeMarkerId: string | null
  isCreateMarkerMode: boolean
  draftMarkerCoords: DraftCoords | null
  showAiMarkers: boolean
  showUserMarkers: boolean

  // Actions
  setZoom: (zoom: number) => void
  setPan: (x: number, y: number) => void
  resetView: () => void
  setActiveMarkerId: (id: string | null) => void
  setCreateMarkerMode: (on: boolean) => void
  setDraftMarkerCoords: (coords: DraftCoords | null) => void
  toggleAiMarkers: () => void
  toggleUserMarkers: () => void
  /** Full reset when navigating away from viewer. */
  reset: () => void
}

const INITIAL: Pick<
  ViewerState,
  | 'zoom' | 'panX' | 'panY'
  | 'activeMarkerId' | 'isCreateMarkerMode' | 'draftMarkerCoords'
  | 'showAiMarkers' | 'showUserMarkers'
> = {
  zoom: 1,
  panX: 0,
  panY: 0,
  activeMarkerId: null,
  isCreateMarkerMode: false,
  draftMarkerCoords: null,
  showAiMarkers: true,
  showUserMarkers: true,
}

export const useViewerStore = create<ViewerState>((set) => ({
  ...INITIAL,

  setZoom: (zoom) => set({ zoom: Math.max(0.1, Math.min(zoom, 10)) }),
  setPan: (panX, panY) => set({ panX, panY }),
  resetView: () => set({ zoom: 1, panX: 0, panY: 0 }),
  setActiveMarkerId: (activeMarkerId) => set({ activeMarkerId }),
  setCreateMarkerMode: (isCreateMarkerMode) =>
    set({ isCreateMarkerMode, draftMarkerCoords: null }),
  setDraftMarkerCoords: (draftMarkerCoords) => set({ draftMarkerCoords }),
  toggleAiMarkers: () => set((s) => ({ showAiMarkers: !s.showAiMarkers })),
  toggleUserMarkers: () => set((s) => ({ showUserMarkers: !s.showUserMarkers })),
  reset: () => set(INITIAL),
}))
