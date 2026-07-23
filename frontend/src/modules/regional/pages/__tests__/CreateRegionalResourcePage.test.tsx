import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateRegionalResourcePage } from '../CreateRegionalResourcePage';
import { regionalService } from '../../services/regional-service';
import { configurationFixture, resourceFixture } from './regional-test-fixtures';

vi.mock('../../services/regional-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const createTestQueryClient = () => new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});

function renderPage(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><CreateRegionalResourcePage /></BrowserRouter>
    </QueryClientProvider>,
  );
}

describe('CreateRegionalResourcePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(regionalService.getActiveConfiguration).mockResolvedValue(configurationFixture());
  });

  it('loads the governed form and validates required fields', async () => {
    renderPage(createTestQueryClient());
    const name = await screen.findByLabelText('Name');
    expect(name).toHaveValue('Regional resource');
    await userEvent.clear(name);
    await userEvent.type(name, ' ');
    await userEvent.click(screen.getByRole('button', { name: 'Create resource' }));
    expect(
      await screen.findByText('Name must contain at least 1 non-whitespace characters'),
    ).toBeInTheDocument();
  });

  it('submits a typed request using the runtime description default', async () => {
    const created = resourceFixture({ id: 'new-id', name: 'New resource' });
    const create = vi.mocked(regionalService.createResource).mockResolvedValue(created);
    renderPage(createTestQueryClient());
    const name = await screen.findByLabelText('Name');
    await userEvent.clear(name);
    await userEvent.type(name, 'New resource');
    await userEvent.click(screen.getByRole('button', { name: 'Create resource' }));
    await waitFor(() => {
      expect(create).toHaveBeenCalledOnce();
    });
    const firstCall = create.mock.calls[0];
    if (!firstCall) throw new Error('Expected a createResource invocation.');
    const [payload, key] = firstCall;
    expect(payload).toEqual({ name: 'New resource', description: '' });
    expect(typeof key).toBe('string');
  });
});
