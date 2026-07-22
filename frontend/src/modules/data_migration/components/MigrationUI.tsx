import { AlertTriangle, CheckCircle2, DatabaseZap, Loader2, ShieldX } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import type { JobStatus, RollbackStatus, RunStatus } from '../contracts';

export function PageTitle({ title }: { title: string }): null {
  useEffect(() => { document.title = `${title} · SARAISE`; }, [title]);
  return null;
}

export function PageShell({ title, description, actions, children }: { title: string; description: string; actions?: ReactNode; children: ReactNode }) {
  return <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <PageTitle title={title} />
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div><h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
    {children}
  </main>;
}

export function PageSkeleton({ label = 'Loading migration data' }: { label?: string }) {
  return <div className="space-y-4 p-6" role="status" aria-label={label}><span className="sr-only">{label}</span><Skeleton className="h-10 w-2/5" /><Skeleton className="h-5 w-3/5" /><Skeleton className="h-40 w-full" /><Skeleton className="h-40 w-full" /></div>;
}

export function FailureState({ title = 'Unable to load data', message, forbidden = false, onRetry }: { title?: string; message: string; forbidden?: boolean; onRetry?: () => void }) {
  const Icon = forbidden ? ShieldX : AlertTriangle;
  return <Card className="mx-auto max-w-2xl p-8 text-center" role="alert"><Icon className="mx-auto h-10 w-10 text-destructive" aria-hidden="true" /><h2 className="mt-4 text-lg font-semibold text-foreground">{forbidden ? 'Access denied' : title}</h2><p className="mt-2 text-sm text-muted-foreground">{message}</p>{onRetry && !forbidden ? <Button className="mt-5" variant="outline" onClick={onRetry}>Try again</Button> : null}</Card>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: { label: string; onClick: () => void } }) {
  return <Card className="p-10 text-center"><DatabaseZap className="mx-auto h-10 w-10 text-muted-foreground" aria-hidden="true" /><h2 className="mt-4 text-lg font-semibold text-foreground">{title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>{action ? <Button className="mt-5" onClick={action.onClick}>{action.label}</Button> : null}</Card>;
}

const stateStyles: Record<JobStatus | RunStatus | RollbackStatus, string> = {
  draft: 'bg-muted text-muted-foreground', ready: 'bg-primary/10 text-primary', archived: 'bg-muted text-muted-foreground',
  queued: 'bg-muted text-muted-foreground', running: 'bg-primary/10 text-primary', succeeded: 'bg-primary/10 text-primary', partial: 'bg-destructive/10 text-destructive', failed: 'bg-destructive/10 text-destructive', cancelled: 'bg-muted text-muted-foreground', rolled_back: 'bg-muted text-muted-foreground',
};

export function StateBadge({ state }: { state: JobStatus | RunStatus | RollbackStatus }) {
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${stateStyles[state]}`}>{state.replace('_', ' ')}</span>;
}

export function InlinePending({ label }: { label: string }) { return <span className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />{label}</span>; }
export function SuccessBanner({ children }: { children: ReactNode }) { return <div className="flex gap-3 rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm text-foreground" role="status"><CheckCircle2 className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />{children}</div>; }

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const bounded = Math.max(0, Math.min(100, value));
  return <div><div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>{label}</span><span>{Math.round(bounded)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={bounded}><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${bounded}%` }} /></div></div>;
}
