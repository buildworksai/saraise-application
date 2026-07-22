import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DataMigrationListPage } from '../DataMigrationListPage';
import { dataMigrationService } from '../../services/data-migration-service';

vi.mock('../../services/data-migration-service', async (load) => {
  const actual = await load<typeof import('../../services/data-migration-service')>();
  return { ...actual, dataMigrationService: { ...actual.dataMigrationService, jobs: { ...actual.dataMigrationService.jobs, list: vi.fn() } } };
});

describe('DataMigrationListPage', () => {
  it('renders an accessible skeleton while the governed page is pending', () => {
    vi.mocked(dataMigrationService.jobs.list).mockImplementation(() => new Promise(() => undefined));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><DataMigrationListPage /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole('status', { name: 'Loading migration definitions' })).toBeInTheDocument();
  });
});
