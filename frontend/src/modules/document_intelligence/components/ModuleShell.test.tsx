import { fireEvent, render, screen } from '@testing-library/react';
import { ApiProblem, EmptyPanel, PageSkeleton } from './ModuleShell';
import { DocumentIntelligenceApiError } from '../services/document-intelligence-service';

describe('document intelligence shared states', () => {
  it('renders a layout-matched accessible skeleton', () => {
    render(<PageSkeleton />);
    expect(screen.getByLabelText('Loading document intelligence')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders a permission-aware empty action when supplied', () => {
    render(<EmptyPanel title="No evidence" description="Nothing processed." action={<button>Process document</button>} />);
    expect(screen.getByRole('button', { name: 'Process document' })).toBeInTheDocument();
  });

  it('does not leak object existence for access errors and preserves correlation', () => {
    const retry = vi.fn();
    render(<ApiProblem error={new DocumentIntelligenceApiError('Hidden server detail', 404, 'not_found', 'corr-404', {})} onRetry={retry} />);
    expect(screen.getByText('Access unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Hidden server detail')).not.toBeInTheDocument();
    expect(screen.getByText(/corr-404/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('shows quota remaining and reset evidence', () => {
    render(<ApiProblem error={new DocumentIntelligenceApiError('Quota', 429, 'quota_exhausted', 'corr-429', { quota: { resource: 'pages', remaining: 0, reset_at: '2026-07-22T00:00:00Z' } })} onRetry={() => undefined} />);
    expect(screen.getByText('Processing quota reached')).toBeInTheDocument();
    expect(screen.getByText(/0 units remain/u)).toBeInTheDocument();
  });
});
