/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Authorization-Gated Components (Server-Side Decision)
// frontend/src/components/AdminPage.tsx
// Reference: docs/architecture/security-model.md § 2.4
//            docs/architecture/policy-engine-spec.md § 4

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/services/api-client'
import { ReactNode } from 'react'

/**
 * CRITICAL: Authorization decisions are made by the SERVER (Policy Engine).
 * Frontend should attempt the operation and handle 403 Forbidden response.
 *
 * WRONG Pattern:
 * - Check roles cached in useAuth hook
 * - Show/hide UI based on cached roles
 * - Problem: Roles can change at any moment; frontend is out of sync
 *
 * RIGHT Pattern:
 * - Make the API request
 * - Backend's Policy Engine evaluates authorization per-request
 * - If denied (403), show error message to user
 * - If allowed (200), proceed with operation
 *
 * See docs/architecture/security-model.md § 2.4:
 * "Session Is NOT an Authorization Cache (Hard Invariant)"
 */

interface AuthContextType {
  user: { id: string; email: string; tenant_id: string } | null
  isLoading: boolean
}

const AuthContext = React.createContext<AuthContextType | null>(null)

function AdminPage() {
  const auth = React.useContext(AuthContext)

  if (auth?.isLoading) {
    return <LoadingSpinner />
  }

  if (!auth?.user) {
    return <LoginPrompt />
  }

  // Instead of checking cached roles, make a request to a protected route
  // Let the backend return 403 if not authorized
  return <AdminContent userId={auth.user.id} tenantId={auth.user.tenant_id} />
}

/**
 * Protected component that attempts an operation and handles 403 response.
 *
 * The backend's Policy Engine determines authorization.
 * We don't pre-check on frontend (no cached roles).
 */
function AdminContent({ userId, tenantId }: { userId: string; tenantId: string }) {
  const { data: adminData, error, isLoading } = useQuery({
    queryKey: ['admin-dashboard', tenantId],
    queryFn: async () => {
      // Backend's Policy Engine will evaluate if user can access admin dashboard
      const response = await apiClient.get(`/api/v1/admin/dashboard`)
      return response.data
    },
    retry: (count, error: unknown): boolean => {
      // Don't retry on 403 (authorization failed)
      if (error instanceof Error && 'response' in error) {
        const httpError = error as Error & { response?: { status: number } }
        if (httpError.response?.status === 403) return false
      }
      return count < 3
    }
  })

  if (isLoading) {
    return <LoadingSpinner />
  }

  if (error) {
    const httpError = error instanceof Error && 'response' in error 
      ? (error as Error & { response?: { status: number } })
      : null
    if (httpError?.response?.status === 403) {
      return <AccessDenied reason="You do not have admin access." />
    }
    return <ErrorMessage error={error} />
  }

  return <AdminDashboard data={adminData} />
}

/**
 * PATTERN: Conditional UI Rendering Based on Server Response
 *
 * For features that require specific authorization, attempt the operation.
 * If denied, show an error message.
 *
 * ALTERNATIVELY: Check permissions by attempting a lightweight authorization check:
 */

function DeployButton({ tenantId }: { tenantId: string }) {
  const { data: canDeploy, isLoading } = useQuery({
    queryKey: ['can-deploy', tenantId],
    queryFn: async () => {
      try {
        // Try to check authorization without performing the actual operation
        // Backend could provide a lightweight check endpoint:
        // POST /api/v1/auth/check-authorization
        const response = await apiClient.post('/api/v1/auth/check-authorization', {
          resource: 'deployments',
          action: 'create'
        })
        return response.data.allowed
      } catch (error: unknown) {
        // If check fails with 403, user is not authorized
        if (error instanceof Error && 'response' in error) {
          const httpError = error as Error & { response?: { status: number } }
          if (httpError.response?.status === 403) return false
        }
        throw error
      }
    },
    staleTime: 0,  // Always fresh - roles/permissions change
    retry: false
  })

  if (isLoading) {
    return <Button disabled>Loading...</Button>
  }

  if (!canDeploy) {
    return null  // Hide button (or show disabled with tooltip)
  }

  return (
    <Button
      onClick={() => {
        // Attempt deployment; backend will validate authorization again
        // This ensures consistent evaluation
      }}
    >
      Deploy
    </Button>
  )
}

