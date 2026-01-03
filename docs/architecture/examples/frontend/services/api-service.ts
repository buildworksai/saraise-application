/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Frontend API Service with Session Cookie Handling
// frontend/src/services/api-client.ts
// Reference: docs/architecture/authentication-and-session-management-spec.md

import { getApiUrl } from '@/lib/urls'

/**
 * API Client for server communication.
 *
 * CRITICAL: Session cookies are included automatically via credentials: 'include'.
 * NO manual token management (JWT, OAuth tokens) - sessions only.
 *
 * Session cookie contains:
 * - session_id (opaque identifier)
 * - user_id (from session data)
 * - email (from session data)
 * - tenant_id (from session data)
 *
 * See docs/architecture/authentication-and-session-management-spec.md
 */

interface RequestOptions extends RequestInit {
  timeout?: number
  retries?: number
}

class ApiClient {
  private baseUrl: string
  private defaultTimeout: number = 30000
  private maxRetries: number = 3

  constructor() {
    this.baseUrl = getApiUrl()
  }

  /**
   * Make HTTP request with session cookie included.
   *
   * CRITICAL: credentials: 'include' ensures session cookie is sent.
   * Server validates session and establishes user identity.
   * Authorization evaluated by Policy Engine on backend.
   */
  private async makeRequest<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const url = `${this.baseUrl}/api/v1${endpoint}`
    const timeout = options.timeout ?? this.defaultTimeout
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(url, {
        ...options,
        credentials: 'include',  // ✅ CRITICAL: Include session cookie
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      // Handle authorization errors
      if (response.status === 401) {
        // Session expired or invalid
        window.location.href = '/login'
        throw new Error('Session expired. Please log in again.')
      }

      if (response.status === 403) {
        // Authorization denied by Policy Engine
        throw new Error('Access denied. You do not have permission for this action.')
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail || `API error: ${response.status} ${response.statusText}`
        )
      }

      return (await response.json()) as T
    } catch (error: any) {
      clearTimeout(timeoutId)

      if (error.name === 'AbortError') {
        throw new Error('Request timeout')
      }

      throw error
    }
  }

  async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.makeRequest<T>(endpoint, {
      ...options,
      method: 'GET',
    })
  }

  async post<T>(endpoint: string, data?: any, options?: RequestOptions): Promise<T> {
    return this.makeRequest<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async put<T>(endpoint: string, data?: any, options?: RequestOptions): Promise<T> {
    return this.makeRequest<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.makeRequest<T>(endpoint, {
      ...options,
      method: 'DELETE',
    })
  }
}

export const apiClient = new ApiClient()

/**
 * PATTERN: Using API Client in Components
 *
 * Example: Fetch user's tenant data with session authentication
 *
 * const { data: tenant } = useQuery({
 *   queryKey: ['tenant'],
 *   queryFn: () => apiClient.get('/tenant/info')
 * })
 *
 * Session cookie is included automatically.
 * Backend validates session and authorizes request via Policy Engine.
 * If denied, apiClient throws 403 error (caught by error boundary).
 */

