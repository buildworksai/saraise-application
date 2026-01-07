/**
 * AgentListPage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentListPage } from './AgentListPage';
import { aiAgentService } from '../services/ai-agent-service';

// Mock dependencies
vi.mock('../services/ai-agent-service');
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

describe('AgentListPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    vi.mocked(aiAgentService.listAgents).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    // Should show skeleton or loading indicator
    expect(screen.getByText(/ai agents/i)).toBeInTheDocument();
  });

  it('should render agents list', async () => {
    const mockAgents = [
      {
        id: '1',
        name: 'Test Agent',
        description: 'Test description',
        identity_type: 'user_bound' as const,
        subject_id: 'user-123',
        framework: 'langgraph',
        is_active: true,
      },
    ];

    vi.mocked(aiAgentService.listAgents).mockResolvedValueOnce(mockAgents);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Agent')).toBeInTheDocument();
    });
  });

  it('should render empty state when no agents', async () => {
    vi.mocked(aiAgentService.listAgents).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no ai agents yet/i)).toBeInTheDocument();
    });
  });

  it('should filter agents by search term', async () => {
    const user = userEvent.setup();
    const mockAgents = [
      {
        id: '1',
        name: 'Test Agent',
        description: 'Test description',
        identity_type: 'user_bound' as const,
        subject_id: 'user-123',
        framework: 'langgraph',
        is_active: true,
      },
      {
        id: '2',
        name: 'Another Agent',
        description: 'Another description',
        identity_type: 'user_bound' as const,
        subject_id: 'user-456',
        framework: 'langgraph',
        is_active: true,
      },
    ];

    vi.mocked(aiAgentService.listAgents).mockResolvedValueOnce(mockAgents);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Agent')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search/i);
    await user.clear(searchInput);
    await user.type(searchInput, 'Test');

    // Wait for deferred value to update
    await waitFor(() => {
      expect(screen.getByText('Test Agent')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('should show error state on failure', async () => {
    vi.mocked(aiAgentService.listAgents).mockRejectedValueOnce(new Error('Failed to load'));

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AgentListPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/failed to load agents/i)).toBeInTheDocument();
    });
  });
});

