import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegionalConfigurationPage } from '../RegionalConfigurationPage';
import { regionalService } from '../../services/regional-service';
import { configurationFixture } from './regional-test-fixtures';

const auth = vi.hoisted(() => ({ tenantRole: 'tenant_admin' as string | null }));

vi.mock('../../services/regional-service');
vi.mock('@/stores/auth-store', () => ({
  useAuthStore: (
    selector: (state: { user: { tenant_role: string | null } }) => unknown,
  ) => selector({ user: { tenant_role: auth.tenantRole } }),
}));

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })}>
      <RegionalConfigurationPage />
    </QueryClientProvider>,
  );
}

describe('RegionalConfigurationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.tenantRole = 'tenant_admin';
    vi.mocked(regionalService.getConfiguration).mockResolvedValue(configurationFixture());
    vi.mocked(regionalService.listConfigurationHistory).mockResolvedValue([]);
  });

  it('loads every configuration section from the RBAC-gated API', async () => {
    renderPage();
    expect(await screen.findByText('Resource defaults and safe limits')).toBeInTheDocument();
    expect(screen.getByText('Workflow and API policy')).toBeInTheDocument();
    expect(screen.getByText('Version history and immutable audit')).toBeInTheDocument();
    expect(regionalService.getConfiguration).toHaveBeenCalledWith('development');
  });

  it('fails closed for a non-administrator without requesting tenant configuration', () => {
    auth.tenantRole = 'tenant_user';
    renderPage();
    expect(screen.getByText('Access denied')).toBeInTheDocument();
    expect(regionalService.getConfiguration).not.toHaveBeenCalled();
  });
});
