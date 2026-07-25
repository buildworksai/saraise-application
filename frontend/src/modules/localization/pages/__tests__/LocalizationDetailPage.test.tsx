/**
 * LocalizationDetailPage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocalizationDetailPage } from '../LocalizationDetailPage';
import { localizationService as localization_service } from '../../services/localization-service';
import type { Translation } from '../../contracts';

// Mock dependencies
vi.mock('../../services/localization-service');
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'test-id' }),
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

describe('LocalizationDetailPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    vi.mocked(localization_service.getResource).mockImplementation(
      () => new Promise<Translation>(() => {
        // Intentionally unresolved to exercise the loading state.
      })
    );

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/test-id']}>
          <Routes>
            <Route path="/:id" element={<LocalizationDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should render resource details', async () => {
    const mockResource: Translation = {
      id: 'test-id',
      tenant_id: 'tenant-id',
      language: 'en',
      key: 'test.resource',
      value: 'Test Resource',
      context: 'Test Description',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    vi.mocked(localization_service.getResource).mockResolvedValue(mockResource);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/test-id']}>
          <Routes>
            <Route path="/:id" element={<LocalizationDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Resource')).toBeInTheDocument();
      expect(screen.getByText('Test Description')).toBeInTheDocument();
    });
  });

  it('should render error state when resource not found', async () => {
    vi.mocked(localization_service.getResource).mockRejectedValue(new Error('Not found'));

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/test-id']}>
          <Routes>
            <Route path="/:id" element={<LocalizationDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });
});
