import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/services/api-client';
import { IntegrationListPage } from '../pages/IntegrationPages';

const calls = vi.hoisted(() => ({ listIntegrations: vi.fn(), listConnectors: vi.fn() }));
vi.mock('../services/integration-platform-service', () => ({ integrationPlatformService: calls }));

const meta = { correlation_id: 'corr-page', timestamp: '2026-07-22T00:00:00Z', count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false };
function renderPage(path = '/integration-platform') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><IntegrationListPage /></MemoryRouter></QueryClientProvider>);
}

describe('IntegrationListPage governed states', () => {
  beforeEach(() => { vi.clearAllMocks(); calls.listConnectors.mockResolvedValue({ items: [], meta }); });

  it('renders a layout-preserving loading skeleton', () => {
    calls.listIntegrations.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByLabelText('Loading integrations')).toHaveAttribute('aria-busy', 'true');
  });

  it('distinguishes first-use empty and filtered-empty with reset', async () => {
    calls.listIntegrations.mockResolvedValue({ items: [], meta });
    const first = renderPage();
    expect(await screen.findByText('integrations')).toBeInTheDocument();
    first.unmount();
    renderPage('/integration-platform?status=active');
    expect(await screen.findByText('No matching integrations')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Reset filters' }));
    await waitFor(() => expect(calls.listIntegrations).toHaveBeenCalledTimes(3));
  });

  it('renders explicit 403 and correlation-aware retry behavior', async () => {
    calls.listIntegrations.mockRejectedValueOnce(new ApiError('Denied', 403, undefined, 'policy_denied', 'corr-denied')).mockResolvedValueOnce({ items: [], meta });
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('integrations')).toBeInTheDocument();
  });

  it('renders explicit tenant-safe 404 state', async () => {
    calls.listIntegrations.mockRejectedValue(new ApiError('Missing', 404, undefined, 'not_found', 'corr-missing'));
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Record not found' })).toBeInTheDocument();
  });

  it('submits server search and supports keyboard operation', async () => {
    calls.listIntegrations.mockResolvedValue({ items: [], meta });
    renderPage();
    const search = await screen.findByRole('textbox', { name: 'Search integrations' });
    fireEvent.change(search, { target: { value: 'warehouse' } });
    search.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(calls.listIntegrations).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'warehouse' })));
  });
});
