/**
 * DataMigrationDetailPage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DataMigrationDetailPage } from './DataMigrationDetailPage';
import { data_migration_service } from '../services/data-migration-service';

// Mock dependencies
vi.mock('../services/data-migration-service');
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

describe('DataMigrationDetailPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    vi.mocked(data_migration_service.getResource).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/:id" element={<DataMigrationDetailPage />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should render resource details', async () => {
    const mockResource = {
      id: 'test-id',
      name: 'Test Resource',
      description: 'Test Description',
      is_active: true,
      config: { key: 'value' },
    };

    vi.mocked(data_migration_service.getResource).mockResolvedValue(mockResource as any);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/:id" element={<DataMigrationDetailPage />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Resource')).toBeInTheDocument();
      expect(screen.getByText('Test Description')).toBeInTheDocument();
    });
  });

  it('should render error state when resource not found', async () => {
    vi.mocked(data_migration_service.getResource).mockRejectedValue(new Error('Not found'));

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/:id" element={<DataMigrationDetailPage />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });
});
