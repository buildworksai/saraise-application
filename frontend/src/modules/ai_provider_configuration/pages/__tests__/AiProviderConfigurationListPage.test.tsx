import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AiProviderConfigurationListPage } from '../AiProviderConfigurationListPage';
import { aiProviderConfigurationService } from '../../services/ai_provider_configuration-service';
import type { AIModel, AIProvider } from '../../contracts';

vi.mock('../../services/ai_provider_configuration-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const provider: AIProvider = {
  id: 'provider-1', name: 'OpenAI', provider_type: 'openai', base_url: 'https://example.invalid',
  is_active: true, models_count: 1, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
};
const model: AIModel = {
  id: 'model-1', provider: provider.id, provider_name: provider.name, provider_type: 'openai',
  model_id: 'gpt-enterprise', display_name: 'GPT Enterprise', capabilities: ['text', 'function_calling'],
  pricing: {}, max_tokens: 128000, is_active: true, deployments_count: 0,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><AiProviderConfigurationListPage /></MemoryRouter></QueryClientProvider>);
}

describe('AiProviderConfigurationListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.listProviders).mockResolvedValue([provider]);
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.listModels).mockResolvedValue([model]);
    vi.mocked(aiProviderConfigurationService.listDeployments).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.listUsageLogs).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.getHealth).mockResolvedValue({ status: 'healthy' });
  });

  it('renders the provider catalog and tenant metrics', async () => {
    renderPage();
    expect(screen.getByRole('status', { name: /loading ai provider configuration/i })).toBeInTheDocument();
    expect(await screen.findByText('OpenAI')).toBeInTheDocument();
    expect(screen.getByText('Connected credentials')).toBeInTheDocument();
    expect(screen.getByText('Service healthy')).toBeInTheDocument();
  });

  it('supports resource tabs, empty states, and catalog search', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('OpenAI');
    await user.type(screen.getByRole('textbox', { name: /search providers/i }), 'missing');
    expect(screen.getByText('No matching providers')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Credentials' }));
    expect(screen.getByText('No credentials connected')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Usage' }));
    expect(screen.getByText('No usage recorded')).toBeInTheDocument();
  });

  it('shows a retryable error without fabricating empty data', async () => {
    vi.mocked(aiProviderConfigurationService.listProviders).mockRejectedValue(new Error('offline'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider configuration unavailable');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    await waitFor(() => expect(aiProviderConfigurationService.listProviders).toHaveBeenCalledTimes(1));
  });
});
