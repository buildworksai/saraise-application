/**
 * EmptyState Component Tests
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Bot } from 'lucide-react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('should render title and description', () => {
    render(
      <EmptyState
        icon={Bot}
        title="No items"
        description="There are no items to display"
      />
    );

    expect(screen.getByText('No items')).toBeInTheDocument();
    expect(screen.getByText('There are no items to display')).toBeInTheDocument();
  });

  it('should render action button when provided', async () => {
    const user = userEvent.setup();
    const handleAction = vi.fn();

    render(
      <EmptyState
        icon={Bot}
        title="No items"
        description="Create your first item"
        action={{
          label: 'Create Item',
          onClick: handleAction,
        }}
      />
    );

    const button = screen.getByRole('button', { name: 'Create Item' });
    expect(button).toBeInTheDocument();

    await user.click(button);
    expect(handleAction).toHaveBeenCalled();
  });

  it('should not render action button when not provided', () => {
    render(
      <EmptyState
        icon={Bot}
        title="No items"
        description="There are no items"
      />
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
