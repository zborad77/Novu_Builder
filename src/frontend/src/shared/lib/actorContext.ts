/**
 * Pure helper functions for identity/context checks.
 * These are NOT hooks — they receive an Actor object as argument.
 * Used by permissions.ts, guards, and UI rendering logic.
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
 * Used by OrgGuard.
 * Superadmins are allowed on org-scoped routes even without organizationId
 * (they see all tenants or a specific one when impersonating).
 */
export function canAccessOrgScopedRoute(actor: Actor): boolean {
  return isSuperAdmin(actor) || hasOrganizationContext(actor)
}

/**
 * True when the actor is a superadmin operating in global admin context
 * (not impersonating a specific tenant user).
 */
export function isGlobalAdminContext(actor: Actor): boolean {
  return isSuperAdmin(actor)
}
