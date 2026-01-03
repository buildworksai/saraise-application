export interface ApiClientOptions {
  baseUrl?: string;
}

export class ApiClient {
  private readonly baseUrl: string;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL ?? '');
  }

  async get<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`GET ${path} failed: ${response.status}`);
    }

    return (await response.json()) as T;
  }
}
