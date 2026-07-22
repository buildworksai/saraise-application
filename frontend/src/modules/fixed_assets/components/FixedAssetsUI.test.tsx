import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/services/api-client';
import { CommandButton, EmptyPanel, formatDateOnly, formatMoney, ProblemState } from './FixedAssetsUI';

describe('fixed asset shared UX states', () => {
  it('renders a distinct forbidden state without implying existence', () => {
    render(<ProblemState error={new ApiError('Denied', 403, undefined, 'POLICY_DENIED', 'corr-denied')}/>);
    expect(screen.getByRole('alert')).toHaveTextContent('Access denied');
    expect(screen.getByRole('alert')).toHaveTextContent('No resource existence has been disclosed');
    expect(screen.getByRole('alert')).toHaveTextContent('corr-denied');
  });

  it('renders a distinct not-found state and a retryable general error', async () => {
    const retry = vi.fn(); const { rerender } = render(<ProblemState error={new ApiError('Missing', 404)}/>);
    expect(screen.getByRole('alert')).toHaveTextContent('Record not found');
    rerender(<ProblemState error={new ApiError('Unavailable', 503, undefined, 'CAPABILITY_UNAVAILABLE', 'corr-503')} onRetry={retry}/>);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce(); expect(screen.getByRole('alert')).toHaveTextContent('corr-503');
  });

  it('offers the permitted next action in empty states', async () => {
    const action = vi.fn(); render(<EmptyPanel title="No assets" description="Register one" action={{ label: 'Register asset', onClick: action }}/>);
    await userEvent.click(screen.getByRole('button', { name: 'Register asset' })); expect(action).toHaveBeenCalledOnce();
  });

  it('explains disabled server-authoritative commands accessibly', () => {
    render(<CommandButton affordance={{ command: 'dispose', allowed: false, denial_code: 'INVALID_STATE', explanation: 'Only active assets can be disposed.' }} onClick={vi.fn()}>Dispose</CommandButton>);
    expect(screen.getByRole('button', { name: 'Dispose' })).toBeDisabled();
    expect(screen.getByText('Only active assets can be disposed.')).toHaveClass('sr-only');
  });

  it('formats currency and date-only values without local timezone drift', () => {
    expect(formatMoney('1234.50', 'USD')).toContain('1,234.50');
    expect(formatDateOnly('2026-07-22')).not.toBe('2026-07-21');
  });
});
