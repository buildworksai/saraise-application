import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ExtractionDashboardPage } from './ExtractionDashboardPage';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import type { DocumentExtractionListItem, PaginatedResult } from '../contracts';

const extraction: DocumentExtractionListItem = { id: 'e1', tenant_id: 't1', created_by: 'u1', document_id: 'd1', document_version_id: 'v1', engine: 'tesseract', extraction_type: 'text', template: null, status: 'queued', confidence: null, page_count: null, processing_time_ms: null, completed_at: null, is_deleted: false, deleted_at: null, created_at: '2026-07-21T10:00:00Z', updated_at: '2026-07-21T10:00:00Z' };
const result: PaginatedResult<DocumentExtractionListItem> = { items: [extraction], pagination: { count: 1, page: 1, page_size: 25, total_pages: 1, has_next: false, has_previous: false }, correlationId: 'corr-dashboard' };

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/document-intelligence/extractions?status=queued']}><ExtractionDashboardPage /></MemoryRouter></QueryClientProvider>);
}

describe('ExtractionDashboardPage polling', () => {
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('polls controlled active jobs and preserves URL server filters', async () => {
    vi.useFakeTimers();
    const list = vi.spyOn(documentIntelligenceService, 'listExtractions').mockResolvedValue(result);
    renderDashboard();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ status: 'queued' }));
    expect(screen.getByText('Auto-refreshing active work', { exact: false })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(list.mock.calls.length).toBeGreaterThan(1);
  });
});
