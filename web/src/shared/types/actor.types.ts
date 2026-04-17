export type ActorRole = 'superadmin' | 'manager' | 'user'

export interface Actor {
  id: string
  email: string
  name: string
  role: ActorRole
  organizationId: string | null
}
