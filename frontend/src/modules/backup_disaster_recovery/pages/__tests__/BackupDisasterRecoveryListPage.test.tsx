/**
 * BackupDisasterRecoveryListPage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BackupDisasterRecoveryListPage } from './BackupDisasterRecoveryListPage';
import { backup_disaster_recovery_service } from '../services/backup-disaster-recovery-service';

// Mock dependencies
vi.mock('../services/backup-disaster-recovery-service');
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

describe('BackupDisasterRecoveryListPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    vi.mocked(backup_disaster_recovery_service.listResources).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <BackupDisasterRecoveryListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should render empty state when no resources', async () => {
    vi.mocked(backup_disaster_recovery_service.listResources).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <BackupDisasterRecoveryListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no resources yet/i)).toBeInTheDocument();
    });
  });

  it('should render resources list', async () => {
    const mockResources = [
      {
        id: '1',
        name: 'Resource 1',
        description: 'Description 1',
        is_active: true,
      },
      {
        id: '2',
        name: 'Resource 2',
        description: 'Description 2',
        is_active: false,
      },
    ];

    vi.mocked(backup_disaster_recovery_service.listResources).mockResolvedValue(mockResources as any);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <BackupDisasterRecoveryListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Resource 1')).toBeInTheDocument();
      expect(screen.getByText('Resource 2')).toBeInTheDocument();
    });
  });

  it('should filter resources by search term', async () => {
    const mockResources = [
      { id: '1', name: 'Apple', description: 'Fruit' },
      { id: '2', name: 'Banana', description: 'Fruit' },
    ];

    vi.mocked(backup_disaster_recovery_service.listResources).mockResolvedValue(mockResources as any);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <BackupDisasterRecoveryListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Apple')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search/i);
    await userEvent.type(searchInput, 'Banana');

    await waitFor(() => {
      expect(screen.queryByText('Apple')).not.toBeInTheDocument();
      expect(screen.getByText('Banana')).toBeInTheDocument();
    });
  });
});
