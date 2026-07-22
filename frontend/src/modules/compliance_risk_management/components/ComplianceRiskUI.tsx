/* eslint-disable react-refresh/only-export-components */
import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, ArrowLeft, FileQuestion, LockKeyhole, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/auth-store';
import { ComplianceRiskApiError } from '../services/compliance-risk-service';
import type { ApiPageMeta, GovernedFieldError } from '../contracts';

export function useDocumentTitle(title: string): void {
  useEffect(() => { const previous = document.title; document.title = `${title} · SARAISE`; return () => { document.title = previous; }; }, [title]);
}

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
}

export type Permission = 'read' | 'create' | 'update' | 'delete' | 'transition' | 'manage_configuration' | 'rollback_configuration';
export function usePermission(permission: Permission): boolean {
  const user = useAuthStore((state) => state.user);
  if (user?.is_superuser || user?.tenant_role === 'tenant_admin' || user?.tenant_role === 'administrator') return true;
  if (permission === 'read') return Boolean(user);
  if (user?.tenant_role === 'compliance_officer') return permission !== 'manage_configuration' && permission !== 'rollback_configuration';
  if (user?.tenant_role === 'risk_owner') return ['create', 'update', 'transition'].includes(permission);
  if (user?.tenant_role === 'tester') return permission === 'transition';
  return false;
}

export function Page({ children }: { children: ReactNode }) { return <main className="space-y-6 p-4 sm:p-6 lg:p-8">{children}</main>; }
export function PageHeader({ title, description, back, actions }: { title: string; description: string; back?: () => void; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div>{back && <Button type="button" variant="ghost" className="-ml-3 mb-2" onClick={back}><ArrowLeft className="mr-2 h-4 w-4"/>Back</Button>}<h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</header>;
}

export function PageSkeleton({ rows = 6, label = 'Loading compliance risk information' }: { rows?: number; label?: string }) {
  return <Page><div aria-busy="true" aria-label={label} className="space-y-6"><div className="space-y-2"><Skeleton className="h-8 w-64"/><Skeleton className="h-4 w-full max-w-2xl"/></div><Skeleton className="h-16 w-full"/><div className="space-y-2">{Array.from({ length: rows }, (_, index) => <Skeleton className="h-14 w-full" key={index}/>)}</div></div></Page>;
}

export function GovernedProblem({ error, retry }: { error: unknown; retry?: () => void }) {
  const moduleError = error instanceof ComplianceRiskApiError ? error : undefined;
  const forbidden = moduleError?.status === 403; const missing = moduleError?.status === 404;
  const Icon = forbidden ? LockKeyhole : missing ? FileQuestion : AlertTriangle;
  const title = forbidden ? 'Access denied' : missing ? 'Record not found' : 'Unable to load this view';
  const message = forbidden ? 'Your current policy does not grant this action.' : missing ? 'This record is unavailable or belongs to another tenant.' : moduleError?.message ?? 'The request failed safely. Try again or contact your administrator.';
  return <Card role="alert" className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><Icon className="h-9 w-9 text-destructive"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-xl text-sm text-muted-foreground">{message}</p>{moduleError?.correlationId && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {moduleError.correlationId}</p>}{retry && !forbidden && !missing && <Button className="mt-5" variant="secondary" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button>}</Card>;
}

export function EmptyState({ title, message, action }: { title: string; message: string; action?: { label: string; onClick: () => void } }) {
  return <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center"><FileQuestion className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>{action && <Button className="mt-5" onClick={action.onClick}>{action.label}</Button>}</Card>;
}

export function StatusBadge({ value }: { value: string }) {
  const negative = ['critical', 'failed', 'non_compliant', 'overdue', 'cancelled'].includes(value);
  const positive = ['low', 'negligible', 'passed', 'compliant', 'completed', 'active'].includes(value);
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${negative ? 'border-destructive/40 bg-destructive/10 text-destructive' : positive ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-muted text-muted-foreground'}`}><span aria-hidden="true">{negative ? '▲' : positive ? '●' : '◆'}</span>{titleCase(value)}</span>;
}

export function titleCase(value: string): string { return value.replaceAll('_', ' ').replace(/\b\w/gu, (letter) => letter.toUpperCase()); }
export function formatDate(value: string | null | undefined): string { if (!value) return '—'; const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`); return Number.isNaN(parsed.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(parsed); }

export function Pagination({ meta, onPage }: { meta: ApiPageMeta; onPage: (page: number) => void }) {
  return <nav className="flex items-center justify-between border-t p-4" aria-label="Pagination"><p className="text-sm text-muted-foreground">Page {meta.page} of {Math.max(meta.total_pages, 1)} · {meta.count} records</p><div className="flex gap-2"><Button variant="secondary" disabled={!meta.has_previous} onClick={() => onPage(meta.page - 1)}>Previous</Button><Button variant="secondary" disabled={!meta.has_next} onClick={() => onPage(meta.page + 1)}>Next</Button></div></nav>;
}

export function fieldErrors(error: unknown): Map<string, string> {
  if (!(error instanceof ComplianceRiskApiError) || !error.detail || typeof error.detail !== 'object' || Array.isArray(error.detail)) return new Map();
  const fields = 'fields' in error.detail ? (error.detail.fields as readonly GovernedFieldError[] | undefined) : undefined;
  return new Map((fields ?? []).map((item) => [item.field, item.message]));
}

export function DetailGrid({ items }: { items: readonly { label: string; value: ReactNode }[] }) {
  return <dl className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-3">{items.map((item) => <div className="bg-card p-4" key={item.label}><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{item.label}</dt><dd className="mt-1 break-words text-sm">{item.value}</dd></div>)}</dl>;
}

export function Timeline({ items }: { items: readonly { command: string; from: string; to: string; occurred_at: string; correlation_id: string; rationale?: string }[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No lifecycle transitions have been recorded.</p>;
  return <ol className="space-y-3" aria-label="Audit timeline">{[...items].reverse().map((item) => <li key={`${item.correlation_id}-${item.occurred_at}`} className="border-l-2 border-primary pl-4"><p className="font-medium">{titleCase(item.command)} · {titleCase(item.from)} → {titleCase(item.to)}</p><p className="text-sm text-muted-foreground">{new Date(item.occurred_at).toLocaleString()} · <span className="font-mono text-xs">{item.correlation_id}</span></p>{item.rationale && <p className="mt-1 text-sm">{item.rationale}</p>}</li>)}</ol>;
}
