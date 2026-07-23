import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegionalDetailPage } from '../RegionalDetailPage';
import { regionalService } from '../../services/regional-service';
import { ROUTES } from '../../contracts';
import { configurationFixture, resourceFixture } from './regional-test-fixtures';

vi.mock('../../services/regional-service');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/regional/test-id']}>
        <Routes>
          <Route path={ROUTES.DETAIL_PATTERN} element={<RegionalDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RegionalDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(regionalService.getActiveConfiguration).mockResolvedValue(configurationFixture());
  });

  it('renders a complete typed resource', async () => {
    vi.mocked(regionalService.getResource).mockResolvedValue(
      resourceFixture({ id: 'test-id', name: 'Test resource' }),
    );
    renderPage();
    expect(await screen.findByText('Test resource')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('distinguishes a request failure and provides retry', async () => {
    vi.mocked(regionalService.getResource).mockRejectedValue(new Error('Service unavailable'));
    renderPage();
    expect(await screen.findByText('Unable to load resource')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument();
  });
});
