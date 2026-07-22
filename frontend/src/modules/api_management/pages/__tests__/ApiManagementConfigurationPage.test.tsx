import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ConfigurationPreview, ConfigurationVersion, PortableApiManagementConfiguration } from '../../contracts';
import { ApiManagementConfigurationPage } from '../ApiManagementConfigurationPage';
import { api_managementService } from '../../services/api_management-service';
import { configuration } from './test-fixtures';

vi.mock('../../services/api_management-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const current = { ...configuration, version: 2 };
const version = {
  version: 1,
  document: configuration.document,
  actor_id: 'operator-1',
  correlation_id: 'req_configuration_1',
  created_at: '2026-07-23T09:00:00Z',
} satisfies ConfigurationVersion;
const preview = {
  valid: true,
  normalized_document: configuration.document,
  changes: [{ field: 'page_size', before: 20, after: 25 }],
} satisfies ConfigurationPreview;
const portable = {
  module: 'api_management',
  schema_version: 1,
  version: 2,
  document: configuration.document,
} satisfies PortableApiManagementConfiguration;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BrowserRouter><ApiManagementConfigurationPage /></BrowserRouter></QueryClientProvider>);
}

describe('ApiManagementConfigurationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api_managementService.getConfiguration).mockResolvedValue(current);
    vi.mocked(api_managementService.listConfigurationHistory).mockResolvedValue([version]);
    vi.mocked(api_managementService.previewConfiguration).mockResolvedValue(preview);
    vi.mocked(api_managementService.updateConfiguration).mockResolvedValue(current);
    vi.mocked(api_managementService.importConfiguration).mockResolvedValue(current);
    vi.mocked(api_managementService.rollbackConfiguration).mockResolvedValue(current);
    vi.mocked(api_managementService.exportConfiguration).mockResolvedValue(portable);
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:configuration') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  it('renders every governed configuration section and immutable evidence', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'API Management configuration' })).toBeInTheDocument();
    expect(screen.getByText('Environment and rollout')).toBeInTheDocument();
    expect(screen.getByText('Resource defaults and safe limits')).toBeInTheDocument();
    expect(screen.getByText('Allow-listed operations')).toBeInTheDocument();
    expect(await screen.findByText('req_configuration_1')).toBeInTheDocument();
  });

  it('cannot save until the exact draft passes server preview', async () => {
    renderPage();
    const apply = await screen.findByRole('button', { name: 'Apply new version' });
    expect(apply).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Preview changes' }));
    await waitFor(() => expect(apply).toBeEnabled());
    await userEvent.click(apply);
    await waitFor(() => expect(api_managementService.updateConfiguration).toHaveBeenCalledOnce());
    const request = vi.mocked(api_managementService.updateConfiguration).mock.calls[0]?.[0];
    expect(request?.document).toEqual(configuration.document);
    expect(typeof request?.idempotency_key).toBe('string');
  });

  it('fails closed when tenant configuration cannot be loaded', async () => {
    vi.mocked(api_managementService.getConfiguration).mockRejectedValue(new Error('Policy unavailable'));
    renderPage();
    expect(await screen.findByText('Configuration unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument();
  });

  it('uses governed rollback and export endpoints', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Export' }));
    await waitFor(() => expect(api_managementService.exportConfiguration).toHaveBeenCalledOnce());
    await userEvent.click(await screen.findByRole('button', { name: 'Rollback' }));
    await userEvent.click(screen.getByRole('button', { name: 'Create rollback version' }));
    await waitFor(() => expect(api_managementService.rollbackConfiguration).toHaveBeenCalledOnce());
    const request = vi.mocked(api_managementService.rollbackConfiguration).mock.calls[0]?.[0];
    expect(request?.version).toBe(1);
    expect(typeof request?.idempotency_key).toBe('string');
  });

  it('server-previews an import before applying it', async () => {
    renderPage();
    const file = new File([JSON.stringify(portable)], 'configuration.json', { type: 'application/json' });
    Object.defineProperty(file, 'text', { value: () => Promise.resolve(JSON.stringify(portable)) });
    await userEvent.upload(await screen.findByLabelText('Import preview'), file);
    const apply = await screen.findByRole('button', { name: 'Apply imported configuration' });
    await userEvent.click(apply);
    await waitFor(() => expect(api_managementService.importConfiguration).toHaveBeenCalledOnce());
    const request = vi.mocked(api_managementService.importConfiguration).mock.calls[0]?.[0];
    expect(request?.document).toEqual(configuration.document);
    expect(typeof request?.idempotency_key).toBe('string');
  });
});
