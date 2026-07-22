import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CreateAiProviderConfigurationResourcePage } from '../CreateAiProviderConfigurationResourcePage';
import { aiProviderConfigurationService } from '../../services/ai_provider_configuration-service';

const navigate = vi.fn();
vi.mock('../../services/ai_provider_configuration-service');
vi.mock('react-router-dom', async () => ({ ...await vi.importActual('react-router-dom'), useNavigate: () => navigate }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><CreateAiProviderConfigurationResourcePage /></MemoryRouter></QueryClientProvider>);
}

describe('CreateAiProviderConfigurationResourcePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.listProviders).mockResolvedValue([{ id: 'provider-1', name: 'Anthropic', provider_type: 'anthropic', base_url: '', is_active: true, models_count: 2, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]);
  });

  it('validates the provider before submitting secret material', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('option', { name: 'Anthropic' });
    await user.click(screen.getByRole('button', { name: /connect credential/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Select a provider');
    expect(aiProviderConfigurationService.createCredential).not.toHaveBeenCalled();
  });

  it('submits the exact credential contract and redirects after durable success', async () => {
    vi.mocked(aiProviderConfigurationService.createCredential).mockResolvedValue({
      id: 'credential-1', tenant_id: 'tenant-1', provider: 'provider-1', provider_name: 'Anthropic', provider_type: 'anthropic',
      label: 'Production', status: 'unverified', secret_hint: '1234', has_secret: true, last_verified_at: null,
      last_error_code: '', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    });
    const user = userEvent.setup();
    renderPage();
    await user.selectOptions(await screen.findByLabelText('Provider'), 'provider-1');
    await user.clear(screen.getByLabelText('Credential label'));
    await user.type(screen.getByLabelText('Credential label'), 'Production');
    await user.type(screen.getByLabelText('Provider API key'), 'secret-123456');
    await user.click(screen.getByRole('button', { name: /connect credential/i }));
    await waitFor(() => expect(aiProviderConfigurationService.createCredential).toHaveBeenCalledWith({ provider: 'provider-1', label: 'Production', api_key: 'secret-123456' }));
    expect(navigate).toHaveBeenCalledWith('/ai-provider-configuration');
  });
});
