import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DataMigrationDetailPage } from '../DataMigrationDetailPage';
import { dataMigrationService } from '../../services/data-migration-service';

vi.mock('../../services/data-migration-service', async (load) => {
  const actual = await load<typeof import('../../services/data-migration-service')>();
  return { ...actual, dataMigrationService: { ...actual.dataMigrationService, jobs: { ...actual.dataMigrationService.jobs, get: vi.fn() } } };
});

describe('DataMigrationDetailPage', () => {
  it('renders an accessible skeleton while durable detail is pending', () => {
    vi.mocked(dataMigrationService.jobs.get).mockImplementation(() => new Promise(() => undefined));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/data-migration/jobs/00000000-0000-4000-8000-000000000001']}><Routes><Route path="/data-migration/jobs/:id" element={<DataMigrationDetailPage />} /></Routes></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole('status', { name: 'Loading migration definition' })).toBeInTheDocument();
  });
});
