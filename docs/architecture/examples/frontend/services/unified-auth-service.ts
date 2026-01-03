/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Session-Based Auth Service
// frontend/src/services/unified-auth-service.ts
// Reference: docs/architecture/authentication-and-session-management-spec.md § 2
// CRITICAL NOTES:
// - Sessions are server-managed and stateful (stored in Redis backend)
// - HTTP-only cookies prevent XSS attacks on session_id
// - No JWT tokens, OAuth tokens, or other bearer tokens used for interactive users
// - Credentials: 'include' ensures session cookies sent with every request
// - Session establishes IDENTITY ONLY (user_id, email, tenant_id) - NO authorization cached
// - Authorization decisions evaluated per-request via Policy Engine on backend
// - Session rotation happens server-side on login/logout (security-model.md § 3.1)
// - Client-side session storage is FORBIDDEN - session state lives server-side only
// Source: docs/architecture/authentication-and-session-management-spec.md § 2, security-model.md § 3.1

class UnifiedAuthService {
  constructor(private apiClient: ApiClient) {}

  async login(email: string, password: string): Promise<LoginResponse> {
    // ✅ Authentication is platform-level service (not in modules)
    // Uses session-based auth only (no JWT, OAuth, or bearer tokens)
    const data = await this.apiClient.post<LoginResponse>('/auth/login', {
      email,
      password,
    });

    // Session is stored in HTTP-only cookie by the server
    // No client-side storage needed

    return data;
  }

  async logout(): Promise<void> {
    // Session cookie is cleared server-side
    await this.apiClient.post<void>('/auth/logout', {});
  }

  async getCurrentUser(): Promise<User | null> {
    try {
      const user = await this.apiClient.get<User>('/auth/profile');
      return user;
    } catch (error) {
      return null;
    }
  }
}

export const unifiedAuthService = new UnifiedAuthService();

