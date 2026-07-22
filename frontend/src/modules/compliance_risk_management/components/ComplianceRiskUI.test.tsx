import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ComplianceRiskApiError } from '../services/compliance-risk-service';
import { EmptyState, GovernedProblem, StatusBadge, Timeline } from './ComplianceRiskUI';

describe('compliance risk shared UX', () => {
  it('renders dedicated 403 and 404 states without leaking resource existence', () => {
    const { rerender } = render(<GovernedProblem error={new ComplianceRiskApiError('denied', 403, 'POLICY_DENIED', 'corr-403')}/>);
    expect(screen.getByRole('alert')).toHaveTextContent('Access denied');
    expect(screen.getByRole('alert')).toHaveTextContent('corr-403');
    rerender(<GovernedProblem error={new ComplianceRiskApiError('missing', 404, 'NOT_FOUND', 'corr-404')}/>);
    expect(screen.getByRole('alert')).toHaveTextContent('Record not found');
  });

  it('offers retry only for general governed failures', async () => {
    const retry = vi.fn(); render(<GovernedProblem error={new ComplianceRiskApiError('unavailable', 503, 'UNAVAILABLE', 'corr-503')} retry={retry}/>);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('supports permission-aware empty actions and non-color-only status', async () => {
    const action = vi.fn(); render(<><EmptyState title="No risks" message="Create one" action={{ label: 'Create risk', onClick: action }}/><StatusBadge value="critical"/></>);
    await userEvent.click(screen.getByRole('button', { name: 'Create risk' }));
    expect(action).toHaveBeenCalledOnce(); expect(screen.getByText('Critical')).toHaveTextContent('▲');
  });

  it('renders an accessible audit timeline with correlation evidence', () => {
    render(<Timeline items={[{ command: 'assess', from: 'identified', to: 'assessed', occurred_at: '2026-07-23T00:00:00Z', correlation_id: 'corr-a', rationale: 'Evidence reviewed' }]}/>);
    expect(screen.getByRole('list', { name: 'Audit timeline' })).toHaveTextContent('corr-a');
    expect(screen.getByText('Evidence reviewed')).toBeVisible();
  });
});
