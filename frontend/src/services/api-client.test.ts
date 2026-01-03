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

    const client = new ApiClient({ baseUrl: 'https://example.test' });
    const result = await client.get<{ ok: boolean }>('/ping');

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith('https://example.test/ping', {
      method: 'GET',
      credentials: 'include',
    });
  });

  it('throws for non-2xx responses', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('nope', { status: 403 })));

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    const client = new ApiClient({ baseUrl: 'https://example.test' });

    await expect(client.get('/forbidden')).rejects.toThrow('GET /forbidden failed: 403');
  });
});
