import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateApiManagementResourcePage } from '../CreateApiManagementResourcePage';
import { api_managementService } from '../../services/api_management-service';
import { configuration, resource } from './test-fixtures';

vi.mock('../../services/api_management-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', async () => ({ ...(await vi.importActual<typeof ReactRouterDom>('react-router-dom')), useNavigate: () => vi.fn() }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BrowserRouter><CreateApiManagementResourcePage /></BrowserRouter></QueryClientProvider>);
}

describe('CreateApiManagementResourcePage', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(api_managementService.getConfiguration).mockResolvedValue(configuration); });

  it('loads configured defaults and limits', async () => {
    renderPage();
    const name = await screen.findByLabelText('Name');
    expect(name).toHaveAttribute('maxlength', String(configuration.document.resource_name_max_length));
    expect(screen.getByLabelText('Description')).toHaveAttribute('rows', String(configuration.document.form_description_rows));
  });

  it('prevents submission outside configured name limits', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /create resource/i }));
    expect(await screen.findByText(/name must contain/i)).toBeInTheDocument();
    expect(api_managementService.createResource).not.toHaveBeenCalled();
  });

  it('submits typed configured defaults and an idempotency key', async () => {
    vi.mocked(api_managementService.createResource).mockResolvedValue(resource());
    renderPage();
    await userEvent.type(await screen.findByLabelText('Name'), 'New resource');
    await userEvent.click(screen.getByRole('button', { name: /create resource/i }));
    await waitFor(() => expect(api_managementService.createResource).toHaveBeenCalledOnce());
    const request = vi.mocked(api_managementService.createResource).mock.calls[0]?.[0];
    expect(request?.name).toBe('New resource');
    expect(request?.description).toBe(configuration.document.resource_description_default);
    expect(request?.config).toEqual(configuration.document.resource_config_default);
    expect(typeof request?.idempotency_key).toBe('string');
  });
});
