import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ActionDialog } from './ActionDialog';

describe('ActionDialog', () => {
  it('uses a labelled modal and disables its explicit pending action', () => {
    render(<ActionDialog open onOpenChange={() => undefined} title="Cancel extraction?" description="Evidence remains retained." confirmLabel="Cancel extraction" pending onConfirm={() => Promise.resolve()} destructive />);
    expect(screen.getByRole('dialog', { name: 'Cancel extraction?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel extraction…' })).toBeDisabled();
  });

  it('runs confirmed domain actions and closes only after success', async () => {
    const action = vi.fn(() => Promise.resolve()); const close = vi.fn();
    render(<ActionDialog open onOpenChange={close} title="Activate model?" description="Readiness is validated." confirmLabel="Activate" pending={false} onConfirm={action} />);
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    await waitFor(() => expect(action).toHaveBeenCalledOnce());
    expect(close).toHaveBeenCalledWith(false);
  });
});
