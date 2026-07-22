import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SecretManagementPage } from '../SecretManagementPage';
import { aiProviderConfigurationService } from '../../services/ai_provider_configuration-service';
import { secretService } from '../../services/secret-service';

vi.mock('../../services/ai_provider_configuration-service');
vi.mock('../../services/secret-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><SecretManagementPage /></MemoryRouter></QueryClientProvider>);
}

describe('SecretManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([]);
  });

  it('does not claim rotation before the provider operation succeeds', async () => {
    vi.mocked(secretService.rotateKey).mockRejectedValue(new Error('unavailable'));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('No protected credentials');
    await user.click(screen.getByRole('button', { name: 'Generate new key' }));
    await user.click(await screen.findByRole('button', { name: 'Generate key' }));
    expect(secretService.rotateKey).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('new-encryption-key')).not.toBeInTheDocument();
  });

  it('submits both keys to the explicit re-encryption operation', async () => {
    vi.mocked(secretService.reEncrypt).mockResolvedValue({ success: true, re_encrypted_count: 2, message: 'done' });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('No protected credentials');
    await user.type(screen.getByLabelText('Current encryption key'), 'old-secret');
    await user.type(screen.getByLabelText('Replacement encryption key'), 'new-secret');
    await user.click(screen.getByRole('button', { name: 'Re-encrypt all credentials' }));
    expect(secretService.reEncrypt).toHaveBeenCalledWith({ old_key: 'old-secret', new_key: 'new-secret' });
  });
});
