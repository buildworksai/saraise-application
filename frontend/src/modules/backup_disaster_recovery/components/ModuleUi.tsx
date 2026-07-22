/* eslint-disable react-refresh/only-export-components -- module UI primitives intentionally share presentation helpers. */
import { useEffect, useState, type FormEventHandler, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { AlertTriangle, Ban, ChevronRight, CloudOff, FileQuestion, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type { BDRPresentationConfiguration } from '../contracts';
import { BackupDisasterRecoveryError } from '../services/backup_disaster_recovery-service';

export const MODULE_PATHS = {
  overview: '/backup-disaster-recovery',
  backupNew: '/backup-disaster-recovery/backups/new',
  recoveryPoints: '/backup-disaster-recovery/recovery-points',
  restores: '/backup-disaster-recovery/restores',
  restoreNew: '/backup-disaster-recovery/restores/new',
  runbooks: '/backup-disaster-recovery/runbooks',
  runbookNew: '/backup-disaster-recovery/runbooks/new',
  exercises: '/backup-disaster-recovery/exercises',
  exerciseNew: '/backup-disaster-recovery/exercises/new',
  objectives: '/backup-disaster-recovery/reports/objectives',
  configuration: '/backup-disaster-recovery/configuration',
} as const;

export const formatDateTime = (value: string | null): string =>
  value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not yet';

export const formatDuration = (seconds: number | null, presentation: BDRPresentationConfiguration): string => {
  if (seconds === null) return 'Not measured';
  if (seconds < presentation.duration_minute_seconds) return `${seconds}s`;
  if (seconds < presentation.duration_hour_seconds) return `${Math.round(seconds / presentation.duration_minute_seconds)}m`;
  return `${(seconds / presentation.duration_hour_seconds).toFixed(1)}h`;
};

export const formatBytes = (bytes: number | null, presentation: BDRPresentationConfiguration): string => {
  if (bytes === null) return 'Unknown';
  const base = presentation.byte_base;
  if (bytes < base) return `${bytes} B`;
  if (bytes < base ** 2) return `${(bytes / base).toFixed(1)} KiB`;
  if (bytes < base ** 3) return `${(bytes / base ** 2).toFixed(1)} MiB`;
  return `${(bytes / base ** 3).toFixed(1)} GiB`;
};

export const createIdempotencyKey = (operation: string): string =>
  `${operation}-${crypto.randomUUID()}`;

export const PageShell = ({ children }: { children: ReactNode }) => (
  <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">{children}</main>
);

interface PageHeaderProps {
  title: string;
  description: string;
  actions?: ReactNode;
  parentLabel?: string;
  parentPath?: string;
}

export const PageHeader = ({ title, description, actions, parentLabel, parentPath }: PageHeaderProps) => {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = `${title} | SARAISE`;
  }, [title]);
  return (
    <header className="space-y-4">
      {parentLabel && parentPath ? (
        <button
          type="button"
          className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => navigate(parentPath)}
        >
          {parentLabel}<ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
      ) : null}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{title}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground sm:text-base">{description}</p>
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </header>
  );
};

export const PageSkeleton = ({ cards = 3 }: { cards?: number }) => (
  <PageShell>
    <div aria-busy="true" aria-label="Loading disaster recovery data" className="space-y-6">
      <div className="space-y-3"><Skeleton className="h-9 w-72" /><Skeleton className="h-5 w-full max-w-xl" /></div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: cards }).map((_, index) => <Skeleton key={index} className="h-40" />)}
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  </PageShell>
);

export const BackgroundProgress = ({ active, label = 'Refreshing data' }: { active: boolean; label?: string }) => (
  <div aria-live="polite" aria-atomic="true" className="h-1">
    {active ? <div role="status" className="h-1 animate-pulse rounded-full bg-primary"><span className="sr-only">{label}</span></div> : null}
  </div>
);

export const ModuleErrorState = ({ error, onRetry }: { error: Error; onRetry: () => void }) => {
  const moduleError = error instanceof BackupDisasterRecoveryError ? error : null;
  const status = moduleError?.status;
  const correlation = moduleError?.correlationId;
  const icon = status === 403 ? Ban : status === 404 ? FileQuestion : status === 503 ? CloudOff : AlertTriangle;
  const Icon = icon;
  const title = status === 403 ? 'Permission required' : status === 404 ? 'Resource not found' : status === 503 ? 'Service temporarily unavailable' : 'Unable to load disaster recovery data';
  return (
    <PageShell>
      <section role="alert" className="mx-auto flex min-h-[28rem] max-w-2xl flex-col items-center justify-center rounded-xl border bg-card p-8 text-center">
        <span className="mb-4 rounded-full bg-destructive/10 p-4"><Icon aria-hidden="true" className="h-10 w-10 text-destructive" /></span>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="mt-2 text-muted-foreground">{moduleError?.message ?? error.message}</p>
        {correlation ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {correlation}</p> : null}
        {status !== 403 && status !== 404 ? (
          <Button className="mt-6" onClick={onRetry}><RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />Retry</Button>
        ) : null}
      </section>
    </PageShell>
  );
};

