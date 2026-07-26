/**
 * BillingSubscriptionsDetailPage Component Tests
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { Subscription } from '../../contracts';
import { billing_subscriptionsService } from '../../services/billing_subscriptions-service';
import { BillingSubscriptionsDetailPage } from '../BillingSubscriptionsDetailPage';

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock('../../services/billing_subscriptions-service');
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'subscription-1' }),
    useNavigate: () => navigateMock,
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const subscription: Subscription = {
  id: 'subscription-1',
  tenant_id: 'tenant-1',
  plan: 'enterprise-plan',
  plan_id: 'plan-1',
  status: 'active',
  current_period_start: '2026-07-01T00:00:00Z',
  current_period_end: '2026-08-01T00:00:00Z',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

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
        <BillingSubscriptionsDetailPage />
      </BrowserRouter>
    </QueryClientProvider>,
  );

describe('BillingSubscriptionsDetailPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('renders the loading state while the subscription request is pending', () => {
    vi.mocked(billing_subscriptionsService.getSubscription).mockImplementation(
      () => new Promise<Subscription>(() => {}),
    );

    renderPage(queryClient);

    expect(screen.getByText('Loading resource...')).toBeInTheDocument();
    expect(billing_subscriptionsService.getSubscription).toHaveBeenCalledWith('subscription-1');
  });

  it('renders the subscription details returned by the service', async () => {
    vi.mocked(billing_subscriptionsService.getSubscription).mockResolvedValue(subscription);

    renderPage(queryClient);

    expect(
      await screen.findByRole('heading', { name: 'Subscription subscription-1' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Plan: enterprise-plan')).toBeInTheDocument();
    expect(screen.getByText('enterprise-plan')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(
      screen.getByText(new Date(subscription.current_period_start).toLocaleDateString()),
    ).toBeInTheDocument();
    expect(
      screen.getByText(new Date(subscription.current_period_end).toLocaleDateString()),
    ).toBeInTheDocument();
    expect(billing_subscriptionsService.getSubscription).toHaveBeenCalledWith('subscription-1');
  });

  it('renders the not-found state when the subscription request fails', async () => {
    vi.mocked(billing_subscriptionsService.getSubscription).mockRejectedValue(
      new Error('Subscription not found'),
    );

    renderPage(queryClient);

    expect(await screen.findByText('Resource not found')).toBeInTheDocument();
    expect(billing_subscriptionsService.getSubscription).toHaveBeenCalledWith('subscription-1');
  });

  it('deletes the subscription and returns to the list after confirmation', async () => {
    vi.mocked(billing_subscriptionsService.getSubscription).mockResolvedValue(subscription);
    vi.mocked(billing_subscriptionsService.deleteSubscription).mockResolvedValue();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();

    renderPage(queryClient);
    await user.click(await screen.findByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(billing_subscriptionsService.deleteSubscription).toHaveBeenCalledWith('subscription-1');
    });
    expect(toast.success).toHaveBeenCalledWith('Resource deleted successfully');
    expect(navigateMock).toHaveBeenCalledWith('/billing-subscriptions');

    confirmSpy.mockRestore();
  });
});
