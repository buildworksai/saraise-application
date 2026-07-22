/* eslint-disable react-refresh/only-export-components */
import type { FormEvent, ReactNode } from 'react';
import { AlertCircle, ArrowLeft, Ban, CheckCircle2, ChevronLeft, ChevronRight, FileQuestion, LoaderCircle, LockKeyhole, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { ApiError as ClientApiError } from '@/services/api-client';
import { useAuthStore } from '@/stores/auth-store';
import type { JsonValue, PaginatedMeta } from '../contracts';

export function useCanManageIntegrations(): boolean {
  return useAuthStore((state) => state.user?.is_superuser === true || state.user?.is_staff === true || state.user?.tenant_role === 'tenant_admin');
}

export function PageHeader({ title, description, actions, backTo }: { title: string; description: string; actions?: ReactNode; backTo?: { label: string; path: string } }) {
  return <header className="space-y-4">
    {backTo && <Link className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={backTo.path}><ArrowLeft className="h-4 w-4" />{backTo.label}</Link>}
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h1 className="text-3xl font-bold tracking-tight">{title}</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</div>
  </header>;
}

export function PageSkeleton({ label = 'Loading page' }: { label?: string }) {
  return <main className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label={label}><div className="space-y-3"><Skeleton className="h-9 w-64" /><Skeleton className="h-4 w-full max-w-xl" /></div><Card className="p-6"><TableSkeleton rows={6} columns={4} /></Card></main>;
}

export function BackgroundRefresh({ active }: { active: boolean }) {
  return <div className="h-5 text-xs text-muted-foreground" role="status" aria-live="polite">{active && <span className="inline-flex items-center gap-2"><LoaderCircle className="h-3.5 w-3.5 animate-spin" />Refreshing evidence…</span>}</div>;
}

export function GovernedError({ error, retry }: { error: Error | null; retry: () => void }) {
  const apiError = error instanceof ClientApiError ? error : null;
  const forbidden = apiError?.status === 403;
  const missing = apiError?.status === 404;
  const Icon = forbidden ? LockKeyhole : missing ? FileQuestion : AlertCircle;
  const title = forbidden ? 'Access denied' : missing ? 'Record not found' : 'Integration Platform is unavailable';
  const message = forbidden ? 'Your current tenant role does not grant this governed action.' : missing ? 'This record does not exist or belongs to another tenant.' : apiError?.message ?? error?.message ?? 'The governed API could not complete this request.';
  return <Card className="p-8 text-center" role="alert"><Icon className="mx-auto h-12 w-12 text-destructive" /><h2 className="mt-4 text-xl font-semibold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>{apiError?.correlationId && <p className="mt-3 font-mono text-xs">Correlation ID: {apiError.correlationId}</p>}<Button className="mt-6" variant="secondary" onClick={retry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button></Card>;
}

export function EmptyPanel({ filtered, title, description, action, reset }: { filtered: boolean; title: string; description: string; action?: ReactNode; reset?: () => void }) {
  return <Card className="p-10 text-center"><Ban className="mx-auto h-10 w-10 text-muted-foreground" /><h2 className="mt-4 text-lg font-semibold">{filtered ? `No matching ${title}` : title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{filtered ? 'No records match the selected server-side filters.' : description}</p><div className="mt-5 flex justify-center gap-2">{filtered && reset ? <Button variant="secondary" onClick={reset}>Reset filters</Button> : action}</div></Card>;
}

export function StatusBadge({ status }: { status: string }) {
  const positive = ['active', 'healthy', 'delivered', 'succeeded', 'closed'].includes(status);
  const danger = ['error', 'unavailable', 'failed', 'dead_letter', 'open', 'revoked', 'expired'].includes(status);
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${positive ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : danger ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300'}`}>{status.replaceAll('_', ' ')}</span>;
}

export function Pagination({ meta, changePage }: { meta: PaginatedMeta; changePage: (page: number) => void }) {
  return <nav className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination"><p>{meta.count} results · Page {meta.page} of {Math.max(meta.total_pages, 1)}</p><div className="flex gap-2"><Button size="sm" variant="secondary" disabled={!meta.has_previous} onClick={() => changePage(meta.page - 1)}><ChevronLeft className="mr-1 h-4 w-4" />Previous</Button><Button size="sm" variant="secondary" disabled={!meta.has_next} onClick={() => changePage(meta.page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4" /></Button></div></nav>;
}

export function DefinitionGrid({ children }: { children: ReactNode }) { return <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>; }
export function Definition({ label, children }: { label: string; children: ReactNode }) { return <div className="rounded-lg border p-4"><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-2 break-words text-sm">{children}</dd></div>; }
export function EvidenceCard({ title, children }: { title: string; children: ReactNode }) { return <Card className="p-6"><h2 className="mb-4 text-lg font-semibold">{title}</h2>{children}</Card>; }

export function RedactedJsonViewer({ value, label }: { value: JsonValue; label: string }) { return <div><p className="mb-2 text-sm font-medium">{label}</p><pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-4 text-xs" aria-label={`${label}, redacted evidence`}>{JSON.stringify(value, null, 2)}</pre><p className="mt-2 text-xs text-muted-foreground">Sensitive fields are redacted by the server before persistence.</p></div>; }

export function SuccessEvidence({ title, correlationId, detail }: { title: string; correlationId?: string; detail?: string }) { return <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm" role="status" tabIndex={-1}><div className="flex items-center gap-2 font-medium text-emerald-800 dark:text-emerald-200"><CheckCircle2 className="h-4 w-4" />{title}</div>{detail && <p className="mt-2">{detail}</p>}{correlationId && <p className="mt-2 font-mono text-xs">Correlation ID: {correlationId}</p>}</div>; }

export function FilterForm({ children, submit }: { children: ReactNode; submit: (form: FormData) => void }) {
  const onSubmit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); submit(new FormData(event.currentTarget)); };
  return <Card className="p-4"><form className="grid gap-3 md:grid-cols-4" role="search" onSubmit={onSubmit}>{children}</form></Card>;
}

export function formatDate(value: string | null): string { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not yet'; }
export function newOperationKey(prefix: string): string { return `${prefix}-${crypto.randomUUID()}`; }
