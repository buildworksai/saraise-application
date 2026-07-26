/**
 * BillingSubscriptionsListPage Component Tests
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { Subscription } from '../../contracts';
import { billing_subscriptionsService } from '../../services/billing_subscriptions-service';
import { BillingSubscriptionsListPage } from '../BillingSubscriptionsListPage';

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock('../../services/billing_subscriptions-service');
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const subscriptions: Subscription[] = [
  {
    id: 'subscription-1',
    tenant_id: 'tenant-1',
    plan: 'starter-plan',
    plan_id: 'plan-1',
    status: 'active',
    current_period_start: '2026-07-01T00:00:00Z',
    current_period_end: '2026-08-01T00:00:00Z',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'subscription-2',
    tenant_id: 'tenant-1',
    plan: 'enterprise-plan',
    plan_id: 'plan-2',
    status: 'cancelled',
    current_period_start: '2026-06-01T00:00:00Z',
    current_period_end: '2026-07-01T00:00:00Z',
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-07-02T00:00:00Z',
  },
];

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const renderPage = (queryClient: QueryClient) =>
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <BillingSubscriptionsListPage />
      </BrowserRouter>
    </QueryClientProvider>,
  );

describe('BillingSubscriptionsListPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('renders the table loading skeleton while subscriptions are pending', () => {
    vi.mocked(billing_subscriptionsService.listSubscriptions).mockImplementation(
      () => new Promise<Subscription[]>(() => {}),
    );

    const { container } = renderPage(queryClient);

    expect(billing_subscriptionsService.listSubscriptions).toHaveBeenCalledOnce();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(27);
  });

  it('renders the empty state when there are no subscriptions', async () => {
    vi.mocked(billing_subscriptionsService.listSubscriptions).mockResolvedValue([]);

    renderPage(queryClient);

    expect(await screen.findByRole('heading', { name: 'No resources yet' })).toBeInTheDocument();
    expect(screen.getByText('Get started by creating your first resource.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Create Resource' })).toHaveLength(2);
  });

  it('renders one actionable table row for each subscription returned by the service', async () => {
    vi.mocked(billing_subscriptionsService.listSubscriptions).mockResolvedValue(subscriptions);

    renderPage(queryClient);

    const table = await screen.findByRole('table');
    const bodyRows = within(table).getAllByRole('row').slice(1);

    expect(bodyRows).toHaveLength(subscriptions.length);
    expect(within(table).getAllByRole('button', { name: 'View' })).toHaveLength(2);
    expect(within(table).getAllByRole('button', { name: 'Delete' })).toHaveLength(2);
    expect(within(table).getAllByText('Inactive')).toHaveLength(2);
    expect(billing_subscriptionsService.listSubscriptions).toHaveBeenCalledOnce();
  });

  it('renders an error state and retries the subscription request', async () => {
    vi.mocked(billing_subscriptionsService.listSubscriptions)
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce([]);
    const user = userEvent.setup();

    renderPage(queryClient);

    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
    expect(
      screen.getByText('Failed to load resources. Please check your connection and try again.'),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try Again' }));

    expect(await screen.findByRole('heading', { name: 'No resources yet' })).toBeInTheDocument();
    expect(billing_subscriptionsService.listSubscriptions).toHaveBeenCalledTimes(2);
  });

  it('deletes the selected subscription after confirmation', async () => {
    vi.mocked(billing_subscriptionsService.listSubscriptions).mockResolvedValue(subscriptions);
    vi.mocked(billing_subscriptionsService.deleteSubscription).mockResolvedValue();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();

    renderPage(queryClient);
    await user.click((await screen.findAllByRole('button', { name: 'Delete' }))[0]!);

    await waitFor(() => {
      expect(billing_subscriptionsService.deleteSubscription).toHaveBeenCalledWith('subscription-1');
    });
    expect(confirmSpy).toHaveBeenCalledWith('Are you sure you want to delete this resource?');
    expect(toast.success).toHaveBeenCalledWith('Resource deleted successfully');

    confirmSpy.mockRestore();
  });
});
