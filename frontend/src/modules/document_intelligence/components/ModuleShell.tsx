import type { ReactNode } from 'react';
import { AlertCircle, Clock3, FileQuestion, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { DocumentIntelligenceApiError } from '../services/document-intelligence-service';
import type { PaginationMeta } from '../contracts';

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function PageSkeleton({ cards = 3, table = true }: { cards?: number; table?: boolean }) {
  return (
    <div className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label="Loading document intelligence">
      <div className="space-y-3"><Skeleton className="h-9 w-72" /><Skeleton className="h-4 w-full max-w-xl" /></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: cards }, (_, index) => <Skeleton key={index} className="h-28" />)}
      </div>
      {table && <TableSkeleton rows={6} columns={5} />}
    </div>
  );
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <Card className="flex min-h-72 flex-col items-center justify-center p-8 text-center">
      <div className="rounded-full bg-muted p-4"><FileQuestion className="h-8 w-8 text-muted-foreground" /></div>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}

export function ApiProblem({ error, onRetry, inline = false }: { error: unknown; onRetry: () => void; inline?: boolean }) {
  const apiError = error instanceof DocumentIntelligenceApiError ? error : null;
  const isDenied = apiError?.status === 401 || apiError?.status === 403 || apiError?.status === 404;
  const quota = apiError?.status === 429 ? apiError.detail.quota : undefined;
  const title = isDenied ? 'Access unavailable' : quota ? 'Processing quota reached' : 'Document intelligence unavailable';
  const message = isDenied
    ? 'You do not have access to this record or action.'
    : quota
      ? `${quota.remaining} units remain. ${quota.reset_at ? `Quota resets ${new Date(quota.reset_at).toLocaleString()}.` : 'Contact your tenant administrator for quota access.'}`
      : apiError?.message ?? 'The request could not be completed. Try again or share the correlation ID with support.';
  return (
    <Card className={`flex flex-col items-center justify-center text-center ${inline ? 'p-5' : 'min-h-96 p-8'}`} role="alert">
      <div className="rounded-full bg-destructive/10 p-4"><AlertCircle className="h-8 w-8 text-destructive" /></div>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>
      {apiError?.correlationId && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {apiError.correlationId}</p>}
      <Button className="mt-5" variant="secondary" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>
    </Card>
  );
}

export function MetricCard({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <Card className="p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></Card>;
}

export function StatusPill({ status }: { status: string }) {
  const positive = ['active', 'completed', 'confirmed', 'healthy'].includes(status);
  const warning = ['queued', 'processing', 'training', 'pending', 'needs_review', 'candidate', 'degraded'].includes(status);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${positive ? 'bg-green-500/15 text-green-700 dark:text-green-300' : warning ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300' : 'bg-muted text-muted-foreground'}`}>{status.replaceAll('_', ' ')}</span>;
}

export function Pagination({ value, onPage }: { value: PaginationMeta; onPage: (page: number) => void }) {
  return (
    <nav className="flex items-center justify-between gap-3 border-t p-4" aria-label="Pagination">
      <p className="text-sm text-muted-foreground">Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}>Previous</Button>
        <Button variant="outline" size="sm" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next</Button>
      </div>
    </nav>
  );
}

export function StaleIndicator({ updatedAt, active }: { updatedAt: number; active: boolean }) {
  const stale = Date.now() - updatedAt > 15_000;
  return <p className={`flex items-center gap-1 text-xs ${stale ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground'}`} aria-live="polite"><Clock3 className="h-3.5 w-3.5" />{active ? 'Auto-refreshing active work' : 'Snapshot'} · updated {new Date(updatedAt).toLocaleTimeString()}{stale ? ' · stale' : ''}</p>;
}
