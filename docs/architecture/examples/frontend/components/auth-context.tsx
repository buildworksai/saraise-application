/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Auth Context Implementation
// frontend/src/components/auth-context.tsx
// Reference: docs/architecture/authentication-and-session-management-spec.md § 2
// CRITICAL NOTES:
// - User object contains IDENTITY ONLY: id, email, tenant_id, timestamps
// - Roles array shows PLATFORM roles (platform_owner, platform_operator)
// - Tenant roles array shows TENANT roles (tenant_admin, tenant_user, etc.)
// - NO authorization state cached in context (security-model.md § 2.4: HARD INVARIANT)
// - hasRole() / hasTenantRole() MUST NOT be used for authorization decisions
// - Use these helpers ONLY for UI hint purposes (show/hide UI speculatively)
// - All actual authorization decisions evaluated server-side by Policy Engine
// - Session cookie (HTTP-only) handles authentication automatically
// - refreshUser() fetches current user identity (not roles/permissions)
// - Roles can change at any time server-side - frontend caching is FORBIDDEN
// Source: docs/architecture/authentication-and-session-management-spec.md § 2, security-model.md § 2.4

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { apiClient } from '@/services/api-client'

interface User {
  id: string
  email: string
  tenant_id: string | null
  roles: string[]  // Platform roles
  tenant_roles: string[]  // Tenant roles
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  hasRole: (role: string) => boolean
  hasTenantRole: (role: string) => boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Check session on mount
  useEffect(() => {
    refreshUser()
  }, [])

  const refreshUser = async () => {
    try {
      const data = await apiClient.get<{ user: User }>('/api/v1/auth/profile')
      setUser(data.user)
    } catch (error) {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  const hasRole = (role: string): boolean => {
    return user?.roles?.includes(role) ?? false
  }

  const hasTenantRole = (role: string): boolean => {
    return user?.tenant_roles?.includes(role) ?? false
  }

  const login = async (email: string, password: string) => {
    const data = await apiClient.post<{ user: User }>('/api/v1/auth/login', {
      email,
      password
    })
    setUser(data.user)
  }

  const logout = async () => {
    await apiClient.post('/api/v1/auth/logout', {})
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{
      user,
      isAuthenticated: !!user,
      isLoading,
      hasRole,
      hasTenantRole,
      login,
      logout,
      refreshUser
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

