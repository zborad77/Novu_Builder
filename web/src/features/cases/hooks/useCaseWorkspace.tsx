import { createContext, useContext, type ReactNode } from 'react'
import type { CaseDetail } from '../types/case.types'

interface CaseWorkspaceContextValue {
  caseDetail: CaseDetail
}

const CaseWorkspaceContext = createContext<CaseWorkspaceContextValue | null>(null)

interface CaseWorkspaceProviderProps {
  caseDetail: CaseDetail
  children: ReactNode
}

export function CaseWorkspaceProvider({
  caseDetail,
  children,
}: CaseWorkspaceProviderProps) {
  return (
    <CaseWorkspaceContext.Provider value={{ caseDetail }}>
      {children}
    </CaseWorkspaceContext.Provider>
  )
}

export function useCaseWorkspace(): CaseWorkspaceContextValue {
  const context = useContext(CaseWorkspaceContext)

  if (context === null) {
    throw new Error('useCaseWorkspace must be used within CaseWorkspaceProvider')
  }

  return context
}
