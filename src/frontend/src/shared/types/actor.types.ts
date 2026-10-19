export type ActorRole = 'superadmin' | 'manager' | 'user'

export interface Actor {
  id: string
  email: string
  fullName: string
  role: ActorRole
  organizationId: string | null
  isActive?: boolean
  isSuperAdmin?: boolean
}
