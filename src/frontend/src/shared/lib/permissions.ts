/**
 * Business-level permission checks.
 * Pure functions — receive Actor as argument, never use hooks.
 *
 * Rule: checks here must stay free of case-specific state (status, locked).
 * Case-ACL belongs in features/cases; tenant feature flags in their own helper.
 */

import type { Actor } from '../types/actor.types'
import { isSuperAdmin } from './actorContext'

export function canManageCase(actor: Actor, caseOrganizationId: string): boolean {
  return isSuperAdmin(actor) || actor.organizationId === caseOrganizationId
}

export function canCreateMarker(actor: Actor): boolean {
  return actor.role !== 'user' || isSuperAdmin(actor)
}

export function canManageCatalog(actor: Actor): boolean {
  return isSuperAdmin(actor) || actor.role === 'manager'
}

export function canAccessAdminPanel(actor: Actor): boolean {
  return isSuperAdmin(actor)
}

export function canImpersonate(actor: Actor): boolean {
  return isSuperAdmin(actor)
}
