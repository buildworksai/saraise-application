/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Component-Level Gating
// frontend/src/components/component-level-gating.tsx
// Reference: docs/architecture/security-model.md § 2.4 (Authorization)
// CRITICAL NOTES:
// - Component gating is UI HINT ONLY (speculative rendering)
// - Do NOT use cached roles for actual authorization decisions
// - Use hooks like useRoles() ONLY for show/hide UI conditionally
// - NEVER skip server-side validation based on cached roles
// - All data mutations MUST be authorized server-side (Policy Engine)
// - Disabled buttons provide user feedback but are not security controls
// - Hiding UI for unauthorized operations is UX improvement ONLY
// - Backend MUST enforce authorization even if frontend shows action (security-model.md § 2.4)
// - Roles can change between client render and API call - handle 403 errors gracefully
// Source: docs/architecture/security-model.md § 2.4, policy-engine-spec.md § 4

import { useRoles } from '@/hooks/use-roles'

export function AdminActions() {
  const { isTenantAdmin, isPlatformOwner } = useRoles()

  if (!isTenantAdmin && !isPlatformOwner) {
    return null  // Hide completely
  }

  return (
    <div>
      <button>Delete User</button>
      <button>Manage Roles</button>
    </div>
  )
}

export function DeployButton() {
  const { canDeploy } = useRoles()

  return (
    <button disabled={!canDeploy}>
      Deploy Workflow
    </button>
  )
}

