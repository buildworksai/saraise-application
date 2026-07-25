/**
 * LocalizationListPage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocalizationListPage } from '../LocalizationListPage';
import { localizationService as localization_service } from '../../services/localization-service';
import type { Translation } from '../../contracts';

// Mock dependencies
vi.mock('../../services/localization-service');
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

describe('LocalizationListPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    vi.mocked(localization_service.listResources).mockImplementation(
      () => new Promise<Translation[]>(() => {
        // Intentionally unresolved to exercise the loading state.
      })
    );

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LocalizationListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('should render empty state when no resources', async () => {
    vi.mocked(localization_service.listResources).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LocalizationListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no resources yet/i)).toBeInTheDocument();
    });
  });

  it('should render resources list', async () => {
    const mockResources: Translation[] = [
      {
        id: '1',
        tenant_id: 'tenant-id',
        language: 'en',
        key: 'Resource 1',
        value: 'First resource',
        context: 'Description 1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: '2',
        tenant_id: 'tenant-id',
        language: 'en',
        key: 'Resource 2',
        value: 'Second resource',
        context: 'Description 2',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ];

    vi.mocked(localization_service.listResources).mockResolvedValue(mockResources);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LocalizationListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Resource 1')).toBeInTheDocument();
      expect(screen.getByText('Resource 2')).toBeInTheDocument();
    });
  });

  it('should filter resources by search term', async () => {
    const mockResources: Translation[] = [
      { id: '1', tenant_id: 'tenant-id', language: 'en', key: 'Apple', value: 'Apple', context: 'Fruit', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
      { id: '2', tenant_id: 'tenant-id', language: 'en', key: 'Banana', value: 'Banana', context: 'Fruit', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
    ];

    vi.mocked(localization_service.listResources).mockResolvedValue(mockResources);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LocalizationListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Apple' })).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search/i);
    await userEvent.type(searchInput, 'Banana');

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Apple' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Banana' })).toBeInTheDocument();
    });
  });
});
