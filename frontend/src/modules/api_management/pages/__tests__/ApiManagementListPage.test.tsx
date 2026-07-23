import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiManagementListPage } from '../ApiManagementListPage';
import { api_managementService } from '../../services/api_management-service';
import { configuration, page, resource } from './test-fixtures';

vi.mock('../../services/api_management-service');
const navigate = vi.fn();
vi.mock('react-router-dom', async () => ({ ...(await vi.importActual<typeof ReactRouterDom>('react-router-dom')), useNavigate: () => navigate }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BrowserRouter><ApiManagementListPage /></BrowserRouter></QueryClientProvider>);
}

describe('ApiManagementListPage', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(api_managementService.getRuntimeConfiguration).mockResolvedValue(configuration); });

  it('renders tenant-configured loading state', async () => {
    vi.mocked(api_managementService.listResources).mockImplementation(() => new Promise(() => undefined));
    renderPage();
    expect(await screen.findByRole('status', { name: /loading resources/i })).toBeInTheDocument();
  });

  it('renders an empty state', async () => {
    vi.mocked(api_managementService.listResources).mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByText(/no resources yet/i)).toBeInTheDocument();
  });

  it('renders typed resources and performs server-side search', async () => {
    vi.mocked(api_managementService.listResources).mockResolvedValue(page([resource({ name: 'Apple' }), resource({ id: '00000000-0000-4000-8000-000000000002', name: 'Banana' })]));
    renderPage();
    expect(await screen.findByText('Apple')).toBeInTheDocument();
    await userEvent.type(screen.getByRole('textbox', { name: /search resources/i }), 'Banana');
    await waitFor(() => expect(api_managementService.listResources).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'Banana' })));
  });
});
