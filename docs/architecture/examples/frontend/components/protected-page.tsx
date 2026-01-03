/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Protected Page Component (Attempt + Error Handling)
// frontend/src/components/ProtectedPage.tsx
// Reference: docs/architecture/security-model.md § 2.4
//            docs/architecture/policy-engine-spec.md § 4

import { useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/services/api-client'

interface ProtectedPageProps {
  children: React.ReactNode
  pageResource: string  // e.g., 'billing', 'admin', 'users'
  pageAction?: string   // e.g., 'view', 'edit' (default: 'view')
  fallback?: React.ReactNode
}

/**
 * APPROVED: Protected Page Component
 *
 * CRITICAL: Authorization is evaluated by the SERVER (Policy Engine).
 * Frontend attempts to fetch the resource.
 * If denied (403), server returns error; component shows fallback.
 *
 * Do NOT use cached roles for authorization decisions.
 * See docs/architecture/security-model.md § 2.4:
 * "Session Is NOT an Authorization Cache (Hard Invariant)"
 */

export function ProtectedPage({
  children,
  pageResource,
  pageAction = 'view',
  fallback
}: ProtectedPageProps) {
  const navigate = useNavigate()

  // Check if user is authenticated by attempting to load user info
  const { data: user, isLoading: userLoading, error: userError } = useQuery({
    queryKey: ['user'],
    queryFn: () => apiClient.get('/api/v1/auth/user'),
    retry: false,
    staleTime: 60000  // Cache for 1 minute
  })

  // Attempt to access the protected resource
  // Backend's Policy Engine evaluates authorization
  const { data: pageData, error: pageError, isLoading: pageLoading } = useQuery({
    queryKey: ['protected-page', pageResource, pageAction],
    queryFn: () =>
      apiClient.post('/api/v1/auth/check-authorization', {
        resource: pageResource,
        action: pageAction
      }),
    enabled: !!user,  // Only check authorization after user is loaded
    retry: false,
    staleTime: 0  // Always fresh - authorization state changes
  })

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!userLoading && userError) {
      const statusCode = userError instanceof Error && 'response' in userError
        ? (userError as Error & { response?: { status: number } }).response?.status
        : null
      if (statusCode === 401) {
        navigate('/login')
      }
    }
  }, [userError, userLoading, navigate])

  if (userLoading || pageLoading) {
    return <div>Loading...</div>
  }

  if (userError) {
    const statusCode = userError instanceof Error && 'response' in userError
      ? (userError as Error & { response?: { status: number } }).response?.status
      : null
    if (statusCode === 401) {
      return null  // Redirecting to login
    }
    return fallback || <div>Error loading page</div>
  }

  if (!user) {
    return null  // Not authenticated
  }

  // Check authorization - backend's Policy Engine made the decision
  if (pageError) {
    const statusCode = (pageError as any).response?.status
    if (statusCode === 403) {
      // Not authorized for this resource
      return fallback || (
        <div>
          <h1>Access Denied</h1>
          <p>You do not have permission to access this page.</p>
        </div>
      )
    }
    return fallback || <div>Error loading page</div>
  }

  if (!pageData?.allowed) {
    return fallback || (
      <div>
        <h1>Access Denied</h1>
        <p>{pageData?.reason || 'You do not have permission to access this page.'}</p>
      </div>
    )
  }

  return <>{children}</>
}

/**
 * USAGE EXAMPLE:
 *
 * export default function BillingPage() {
 *   return (
 *     <ProtectedPage 
 *       pageResource="billing" 
 *       pageAction="view"
 *     >
 *       <BillingContent />
 *     </ProtectedPage>
 *   )
 * }
 *
 * Flow:
 * 1. Component checks user identity (useQuery for /auth/user)
 * 2. If not authenticated, redirects to /login
 * 3. Component checks authorization (POST /auth/check-authorization)
 * 4. Backend's Policy Engine evaluates at request time (no cached roles)
 * 5. If authorized, renders children
 * 6. If denied (403), renders fallback or "Access Denied" message
 *
 * Key Difference from Old Pattern:
 * - OLD: Check cached roles on frontend, conditionally render
 * - NEW: Attempt operation, handle 403 response with error boundary
 * - NEW approach ensures authorization is always fresh (Policy Engine evaluated per-request)
 */

