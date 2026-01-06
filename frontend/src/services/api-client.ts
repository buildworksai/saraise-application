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
    this.baseUrl = options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:18000');
  }

  private async request<T>(
    path: string,
    method: string,
    body?: unknown,
    init: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...init.headers,
    };

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
      // If server says we're not authenticated/authorized, force-clear persisted auth state
      // to avoid "logged in UI + 403 API" confusion.
      if (response.status === 401 || response.status === 403) {
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
