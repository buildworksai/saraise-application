/* eslint-disable react-refresh/only-export-components */
import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, ArrowLeft, FolderOpen, LockKeyhole, RefreshCw, SearchX } from 'lucide-react';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Skeleton } from '@/components/ui/Skeleton';
import type { AllowedCommand, CommandAffordance, CommandDenialReasons, PaginationMeta, ServerAllowedCommand } from '../contracts';
import { FixedAssetsApiError } from '../services/fixed-assets-service';

export function formatMoney(value: string, currency = 'USD'): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return `${currency} ${value}`;
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(number); }
  catch { return `${currency} ${number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
}

export function formatDateOnly(value: string | null | undefined): string {
  if (!value) return '—';
  const parts = value.split('-').map(Number);
  const year = parts[0]; const month = parts[1]; const day = parts[2];
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);
}

export function PageHeader({ title, description, backLabel, onBack, actions }: { title: string; description?: string; backLabel?: string; onBack?: () => void; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div>{onBack && <Button variant="ghost" className="mb-2 -ml-3" onClick={onBack}><ArrowLeft className="mr-2 h-4 w-4"/>{backLabel ?? 'Back'}</Button>}<h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>{description && <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>}</div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</header>;
}

export function PageSkeleton({ table = false }: { table?: boolean }) {
  return <main className="space-y-6 p-4 sm:p-8" aria-label="Loading fixed asset information" aria-busy="true"><div className="space-y-3"><Skeleton className="h-8 w-56"/><Skeleton className="h-4 w-full max-w-xl"/></div><div className={table ? 'space-y-2' : 'grid gap-4 sm:grid-cols-2 lg:grid-cols-4'}>{Array.from({ length: table ? 7 : 4 }, (_, index) => <Skeleton key={index} className={table ? 'h-12 w-full' : 'h-32 w-full'}/>)}</div></main>;
}

function asModuleError(error: unknown): { status?: number; message: string; correlation?: string | null } {
  if (error instanceof FixedAssetsApiError) return { status: error.status, message: error.message, correlation: error.correlationId };
  if (error instanceof ApiError) return { status: error.status, message: error.message, correlation: error.correlationId };
  return { message: error instanceof Error ? error.message : 'The governed request failed safely.' };
}

export function ProblemState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const problem = asModuleError(error);
  const forbidden = problem.status === 403; const missing = problem.status === 404;
  const Icon = forbidden ? LockKeyhole : missing ? SearchX : AlertTriangle;
  const title = forbidden ? 'Access denied' : missing ? 'Record not found' : 'We could not load this view';
  const message = forbidden ? 'Your current policy does not allow this action. No resource existence has been disclosed.' : missing ? 'The record is unavailable or belongs to another tenant.' : problem.message;
  return <Card role="alert" className="flex min-h-80 flex-col items-center justify-center p-8 text-center"><div className="rounded-full bg-destructive/10 p-4"><Icon className="h-8 w-8 text-destructive"/></div><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>{problem.correlation && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {problem.correlation}</p>}{onRetry && !forbidden && !missing && <Button className="mt-5" variant="secondary" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button>}</Card>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: { label: string; onClick: () => void } }) {
  return <Card className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><FolderOpen className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>{action && <Button className="mt-5" onClick={action.onClick}>{action.label}</Button>}</Card>;
}

export function Pagination({ meta, onPage }: { meta: PaginationMeta; onPage: (page: number) => void }) {
  return <nav aria-label="Pagination" className="flex items-center justify-between border-t p-4"><p className="text-sm text-muted-foreground">Page {meta.page} of {Math.max(meta.total_pages, 1)} · {meta.count} records</p><div className="flex gap-2"><Button variant="secondary" disabled={!meta.has_previous} onClick={() => onPage(meta.page - 1)}>Previous</Button><Button variant="secondary" disabled={!meta.has_next} onClick={() => onPage(meta.page + 1)}>Next</Button></div></nav>;
}

export function commandAffordance(commands: readonly ServerAllowedCommand[] | undefined, command: AllowedCommand, denialReasons?: CommandDenialReasons): CommandAffordance {
  const serverCommand = command === 'edit' ? 'update' : command;
  const allowed = commands?.includes(serverCommand) ?? false;
  const denialCode = denialReasons?.[serverCommand];
  return { command, allowed, denial_code: denialCode, explanation: allowed ? undefined : denialCode ? `The server denied this command: ${denialCode}.` : 'The server did not grant this command.' };
}

export function CommandButton({ affordance, children, onClick, variant = 'secondary' }: { affordance: CommandAffordance; children: ReactNode; onClick: () => void; variant?: 'primary' | 'secondary' | 'danger' }) {
  return <span title={!affordance.allowed ? affordance.explanation ?? affordance.denial_code : undefined}><Button variant={variant} disabled={!affordance.allowed} aria-disabled={!affordance.allowed} aria-describedby={!affordance.allowed ? `command-${affordance.command}-reason` : undefined} onClick={onClick}>{children}</Button>{!affordance.allowed && <span id={`command-${affordance.command}-reason`} className="sr-only">{affordance.explanation ?? affordance.denial_code}</span>}</span>;
}

export function StatusPill({ value }: { value: string }) {
  const danger = value === 'failed'; const success = value === 'active' || value === 'posted' || value === 'completed' || value === 'succeeded';
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${danger ? 'border-destructive/30 bg-destructive/10 text-destructive' : success ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300' : 'border-border bg-muted text-muted-foreground'}`}>{titleCase(value)}</span>;
}

export function UnsavedChangesDialog({ open, onOpenChange, onDiscard }: { open: boolean; onOpenChange: (open: boolean) => void; onDiscard: () => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange} title="Discard unsaved changes?" description="Your edits have not been sent to the server and will be lost."><div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => onOpenChange(false)}>Keep editing</Button><Button variant="danger" onClick={onDiscard}>Discard changes</Button></div></Dialog>;
}
