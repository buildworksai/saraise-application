import { render, screen } from '@testing-library/react';
import { ApiProblem, EmptyPanel, can } from './DmsUI';
import { DmsApiError } from '../services/dms-service';

describe('DMS governed UI states', () => {
  it.each([
    [{ kind: 'denied', status: 403, message: 'hidden', correlation_id: 'corr-denied' } as const, 'Access denied'],
    [{ kind: 'not_found', status: 404, message: 'hidden', correlation_id: 'corr-not-found' } as const, 'Document unavailable'],
    [{ kind: 'unavailable', status: 503, message: 'offline', correlation_id: 'corr-storage' } as const, 'Document storage unavailable'],
    [{ kind: 'conflict', status: 409, message: 'stale', correlation_id: 'corr-conflict' } as const, 'A newer revision exists'],
  ])('renders a safe recovery state for %s', (problem, title) => {
    render(<ApiProblem error={new DmsApiError(problem)}/>);
    expect(screen.getByRole('alert')).toHaveTextContent(title);
    expect(screen.getByText(new RegExp(problem.correlation_id, 'u'))).toBeInTheDocument();
    expect(screen.queryByText(problem.message)).not.toBeInTheDocument();
  });

  it('distinguishes empty folders from filtered-empty results', () => {
    const { rerender } = render(<EmptyPanel filtered={false} folder/>);
    expect(screen.getByText('This folder is empty')).toBeInTheDocument();
    rerender(<EmptyPanel filtered folder={false} onReset={() => undefined}/>);
    expect(screen.getByText('No documents match these filters')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeEnabled();
  });

  it('maps backend ACL capabilities to precise UI actions', () => {
    expect(can(['write'], 'update')).toBe(true);
    expect(can(['write'], 'create_version')).toBe(true);
    expect(can(['manage'], 'manage_permissions')).toBe(true);
    expect(can(['read'], 'delete')).toBe(false);
  });
});
