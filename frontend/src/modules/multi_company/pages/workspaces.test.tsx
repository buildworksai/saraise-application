import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { multiCompanyService } from '../services/multi-company-service';
import { CompanyListPage } from './workspaces';

vi.mock('../services/multi-company-service', () => ({
  multiCompanyService: { listCompanies: vi.fn() },
}));

describe('CompanyListPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('teaches a new tenant how to begin when the governed result is empty', async () => {
    vi.mocked(multiCompanyService.listCompanies).mockResolvedValue({
      data: [],
      meta: { correlation_id: 'corr-empty', timestamp: '2026-07-23T00:00:00Z' },
      pagination: { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/multi-company/companies']}><CompanyListPage /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Build your company structure' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Create company' })).toHaveLength(2);
  });
});
