/**
 * Dialog Component Tests
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Dialog, ConfirmDialog } from './Dialog';

describe('Dialog', () => {
  it('should render when open', () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()}>
        <div>Dialog Content</div>
      </Dialog>
    );
    expect(screen.getByText('Dialog Content')).toBeInTheDocument();
  });

  it('should not render when closed', () => {
    render(
      <Dialog open={false} onOpenChange={vi.fn()}>
        <div>Dialog Content</div>
      </Dialog>
    );
    expect(screen.queryByText('Dialog Content')).not.toBeInTheDocument();
  });

  it('should render title when provided', () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()} title="Test Dialog">
        <div>Content</div>
      </Dialog>
    );
    expect(screen.getByText('Test Dialog')).toBeInTheDocument();
  });

  it('should render description when provided', () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()} description="Test description">
        <div>Content</div>
      </Dialog>
    );
    expect(screen.getByText('Test description')).toBeInTheDocument();
  });

  it('should call onOpenChange when close button is clicked', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <Dialog open={true} onOpenChange={onOpenChange}>
        <div>Content</div>
      </Dialog>
    );

    const closeButton = screen.getByRole('button');
    await user.click(closeButton);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe('ConfirmDialog', () => {
  it('should render title and description', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm Action"
        description="Are you sure?"
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByText('Confirm Action')).toBeInTheDocument();
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
  });

  it('should call onConfirm when confirm button is clicked', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm"
        description="Are you sure?"
        onConfirm={onConfirm}
      />
    );

    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    await user.click(confirmButton);
    expect(onConfirm).toHaveBeenCalled();
  });

  it('should call onOpenChange(false) when cancel is clicked', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        title="Confirm"
        description="Are you sure?"
        onConfirm={vi.fn()}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('should use custom button labels', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm"
        description="Are you sure?"
        confirmLabel="Yes, delete"
        cancelLabel="No, keep"
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: 'Yes, delete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'No, keep' })).toBeInTheDocument();
  });
});
