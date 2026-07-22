/* eslint-disable react-refresh/only-export-components -- HR components and their small shared hooks intentionally live together. */
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { AlertCircle, ArrowLeft, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { HrApiError } from '../services/hr-service';

export function PageShell({ title, description, back, actions, children }: {
  title: string; description: string; back?: () => void; actions?: ReactNode; children: ReactNode;
}) {
  return <main className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
    <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-2">
        {back ? <Button type="button" size="icon" variant="ghost" onClick={back} aria-label="Go back" className="min-h-11 min-w-11"><ArrowLeft className="h-5 w-5" /></Button> : null}
        <div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
    {children}
  </main>;
}

export function PageSkeleton({ cards = 3, rows = 5 }: { cards?: number; rows?: number }) {
  return <div role="status" aria-label="Loading Human Resources" className="mx-auto max-w-[1500px] animate-pulse space-y-6 p-4 sm:p-8">
    <div className="h-9 w-64 rounded bg-muted" /><div className="h-4 w-full max-w-xl rounded bg-muted" />
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: cards }, (_, index) => <div key={index} className="h-28 rounded-xl border bg-muted/50" />)}</div>
    <div className="rounded-xl border p-4">{Array.from({ length: rows }, (_, index) => <div key={index} className="mb-3 h-12 rounded bg-muted last:mb-0" />)}</div>
    <span className="sr-only">Loading…</span>
  </div>;
}

export function GovernedError({ error, retry, resource = 'record' }: { error: unknown; retry?: () => void; resource?: string }) {
  const normalized = error instanceof HrApiError ? error : null;
  const notFound = normalized?.kind === 'not_found';
  const denied = normalized?.kind === 'permission';
  const title = notFound ? `${resource} not found` : denied ? 'Access denied' : 'Human Resources is unavailable';
  const message = notFound ? `This ${resource.toLowerCase()} may have been archived or is outside your tenant.`
    : denied ? `Your access policy does not allow this ${resource.toLowerCase()}. Ask an administrator if you need access.`
      : normalized?.message ?? 'The request could not be completed safely.';
  return <Card><CardContent className="flex min-h-80 flex-col items-center justify-center p-8 text-center" role="alert">
    <span className="rounded-full bg-destructive/10 p-4"><AlertCircle className="h-10 w-10 text-destructive" /></span>
    <h2 className="mt-4 text-xl font-semibold">{title}</h2><p className="mt-2 max-w-xl text-sm text-muted-foreground">{message}</p>
    {normalized?.correlationId ? <p className="mt-3 rounded bg-muted px-3 py-2 font-mono text-xs">Correlation ID: {normalized.correlationId}</p> : null}
    {retry && !notFound && !denied ? <Button type="button" variant="outline" onClick={retry} className="mt-5 min-h-11"><RefreshCw className="mr-2 h-4 w-4" />Try again</Button> : null}
  </CardContent></Card>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: { label: string; onClick: () => void } }) {
  return <Card><CardContent className="flex min-h-72 flex-col items-center justify-center p-8 text-center">
    <span className="rounded-full bg-muted p-4"><Inbox className="h-10 w-10 text-muted-foreground" /></span>
    <h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>
    {action ? <Button type="button" className="mt-5 min-h-11" onClick={action.onClick}>{action.label}</Button> : null}
  </CardContent></Card>;
}

export function StatusChip({ status }: { status: string }) {
  const tone = ['active', 'present', 'approved', 'ready', 'healthy'].includes(status) ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
    : ['pending', 'late', 'on_leave', 'half_day'].includes(status) ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
      : ['rejected', 'terminated', 'not_ready', 'unhealthy'].includes(status) ? 'border-destructive/30 bg-destructive/10 text-destructive'
        : 'border-border bg-muted text-muted-foreground';
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}>{status.replaceAll('_', ' ')}</span>;
}

export function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  if (totalPages < 2) return null;
  return <nav aria-label="Pagination" className="flex items-center justify-between border-t px-4 py-4">
    <Button variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)} className="min-h-11">Previous</Button>
    <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
    <Button variant="outline" disabled={page >= totalPages} onClick={() => onPage(page + 1)} className="min-h-11">Next</Button>
  </nav>;
}

export function ConfirmAction({ open, title, description, confirmLabel, pending, danger = false, onOpenChange, onConfirm }: {
  open: boolean; title: string; description: string; confirmLabel: string; pending: boolean; danger?: boolean;
  onOpenChange: (open: boolean) => void; onConfirm: () => void;
}) {
  return <Dialog open={open} onOpenChange={(next) => { if (!pending) onOpenChange(next); }} title={title} description={description} size="sm">
    <div className="mt-4 flex justify-end gap-3"><Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} className="min-h-11">Keep</Button>
      <Button variant={danger ? 'danger' : 'primary'} disabled={pending} onClick={onConfirm} className="min-h-11">
        {pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}{pending ? 'Working…' : confirmLabel}
      </Button></div>
  </Dialog>;
}

export function FormError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-destructive" role="alert">{message}</p> : null;
}

export function useUnsavedChanges(dirty: boolean) {
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  useEffect(() => {
    const listener = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', listener);
    return () => window.removeEventListener('beforeunload', listener);
  }, [dirty]);
  const requestNavigation = (navigate: () => void) => {
    if (!dirty) navigate(); else { setPendingNavigation(() => navigate); setLeaveOpen(true); }
  };
  const dialog = <ConfirmAction open={leaveOpen} title="Discard unsaved changes?" description="Your edits have not been saved." confirmLabel="Discard changes" danger onOpenChange={setLeaveOpen} pending={false} onConfirm={() => { setLeaveOpen(false); pendingNavigation?.(); }} />;
  return { requestNavigation, dialog };
}

export function formatDate(value: string | null): string {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(`${value.slice(0, 10)}T00:00:00`));
}
export function formatInstant(value: string | null): string {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

export function DetailGrid({ children }: { children: ReactNode }) { return <dl className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>; }
export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 text-sm">{children}</dd></div>;
}

/** Governed actions fail closed when the response has no explicit capability decision. */
export function can(capabilities: readonly string[], permission: string): boolean {
  return capabilities.includes(permission);
}
