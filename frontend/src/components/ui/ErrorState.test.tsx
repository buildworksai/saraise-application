/**
 * ErrorState Component Tests
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorState } from './ErrorState';

describe('ErrorState', () => {
  it('should render default title and message', () => {
    render(<ErrorState message="Something went wrong" />);
    
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('should render custom title', () => {
    render(
      <ErrorState
        title="Custom Error"
        message="Error message"
      />
    );
    
    expect(screen.getByText('Custom Error')).toBeInTheDocument();
    expect(screen.getByText('Error message')).toBeInTheDocument();
  });

  it('should render retry button when onRetry is provided', async () => {
    const user = userEvent.setup();
    const handleRetry = vi.fn();
    
    render(
      <ErrorState
        message="Error occurred"
        onRetry={handleRetry}
      />
    );
    
    const retryButton = screen.getByRole('button', { name: /try again/i });
    expect(retryButton).toBeInTheDocument();
    
    await user.click(retryButton);
    expect(handleRetry).toHaveBeenCalled();
  });

  it('should not render retry button when onRetry is not provided', () => {
    render(<ErrorState message="Error occurred" />);
    
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });
});

