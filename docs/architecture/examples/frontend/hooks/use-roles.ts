/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Authorization Check Hook (Server-Side Only)
// frontend/src/hooks/useAuthorization.ts
// Reference: docs/architecture/security-model.md § 2.4
//            docs/architecture/policy-engine-spec.md § 4

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/services/api-client'

/**
 * CRITICAL: Authorization checks happen on the SERVER via Policy Engine.
 * Frontend should NOT cache roles or permissions.
 * Instead, make requests to the backend, which evaluates authorization.
 *
 * See docs/architecture/security-model.md § 2.4:
 * "Session Is NOT an Authorization Cache (Hard Invariant)"
 *
 * Pattern: Backend returns 403 Forbidden if not authorized.
 * Frontend displays appropriate error message.
 */

interface AuthorizationCheckRequest {
  resource: string
  action: string
  context?: Record<string, string | number | boolean>
}

interface AuthorizationDecision {
  allowed: boolean
  reason?: string
}

export function useAuthorization() {
  /**
   * Query the backend to check authorization.
   * Backend's Policy Engine evaluates at request time (no cached roles).
   *
   * NEVER cache the result - authorization state changes with roles/permissions.
   */
  const checkAuthorization = async (
    req: AuthorizationCheckRequest
  ): Promise<AuthorizationDecision> => {
    try {
      const response = await apiClient.post<AuthorizationDecision>(
        '/api/v1/auth/check-authorization',
        req
      )
      return response.data
    } catch (error: any) {
      // Backend denied authorization
      if (error.response?.status === 403) {
        return {
          allowed: false,
          reason: error.response?.data?.detail || 'Unauthorized'
        }
      }
      throw error
    }
  }

  /**
   * React Query hook for authorization check (with stale-while-revalidate).
   *
   * IMPORTANT: Set staleTime to ensure fresh evaluation.
   * Authorization state can change (roles assigned/revoked, permissions modified).
   */
  const checkAuthorizationQuery = (req: AuthorizationCheckRequest) =>
    useQuery({
      queryKey: ['authorization', req.resource, req.action, req.context],
      queryFn: () => checkAuthorization(req),
      staleTime: 0,  // Always consider stale - evaluate each time
      cacheTime: 0,  // Don't cache - roles/permissions change frequently
      retry: false
    })

  return {
    checkAuthorization,
    checkAuthorizationQuery
  }
}

/**
 * PATTERN: Conditional Rendering Based on Server Response
 *
 * WRONG (Forbidden):
 * const { isPlatformOwner } = useRoles()  // ❌ Cached roles
 * if (isPlatformOwner) { ... }
 *
 * RIGHT (Approved):
 * const { data: decision } = useAuthorization().checkAuthorizationQuery({
 *   resource: 'platform.settings',
 *   action: 'update'
 * })
 * if (decision?.allowed) { ... }
 *
 * Better: Let the backend route return 403, handle error in error boundary.
 * Don't pre-check authorization on frontend (adds latency, increases complexity).
 */

