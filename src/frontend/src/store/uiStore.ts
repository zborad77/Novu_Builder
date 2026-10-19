import { create } from 'zustand'

/**
 * Pure shell / navigation UI state.
 *
 * RULES:
 *  - Server data does NOT belong here (use query cache).
 *  - Active tab does NOT go here when tabs are route-driven (URL = source of truth).
 *  - currentImageId does NOT go here (route param = source of truth).
 */

interface UIState {
  sidebarOpen: boolean
  mobileMenuOpen: boolean

  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
  setMobileMenuOpen: (open: boolean) => void
  closeMobileMenu: () => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  mobileMenuOpen: false,

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setMobileMenuOpen: (open) => set({ mobileMenuOpen: open }),
  closeMobileMenu: () => set({ mobileMenuOpen: false }),
}))
