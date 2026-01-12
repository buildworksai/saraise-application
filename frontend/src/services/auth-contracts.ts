/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Authentication Service Contracts
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on authentication.
 * All types and endpoints for authentication are defined here.
 *
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import type { User } from '../stores/auth-store';

// =============================================================================
// EXPORTED TYPES
// =============================================================================

// Re-export User type from auth-store for consistency
export type { User };

/** Login request payload */
export interface LoginRequest {
  email: string;
  password: string;
  mfa_token?: string;
}

/** Login response */
export interface LoginResponse {
  user: User;
  session_id: string;
}

/** Current user response */
export interface CurrentUserResponse {
  user: User;
}

/** Register request payload */
export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
  company_name?: string;
}

/** Forgot password request */
export interface ForgotPasswordRequest {
  email: string;
}

/** Reset password request */
export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

// =============================================================================
// ENDPOINT REGISTRY
// =============================================================================

/**
 * All Authentication API endpoints.
 * Use these constants instead of hardcoding URLs.
 */
export const ENDPOINTS = {
  /** POST - Login with credentials */
  LOGIN: '/api/v1/auth/login/',
  /** POST - Logout current session */
  LOGOUT: '/api/v1/auth/logout/',
  /** GET - Get current authenticated user */
  ME: '/api/v1/auth/me/',
  /** POST - Refresh session validity */
  REFRESH: '/api/v1/auth/refresh/',
  /** POST - Register new user account */
  REGISTER: '/api/v1/auth/register/',
  /** POST - Request password reset email */
  FORGOT_PASSWORD: '/api/v1/auth/forgot-password/',
  /** POST - Reset password with token */
  RESET_PASSWORD: '/api/v1/auth/reset-password/',
} as const;

// =============================================================================
// EXAMPLES
// =============================================================================

/**
 * EXAMPLES - Type-safe examples for AI agents
 *
 * These examples use `satisfies` to ensure type correctness at compile time.
 */
export const EXAMPLES = {
  login: {
    request: {
      email: 'user@example.com',
      password: 'securePassword123',
    } satisfies LoginRequest,
    response: {
      user: {
        id: 'user-uuid-123',
        email: 'user@example.com',
        username: 'johndoe',
        is_staff: false,
        is_superuser: false,
        tenant_id: 'tenant-uuid-456',
        platform_role: null,
        tenant_role: 'user',
      },
      session_id: 'session-uuid-789',
    } as LoginResponse,
  },
  register: {
    request: {
      name: 'Jane Doe',
      email: 'jane@example.com',
      password: 'securePassword123',
      company_name: 'Acme Corp',
    } satisfies RegisterRequest,
    response: {
      user: {
        id: 'user-uuid-456',
        email: 'jane@example.com',
        username: 'janedoe',
        is_staff: false,
        is_superuser: false,
        tenant_id: 'tenant-uuid-789',
        platform_role: null,
        tenant_role: 'user',
      },
      session_id: 'session-uuid-012',
    } as LoginResponse,
  },
} as const;
