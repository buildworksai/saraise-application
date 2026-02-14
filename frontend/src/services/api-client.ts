import { ENDPOINTS as AUTH_ENDPOINTS } from './auth-contracts';

export interface ApiClientOptions {
  baseUrl?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private readonly baseUrl: string;

  constructor(options: ApiClientOptions = {}) {
    // CRITICAL: Endpoints already include /api prefix, so baseUrl should be empty
    // Vite dev server proxies /api/* to http://localhost:28000/api/*
    // This ensures session cookies work correctly (SameSite=Lax instead of SameSite=None)
    // In production, this should be configured via nginx or similar
    const envBaseUrl = import.meta.env.VITE_API_BASE_URL;
    this.baseUrl = options.baseUrl ?? (envBaseUrl && envBaseUrl !== '' ? envBaseUrl : '');
  }

  /**
   * Get CSRF token from cookie
   */
  private getCsrfToken(): string | null {
    // CSRF token is stored in cookie named 'saraise_csrftoken'
    const name = 'saraise_csrftoken';
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop()?.split(';').shift() || null;
    }
    return null;
  }

  private async request<T>(
    path: string,
    method: string,
    body?: unknown,
    init: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string>),
    };

    // Add CSRF token for authenticated requests (all except login)
    // Login endpoint uses CsrfExemptSessionAuthentication
    const csrfToken = this.getCsrfToken();
    if (csrfToken && path !== AUTH_ENDPOINTS.LOGIN) {
      headers['X-CSRFToken'] = csrfToken;
    }

    const config: RequestInit = {
      ...init,
      method,
      headers,
      credentials: 'include', // Include session cookies
    };

    if (body !== undefined) {
      config.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${path}`, config);

    if (!response.ok) {
      let errorMessage = `${method} ${path} failed: ${response.status}`;
      let errorDetails: unknown;

      try {
        const errorData: unknown = await response.json();
        if (errorData && typeof errorData === 'object') {
          const data = errorData as Record<string, unknown>;
          const message = typeof data.message === 'string' ? data.message : undefined;
          const error = typeof data.error === 'string' ? data.error : undefined;
          errorMessage = message ?? error ?? errorMessage;
        }
        errorDetails = errorData;
      } catch {
        // If response is not JSON, use status text
        errorMessage = response.statusText ?? errorMessage;
      }

      // CRITICAL: backend session is the source of truth.
      // Only auto-logout on 401 (Unauthorized) - this means not authenticated.
      // 403 (Forbidden) can mean "not authorized" (permission issue), not "not authenticated".
      // Exception: For auth/me endpoint, 403 means not authenticated, so logout.
      if (response.status === 401 || (response.status === 403 && path === AUTH_ENDPOINTS.ME)) {
        try {
          const { useAuthStore } = await import('@/stores/auth-store');
          useAuthStore.getState().logout();
        } catch {
          // Best-effort only. Never block error propagation.
        }
      }

      throw new ApiError(errorMessage, response.status, errorDetails);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  async get<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, 'GET', undefined, init);
  }

  async post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, 'POST', body, init);
  }

  async put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, 'PUT', body, init);
  }

  async patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, 'PATCH', body, init);
  }

  async delete<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, 'DELETE', undefined, init);
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
