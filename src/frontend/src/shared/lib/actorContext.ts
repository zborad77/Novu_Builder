/**
 * Pure helper functions for identity/context checks.
 * These are NOT hooks — they receive an Actor object as argument.
 * Used by guards and UI rendering logic.
 *
 * Rule: no business-state exceptions here (case.status, tenant flags).
 * Those belong in the respective feature.
 */

import type { Actor } from '../types/actor.types'

export function isSuperAdmin(actor: Actor): boolean {
  return actor.role === 'superadmin'
}

export function hasOrganizationContext(actor: Actor): boolean {
  return actor.organizationId !== null
}

/** True for tenant users (manager/user) who have an org context. */
export function isEffectiveTenantActor(actor: Actor): boolean {
  return !isSuperAdmin(actor) && hasOrganizationContext(actor)
}

/**
 * Used by OrgGuard (jen směrování UI, o oprávněních rozhoduje core).
 * Superadmins are allowed on org-scoped routes even without organizationId.
 */
export function canAccessOrgScopedRoute(actor: Actor): boolean {
  return isSuperAdmin(actor) || hasOrganizationContext(actor)
}

/**
 * True when the actor is a superadmin operating in global admin context.
 */
export function isGlobalAdminContext(actor: Actor): boolean {
  return isSuperAdmin(actor)
}
