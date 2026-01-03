/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Complete Frontend Testing Examples
// frontend/src/__tests__/auth.test.tsx
// Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Test Coverage)
// CRITICAL NOTES:
// - Test coverage MUST be ≥90% (engineering-governance-and-pr-controls.md § 2.2)
// - Session-based auth MUST be tested (no JWT mocking)
// - Mock fetch API calls (network isolation for unit tests)
// - Mock React Router hooks (useNavigate, useLocation, useParams)
// - TestComponent demonstrates auth hook usage patterns
// - Test authentication success/failure paths
// - Test authorization checks (Policy Engine server-side evaluation)
// - Test session expiration and automatic logout
// - Test MFA flows (step-up authentication)
// - Test error handling and user feedback (toast notifications)
// - All security-sensitive code MUST have high test coverage
// Source: docs/architecture/engineering-governance-and-pr-controls.md § 3

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from '@/hooks/use-auth'
import { config } from '@/lib/config'

// Mock fetch
global.fetch = jest.fn()

// Mock React Router
jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: '/' }),
  useParams: () => ({}),
}))

// Test component that uses auth
function TestComponent() {
  const { user, isAuthenticated, login, logout, hasRole } = useAuth()

  return (
    <div>
      <div data-testid="auth-status">
        {isAuthenticated ? 'Authenticated' : 'Not Authenticated'}
      </div>
      <div data-testid="user-email">{user?.email || 'No user'}</div>
      <div data-testid="has-admin-role">
        {hasRole('platform_owner') ? 'Yes' : 'No'}
      </div>
      <button onClick={() => login('test@example.com', 'password')}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

// Test wrapper
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
      </AuthProvider>
    </QueryClientProvider>
  )
}

describe('Authentication', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should show not authenticated initially', () => {
    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    )

    expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated')
    expect(screen.getByTestId('user-email')).toHaveTextContent('No user')
  })

  it('should handle successful login', async () => {
    const mockResponse = {
      user: {
        id: 'user-123',
        email: 'test@example.com',
        tenant_id: 'tenant-123',
        roles: ['platform_owner'],
        tenant_roles: ['tenant_admin']
      }
    }

    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    })

    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    )

    fireEvent.click(screen.getByText('Login'))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        `${config.api.baseUrl}/auth/login`,
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json'
          }
        })
      )
    })

    // Session is stored in HTTP-only cookie by server, not in localStorage
    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated')
    })
  })

  it('should handle login failure', async () => {
    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 401,
    })

    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    )

    fireEvent.click(screen.getByText('Login'))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled()
    })

    // Should still be not authenticated
    expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated')
  })

  it('should handle logout', async () => {
    // Mock existing session via profile endpoint
    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user: {
          id: 'user-123',
          email: 'test@example.com',
          tenant_id: 'tenant-123',
          roles: ['platform_owner'],
          tenant_roles: ['tenant_admin']
        }
      }),
    })

    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    )

    // Wait for initial auth check
    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated')
    })

    // Mock logout response
    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
    })

    fireEvent.click(screen.getByText('Logout'))

    // Session cookie is cleared by server
    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated')
    })
  })

  it('should check user roles correctly', async () => {
    // Mock authenticated user with admin role
    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user: {
          id: 'user-123',
          email: 'test@example.com',
          tenant_id: 'tenant-123',
          roles: ['platform_owner'],
          tenant_roles: ['tenant_admin']
        }
      }),
    })

    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId('has-admin-role')).toHaveTextContent('Yes')
    })
  })
})

// Run tests with: npm test

