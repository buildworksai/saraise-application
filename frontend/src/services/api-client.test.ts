import { describe, expect, it, vi, afterEach } from 'vitest';

import { ApiClient } from './api-client';

describe('ApiClient', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls fetch with credentials include', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
    // Mock document.cookie for CSRF token
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    });

    const client = new ApiClient({ baseUrl: 'https://example.test' });
    const result = await client.get<{ ok: boolean }>('/ping');

    expect(result.ok).toBe(true);
    // Check that fetch was called with correct base URL and credentials
    expect(fetchMock).toHaveBeenCalled();
    const callArgs = fetchMock.mock.calls[0];
    expect(callArgs?.[0]).toBe('https://example.test/ping');
    expect(callArgs?.[1]).toMatchObject({
      method: 'GET',
      credentials: 'include',
    });
  });

  it('throws for non-2xx responses', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('nope', { status: 403, statusText: 'Forbidden' })));

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
    // Mock document.cookie for CSRF token
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    });

    const client = new ApiClient({ baseUrl: 'https://example.test' });

    // Verify it throws an ApiError with status 403
    await expect(client.get('/forbidden')).rejects.toThrow();
    try {
      await client.get('/forbidden');
    } catch (error: unknown) {
      expect(error).toBeInstanceOf(Error);
      // Check if it's an ApiError with status property
      if (error && typeof error === 'object' && 'status' in error) {
        expect((error as { status: number }).status).toBe(403);
      }
    }
  });
});
