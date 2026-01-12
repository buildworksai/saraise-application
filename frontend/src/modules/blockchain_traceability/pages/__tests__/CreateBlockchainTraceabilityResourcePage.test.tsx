/**
 * CreateBlockchainTraceabilityResourcePage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateBlockchainTraceabilityResourcePage } from './CreateBlockchainTraceabilityResourcePage';
import { blockchain_traceability_service } from '../services/blockchain-traceability-service';

// Mock dependencies
vi.mock('../services/blockchain-traceability-service');
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

describe('CreateBlockchainTraceabilityResourcePage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render form', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateBlockchainTraceabilityResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it('should validate required fields', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateBlockchainTraceabilityResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    const submitButton = screen.getByRole('button', { name: /create/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/name is required/i)).toBeInTheDocument();
    });
  });

  it('should submit form with valid data', async () => {
    const mockCreate = vi.mocked(blockchain_traceability_service.createResource).mockResolvedValue({ id: 'new-id' } as any);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateBlockchainTraceabilityResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    const nameInput = screen.getByLabelText(/name/i);
    const descriptionInput = screen.getByLabelText(/description/i);
    const submitButton = screen.getByRole('button', { name: /create/i });

    await userEvent.type(nameInput, 'New Resource');
    await userEvent.type(descriptionInput, 'New Description');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        name: 'New Resource',
        description: 'New Description',
        config: {},
      });
    });
  });
});
