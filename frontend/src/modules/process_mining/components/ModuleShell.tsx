import type { ReactNode } from 'react';
import { AlertCircle, Clock3, DatabaseZap, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import type { PaginationMeta } from '../contracts';
import { ProcessMiningApiError } from '../services/process_mining-service';

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h1 className="text-3xl font-bold tracking-tight">{title}</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</header>;
}

export function PageSkeleton({ cards = 3, table = true }: { cards?: number; table?: boolean }) {
  return <main className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label="Loading process mining"><div className="space-y-3"><Skeleton className="h-9 w-72"/><Skeleton className="h-4 w-full max-w-xl"/></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: cards }, (_, index) => <Skeleton key={index} className="h-28"/>)}</div>{table && <TableSkeleton rows={6} columns={5}/>}</main>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <Card className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><div className="rounded-full bg-muted p-4"><DatabaseZap className="h-8 w-8 text-muted-foreground"/></div><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action && <div className="mt-5">{action}</div>}</Card>;
}

export function ApiProblem({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const problem = error instanceof ProcessMiningApiError ? error : null;
  const notFound = problem?.status === 404;
  const denied = problem?.status === 401 || problem?.status === 403;
  const unavailable = problem?.status === 503;
  const quota = problem?.status === 429;
  const title = notFound ? 'Evidence not found' : denied ? 'Access unavailable' : quota ? 'Quota reached' : unavailable ? 'Capability unavailable' : 'Process mining unavailable';
  const message = notFound ? 'This record does not exist in your tenant or is no longer available.' : denied ? 'Your current access policy does not permit this view or action.' : quota ? 'This tenant has reached the governed quota for the operation.' : unavailable ? 'A required durable-processing, storage, or adapter capability is not ready.' : problem?.message ?? 'The request could not be completed.';
  return <Card role="alert" className="flex min-h-80 flex-col items-center justify-center p-8 text-center"><div className="rounded-full bg-destructive/10 p-4"><AlertCircle className="h-8 w-8 text-destructive"/></div><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>{problem?.correlationId && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {problem.correlationId}</p>}<Button className="mt-5" variant="secondary" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button></Card>;
}

export function MetricCard({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <Card className="p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></Card>;
}

export function StatusPill({ status }: { status: string }) {
  const positive = ['healthy', 'completed'].includes(status);
  const active = ['queued', 'running'].includes(status);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${positive ? 'bg-accent text-accent-foreground' : active ? 'bg-primary/10 text-primary' : status === 'failed' || status === 'unavailable' ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'}`}>{status.replaceAll('_', ' ')}</span>;
}

export function Pagination({ value, onPage }: { value: PaginationMeta; onPage: (page: number) => void }) {
  return <nav className="flex items-center justify-between gap-3 border-t p-4" aria-label="Pagination"><p className="text-sm text-muted-foreground">Page {value.page} of {Math.max(1, value.total_pages)} · {value.count} records</p><div className="flex gap-2"><Button size="sm" variant="outline" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}>Previous</Button><Button size="sm" variant="outline" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next</Button></div></nav>;
}

export function StaleIndicator({ updatedAt, active }: { updatedAt: number; active: boolean }) {
  const stale = Date.now() - updatedAt > 15_000;
  return <p className={`flex items-center gap-1 text-xs ${stale ? 'text-destructive' : 'text-muted-foreground'}`} aria-live="polite"><Clock3 className="h-3.5 w-3.5"/>{active ? 'Auto-refreshing durable work' : 'Evidence snapshot'} · updated {new Date(updatedAt).toLocaleTimeString()}{stale ? ' · stale' : ''}</p>;
}

export function DataTable({ headers, rows }: { headers: readonly string[]; rows: readonly (readonly ReactNode[])[] }) {
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground"><tr>{headers.map((header) => <th key={header} className="p-4">{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-b align-top hover:bg-muted/40">{row.map((cell, cellIndex) => <td key={cellIndex} className="p-4">{cell}</td>)}</tr>)}</tbody></table></div>;
}
