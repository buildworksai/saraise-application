import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AiProviderConfigurationDetailPage } from '../AiProviderConfigurationDetailPage';
import { aiProviderConfigurationService } from '../../services/ai_provider_configuration-service';

vi.mock('../../services/ai_provider_configuration-service');
vi.mock('react-router-dom', async () => ({ ...await vi.importActual('react-router-dom'), useParams: () => ({ id: 'provider-1' }), useNavigate: () => vi.fn() }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><AiProviderConfigurationDetailPage /></MemoryRouter></QueryClientProvider>);
}

describe('AiProviderConfigurationDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.getProvider).mockResolvedValue({ id: 'provider-1', name: 'Mistral', provider_type: 'mistral', base_url: '', is_active: true, models_count: 1, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' });
    vi.mocked(aiProviderConfigurationService.listModels).mockResolvedValue([{ id: 'model-1', provider: 'provider-1', provider_name: 'Mistral', provider_type: 'mistral', model_id: 'large', display_name: 'Mistral Large', capabilities: ['text'], pricing: {}, max_tokens: 32000, is_active: true, deployments_count: 0, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]);
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.listDeployments).mockResolvedValue([]);
  });

  it('renders provider models and tenant-scoped empty states', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Mistral' })).toBeInTheDocument();
    expect(screen.getByText('Mistral Large')).toBeInTheDocument();
    expect(screen.getByText('No credential')).toBeInTheDocument();
    expect(screen.getByText('No deployments')).toBeInTheDocument();
  });

  it('renders a retryable failure for an unavailable provider', async () => {
    vi.mocked(aiProviderConfigurationService.getProvider).mockRejectedValue(new Error('not found'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider configuration unavailable');
  });
});
