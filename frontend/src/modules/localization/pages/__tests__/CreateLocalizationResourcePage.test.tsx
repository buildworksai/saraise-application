/**
 * CreateLocalizationResourcePage Component Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateLocalizationResourcePage } from '../CreateLocalizationResourcePage';
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

describe('CreateLocalizationResourcePage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it('should render form', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateLocalizationResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByLabelText(/language id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/translation key/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/translation value/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/context/i)).toBeInTheDocument();
  });

  it('should validate required fields', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateLocalizationResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    const submitButton = screen.getByRole('button', { name: /create/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/language is required/i)).toBeInTheDocument();
    });
  });

  it('should submit form with valid data', async () => {
    const createdTranslation: Translation = {
      id: 'new-id',
      tenant_id: 'tenant-id',
      language: 'en',
      key: 'common.save',
      value: 'Save',
      context: 'button',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const mockCreate = vi.mocked(localization_service.createTranslation).mockResolvedValue(createdTranslation);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CreateLocalizationResourcePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    const languageInput = screen.getByLabelText(/language id/i);
    const keyInput = screen.getByLabelText(/translation key/i);
    const valueInput = screen.getByLabelText(/translation value/i);
    const contextInput = screen.getByLabelText(/context/i);
    const submitButton = screen.getByRole('button', { name: /create/i });

    await userEvent.type(languageInput, 'en');
    await userEvent.type(keyInput, 'common.save');
    await userEvent.type(valueInput, 'Save');
    await userEvent.type(contextInput, 'button');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        language: 'en',
        key: 'common.save',
        value: 'Save',
        context: 'button',
      });
    });
  });
});
