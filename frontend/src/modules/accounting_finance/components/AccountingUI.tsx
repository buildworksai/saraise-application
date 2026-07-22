import type { ReactNode } from 'react';
import { AlertCircle, Ban, CloudOff, FileQuestion, Loader2, LockKeyhole, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/auth-store';
import { AccountingApiError } from '../services/accounting-service';

export function AccountingPageSkeleton({ rows = 5 }: { rows?: number }) {
  return <div className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label="Loading accounting information"><div className="flex items-center justify-between"><Skeleton className="h-9 w-64" /><Skeleton className="h-10 w-32" /></div><Card className="space-y-4 p-6">{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-12 w-full" />)}</Card></div>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>{description ? <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p> : null}</div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center"><FileQuestion className="mb-3 h-10 w-10 text-muted-foreground" aria-hidden="true" /><h2 className="text-lg font-semibold">{title}</h2><p className="mt-1 max-w-lg text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</Card>;
}

const failureCopy = {
  'not-found': { title: 'Record not found', icon: FileQuestion },
  permission: { title: 'Access denied', icon: LockKeyhole },
  conflict: { title: 'Action needs attention', icon: Ban },
  dependency: { title: 'Accounting dependency unavailable', icon: CloudOff },
  network: { title: 'Connection interrupted', icon: CloudOff },
  validation: { title: 'Check the highlighted information', icon: AlertCircle },
  unknown: { title: 'Unable to load accounting information', icon: AlertCircle },
} as const;

export function AccountingFailure({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const normalized = error instanceof AccountingApiError ? error : new AccountingApiError('An unexpected accounting error occurred.', 0, 'UNKNOWN_ERROR', null, null);
  const copy = failureCopy[normalized.kind];
  const Icon = copy.icon;
  return <Card className="mx-auto max-w-2xl p-8 text-center" role="alert"><Icon className="mx-auto h-10 w-10 text-destructive" aria-hidden="true" /><h2 className="mt-3 text-xl font-semibold">{copy.title}</h2><p className="mt-2 text-sm text-muted-foreground">{normalized.message}</p>{normalized.detail ? <p className="mt-2 text-sm">{normalized.detail}</p> : null}{normalized.correlationId ? <p className="mt-4 font-mono text-xs text-muted-foreground">Reference {normalized.correlationId}</p> : null}{onRetry && !['not-found', 'permission'].includes(normalized.kind) ? <Button className="mt-5" variant="outline" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button> : null}</Card>;
}

export function Pagination({ page, pagination, onPage }: { page: number; pagination: { has_previous: boolean; has_next: boolean; count: number; total_pages: number }; onPage: (page: number) => void }) {
  return <nav className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination"><span className="text-muted-foreground">{pagination.count} records · page {page} of {Math.max(1, pagination.total_pages)}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!pagination.has_previous} onClick={() => onPage(page - 1)}>Previous</Button><Button variant="outline" size="sm" disabled={!pagination.has_next} onClick={() => onPage(page + 1)}>Next</Button></div></nav>;
}

export function ActionDialog({ open, onOpenChange, title, consequence, confirmLabel, pending, reasonRequired = false, onConfirm }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; consequence: string; confirmLabel: string; pending: boolean; reasonRequired?: boolean; onConfirm: (reason: string) => void }) {
  let reason = '';
  return <Dialog open={open} onOpenChange={onOpenChange} title={title} description={consequence} size="md"><form onSubmit={(event) => { event.preventDefault(); onConfirm(reason); }} className="space-y-4">{reasonRequired ? <div><label className="mb-1 block text-sm font-medium" htmlFor="accounting-action-reason">Reason</label><textarea id="accounting-action-reason" required className="min-h-24 w-full rounded-md border bg-background p-3" onChange={(event) => { reason = event.target.value; }} /></div> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>Cancel</Button><Button type="submit" variant="danger" disabled={pending}>{pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}{confirmLabel}</Button></div></form></Dialog>;
}

export function useAccountingAccess() {
  const role = useAuthStore((state) => state.user?.tenant_role);
  const isAdmin = role === 'tenant_admin' || role === 'admin';
  const isOperator = isAdmin || role === 'operator';
  const canDraft = isOperator || role === 'user' || role === 'tenant_user';
  return { canRead: Boolean(role), canDraft, canOperate: isOperator, canAdminister: isAdmin };
}

export function formatMoney(amount: string, currency = 'USD'): string {
  const parsed = Number(amount);
  if (!Number.isFinite(parsed)) return `${currency} ${amount}`;
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(parsed);
}

export function StatusPill({ status }: { status: string }) {
  return <span className="inline-flex rounded-full border bg-muted px-2 py-0.5 text-xs font-medium capitalize">{status.replaceAll('_', ' ')}</span>;
}
