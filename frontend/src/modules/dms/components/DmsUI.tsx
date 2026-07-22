/* eslint-disable react-refresh/only-export-components -- cohesive module UI primitives and formatting helpers. */
import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, FileQuestion, FolderOpen, LockKeyhole, RefreshCw, SearchX, ServerOff } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type { DmsAllowedAction, DownloadResult, Folder, PaginationMeta } from '../contracts';
import { DmsApiError } from '../services/dms-service';

export function PageHeader({ title, description, actions }: { readonly title: string; readonly description: string; readonly actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ rows = 6, label = 'Loading document management' }: { readonly rows?: number; readonly label?: string }) {
  return <main aria-busy="true" aria-label={label} className="space-y-6 p-4 sm:p-8"><Skeleton className="h-20 w-full"/><div className="grid gap-5 lg:grid-cols-[260px_1fr]"><Skeleton className="h-[480px]"/><div className="space-y-3 rounded-xl border p-4">{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-16 w-full"/>)}</div></div></main>;
}

export function RefreshStatus({ active }: { readonly active: boolean }) {
  return active ? <p role="status" aria-live="polite" className="flex items-center gap-2 text-xs text-muted-foreground"><RefreshCw className="h-3.5 w-3.5 animate-spin"/>Refreshing documents…</p> : null;
}

export function ApiProblem({ error, onRetry }: { readonly error: Error; readonly onRetry?: () => void }) {
  const problem = error instanceof DmsApiError ? error.problem : null;
  const view = problem?.kind === 'denied'
    ? { title: 'Access denied', message: 'Your current policy does not allow this document-management action.', Icon: LockKeyhole }
    : problem?.kind === 'not_found'
      ? { title: 'Document unavailable', message: 'This item no longer exists or is outside the boundary you can access.', Icon: SearchX }
      : problem?.kind === 'unavailable'
        ? { title: 'Document storage unavailable', message: 'The dependency is not ready. No operation has been reported as successful; retry when it recovers.', Icon: ServerOff }
        : problem?.kind === 'conflict'
          ? { title: 'A newer revision exists', message: 'Reload the current record, review the newer values, and apply your change again.', Icon: RefreshCw }
          : { title: 'Document request failed', message: problem?.message ?? error.message ?? 'The governed request failed safely.', Icon: AlertTriangle };
  const Icon = view.Icon;
  return <Card role="alert" className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><Icon className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mt-2 max-w-xl text-sm text-muted-foreground">{view.message}</p>{problem?.correlation_id ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {problem.correlation_id}</p> : null}{onRetry ? <Button className="mt-5" variant="outline" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</Card>;
}

export function MutationProblem({ error }: { readonly error: Error }) {
  const fields = error instanceof DmsApiError && error.problem.kind === 'validation' ? error.problem.field_errors : [];
  return <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4"><p className="font-medium text-destructive">{error.message}</p>{fields.length ? <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">{fields.map((item) => <li key={`${item.field}:${item.code}`}>{item.field}: {item.message}</li>)}</ul> : null}</div>;
}

export function EmptyPanel({ filtered, folder, onReset, action }: { readonly filtered: boolean; readonly folder: boolean; readonly onReset?: () => void; readonly action?: ReactNode }) {
  const Icon = folder ? FolderOpen : FileQuestion;
  return <section className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed bg-card p-8 text-center"><Icon className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{filtered ? 'No documents match these filters' : folder ? 'This folder is empty' : 'No documents yet'}</h2><p className="mt-2 max-w-md text-sm text-muted-foreground">{filtered ? 'Clear or broaden the server-side filters.' : 'Upload a document or create a folder to build a governed workspace.'}</p>{filtered && onReset ? <Button className="mt-5" variant="outline" onClick={onReset}>Clear filters</Button> : action ? <div className="mt-5">{action}</div> : null}</section>;
}

export function Pagination({ value, onPage }: { readonly value: PaginationMeta; readonly onPage: (page: number) => void }) {
  return <nav aria-label="Pagination" className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between"><p>Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} documents</p><div className="flex gap-2"><Button size="sm" variant="outline" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}>Previous</Button><Button size="sm" variant="outline" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next</Button></div></nav>;
}

export function Breadcrumbs({ folders, onRoot }: { readonly folders: readonly Folder[]; readonly onRoot?: () => void }) {
  return <nav aria-label="Folder breadcrumbs" className="flex flex-wrap items-center gap-1 text-sm"><button className="rounded px-1.5 py-1 text-primary hover:underline focus-visible:ring-2" onClick={onRoot}>Documents</button>{folders.map((folder) => <span key={folder.id} className="flex items-center gap-1"><span aria-hidden className="text-muted-foreground">/</span><span className="px-1.5 py-1">{folder.name}</span></span>)}</nav>;
}

export function can(actions: readonly DmsAllowedAction[], action: DmsAllowedAction): boolean {
  if (actions.includes(action)) return true;
  if (action === 'update' || action === 'move' || action === 'create_version' || action === 'restore_version') return actions.includes('write') || actions.includes('manage');
  if (action === 'manage_permissions') return actions.includes('manage');
  return false;
}
export function formatDate(value: string | null | undefined): string { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'; }
export function formatBytes(value: number | undefined): string { if (value === undefined) return '—'; if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`; return `${(value / 1024 ** 2).toFixed(1)} MiB`; }

export function saveDownload(result: DownloadResult): void {
  const url = URL.createObjectURL(result.blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = result.filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
}
