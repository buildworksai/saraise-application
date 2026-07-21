import { useState, type ReactNode } from 'react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

export function ActionDialog({
  open, onOpenChange, title, description, confirmLabel, pending, onConfirm, children, destructive = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  pending: boolean;
  onConfirm: () => Promise<void>;
  children?: ReactNode;
  destructive?: boolean;
}) {
  const [localError, setLocalError] = useState<string | null>(null);
  const confirm = async () => {
    setLocalError(null);
    try { await onConfirm(); onOpenChange(false); } catch { setLocalError('The action failed. Review the page error and retry.'); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description} size="md">
      <div className="space-y-4">
        {children}
        {localError && <p className="text-sm text-destructive" role="alert">{localError}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" disabled={pending} onClick={() => onOpenChange(false)}>Keep unchanged</Button>
          <Button variant={destructive ? 'danger' : 'primary'} disabled={pending} aria-busy={pending} onClick={() => { void confirm(); }}>{pending ? `${confirmLabel}…` : confirmLabel}</Button>
        </div>
      </div>
    </Dialog>
  );
}
