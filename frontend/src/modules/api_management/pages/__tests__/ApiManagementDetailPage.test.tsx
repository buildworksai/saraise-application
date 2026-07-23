import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@/services/api-client';
import { ApiManagementDetailPage } from '../ApiManagementDetailPage';
import { api_managementService } from '../../services/api_management-service';
import { configuration, resource } from './test-fixtures';

vi.mock('../../services/api_management-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', async () => ({ ...(await vi.importActual<typeof ReactRouterDom>('react-router-dom')), useParams: () => ({ id: 'resource-id' }), useNavigate: () => vi.fn() }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BrowserRouter><ApiManagementDetailPage /></BrowserRouter></QueryClientProvider>);
}

describe('ApiManagementDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api_managementService.getRuntimeConfiguration).mockResolvedValue(configuration);
    vi.mocked(api_managementService.listResourceVersions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it('renders complete resource details', async () => {
    vi.mocked(api_managementService.getResource).mockResolvedValue(resource({ name: 'Test resource', description: 'Test description', config: { key: 'value' } }));
    renderPage();
    expect(await screen.findByText('Test resource')).toBeInTheDocument();
    expect(screen.getByText('Test description')).toBeInTheDocument();
  });

  it('keeps not-found distinct from retryable failures', async () => {
    vi.mocked(api_managementService.getResource).mockRejectedValue(new ApiError('Not found', 404));
    renderPage();
    expect(await screen.findByText('Resource not found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });
});