export const DomainEmptyState = ({ icon: Icon, title, description, actionLabel, onAction }: {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) => (
  <section className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed bg-card p-8 text-center">
    <span className="mb-4 rounded-full bg-muted p-4"><Icon aria-hidden="true" className="h-9 w-9 text-muted-foreground" /></span>
    <h2 className="text-lg font-semibold">{title}</h2>
    <p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>
    {actionLabel && onAction ? <Button className="mt-5" onClick={onAction}>{actionLabel}</Button> : null}
  </section>
);

const semanticStatusClasses: Readonly<Record<string, string>> = {
  'status-success': 'bg-primary/10 text-primary',
  'status-danger': 'bg-destructive/10 text-destructive',
  'status-warning': 'bg-muted text-muted-foreground',
};

export const StatusPill = ({ status, presentation }: { status: string; presentation: BDRPresentationConfiguration }) => {
  const positive = presentation.status_positive.includes(status);
  const negative = presentation.status_negative.includes(status);
  const warning = presentation.status_warning.includes(status);
  const token = positive
    ? presentation.status_positive_token
    : negative
      ? presentation.status_negative_token
      : warning
        ? presentation.status_warning_token
        : 'status-warning';
  const style = semanticStatusClasses[token];
  if (!style) throw new Error(`Unsupported semantic status token: ${token}`);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${style}`}>{status.replaceAll('_', ' ')}</span>;
};

export const MetricCard = ({ label, value, hint, state }: { label: string; value: string; hint: string; state?: 'good' | 'warning' | 'bad' }) => (
  <Card className={state === 'bad' ? 'border-destructive/50' : state === 'warning' ? 'border-primary/50' : undefined}>
    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle></CardHeader>
    <CardContent><p className="text-3xl font-bold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{hint}</p></CardContent>
  </Card>
);

export const FormField = ({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactNode }) => (
  <div className="space-y-2">
    <label htmlFor={id} className="text-sm font-medium">{label}</label>
    {children}
    {hint ? <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p> : null}
    {error ? <p id={`${id}-error`} role="alert" className="text-sm text-destructive">{error}</p> : null}
  </div>
);

export const FormCard = ({ title, description, onSubmit, children, footer }: { title: string; description: string; onSubmit: FormEventHandler<HTMLFormElement>; children: ReactNode; footer: ReactNode }) => (
  <Card className="max-w-4xl">
    <CardHeader><CardTitle>{title}</CardTitle><p className="text-sm text-muted-foreground">{description}</p></CardHeader>
    <CardContent><form noValidate onSubmit={onSubmit} className="space-y-5"><div className="grid gap-5 md:grid-cols-2">{children}</div><div className="flex flex-wrap justify-end gap-3 border-t pt-5">{footer}</div></form></CardContent>
  </Card>
);

export const inputClass = 'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50';
export const textareaClass = `${inputClass} min-h-28 resize-y`;

export const ResponsiveTable = ({ label, headers, children }: { label: string; headers: readonly string[]; children: ReactNode }) => (
  <div className="overflow-x-auto rounded-xl border bg-card">
    <table className="w-full min-w-[48rem] text-left text-sm">
      <caption className="sr-only">{label}</caption>
      <thead className="border-b bg-muted/60"><tr>{headers.map((header) => <th key={header} scope="col" className="px-4 py-3 font-medium text-muted-foreground">{header}</th>)}</tr></thead>
      <tbody className="divide-y">{children}</tbody>
    </table>
  </div>
);

export const MutationError = ({ error }: { error: Error | null }) => {
  if (!error) return null;
  const moduleError = error instanceof BackupDisasterRecoveryError ? error : null;
  return (
    <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
      <p>{error.message}</p>
      {moduleError?.correlationId ? <p className="mt-1 font-mono text-xs">Correlation ID: {moduleError.correlationId}</p> : null}
    </div>
  );
};

export const ResourceLookup = ({ title, description, label, destination }: {
  title: string;
  description: string;
  label: string;
  destination: (id: string) => string;
}) => {
  const navigate = useNavigate();
  const [id, setId] = useState('');
  return <PageShell><PageHeader title={title} description={description} /><Card className="max-w-2xl"><CardContent className="space-y-4 pt-6"><FormField id="resource-id" label={label} hint="Tenant isolation and RBAC are enforced again when the record is opened."><input id="resource-id" className={inputClass} value={id} onChange={(event) => setId(event.target.value)} /></FormField><div className="flex justify-end"><Button disabled={!id.trim()} onClick={() => navigate(destination(id.trim()))}>Open</Button></div></CardContent></Card></PageShell>;
};

export const fieldError = (error: Error | null, field: string): string | undefined => {
  if (!(error instanceof BackupDisasterRecoveryError)) return undefined;
  return error.fieldErrors.find((item) => item.field === field)?.message;
};
