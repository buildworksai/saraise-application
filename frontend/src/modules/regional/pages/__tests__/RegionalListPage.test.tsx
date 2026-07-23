import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegionalListPage } from '../RegionalListPage';
import { regionalService } from '../../services/regional-service';
import {
  configurationFixture,
  resourceFixture,
  resourcePageFixture,
} from './regional-test-fixtures';

vi.mock('../../services/regional-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const createTestQueryClient = () => new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});

function renderPage() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <BrowserRouter><RegionalListPage /></BrowserRouter>
    </QueryClientProvider>,
  );
}

describe('RegionalListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(regionalService.getActiveConfiguration).mockResolvedValue(configurationFixture());
  });

  it('renders the empty state from a typed page response', async () => {
    vi.mocked(regionalService.listResources).mockResolvedValue(resourcePageFixture([]));
    renderPage();
    expect(await screen.findByText('No resources found')).toBeInTheDocument();
  });

  it('renders resources and sends server-side governed search', async () => {
    const resources = [
      resourceFixture({ id: 'one', name: 'Apple' }),
      resourceFixture({ id: 'two', name: 'Banana', is_active: false }),
    ];
    const list = vi.mocked(regionalService.listResources)
      .mockResolvedValue(resourcePageFixture(resources));
    renderPage();
    expect(await screen.findByText('Apple')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Search resources'), 'Banana');
    expect(await screen.findByText('Banana')).toBeInTheDocument();
    expect(list).toHaveBeenCalled();
  });
});
