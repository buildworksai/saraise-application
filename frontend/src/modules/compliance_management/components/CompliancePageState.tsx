/* eslint-disable react-refresh/only-export-components -- the title hook and page-state components form one presentation contract. */
import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, FileQuestion, Gauge, LockKeyhole, RefreshCw, ServerOff } from 'lucide-react';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';

export function useComplianceTitle(title: string): void {
  useEffect(() => { document.title = `${title} | SARAISE Compliance`; }, [title]);
}

export function CompliancePage({ title, description, actions, children }: { readonly title: string; readonly description: string; readonly actions?: ReactNode; readonly children: ReactNode }) {
  useComplianceTitle(title);
  return <main className="space-y-6 p-4 sm:p-6 lg:p-8"><header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>{children}</main>;
}

export function ComplianceSkeleton({ label = 'Loading compliance workspace', rows = 5 }: { readonly label?: string; readonly rows?: number }) {
  return <main aria-busy="true" aria-label={label} className="space-y-5 p-4 sm:p-6 lg:p-8"><Skeleton className="h-20 w-full"/><Skeleton className="h-12 w-full"/>{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-16 w-full"/>)}</main>;
}

function presentation(error: Error) {
  if (error instanceof ApiError && error.status === 403) return { title: 'Access denied', message: 'Your current compliance permissions do not allow this action.', icon: LockKeyhole };
  if (error instanceof ApiError && error.status === 404) return { title: 'Record not found', message: 'The record does not exist or belongs to another tenant.', icon: FileQuestion };
  if (error instanceof ApiError && error.status === 429) return { title: 'Quota exhausted', message: 'This tenant has reached its configured compliance quota. Ask an administrator to review capacity.', icon: Gauge };
  if (error instanceof ApiError && error.status === 503) return { title: 'Capability unavailable', message: 'The compliance service is not ready. No successful result has been assumed.', icon: ServerOff };
  return { title: 'Compliance request failed', message: error.message || 'The request failed safely.', icon: AlertTriangle };
}

export function ComplianceError({ error, onRetry }: { readonly error: Error; readonly onRetry?: () => void }) {
  const view = presentation(error); const Icon = view.icon;
  return <section role="alert" className="rounded-xl border bg-card p-8 text-center"><Icon aria-hidden className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{view.message}</p>{error instanceof ApiError && error.correlationId ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {error.correlationId}</p> : null}{onRetry ? <Button className="mt-5" variant="outline" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</section>;
}

export function ComplianceEmpty({ title, description, action }: { readonly title: string; readonly description: string; readonly action?: ReactNode }) {
  return <section className="rounded-xl border border-dashed bg-card p-10 text-center"><FileQuestion className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</section>;
}

export function ComplianceSurface({ title, children }: { readonly title?: string; readonly children: ReactNode }) {
  return <section className="rounded-xl border bg-card p-5 shadow-sm">{title ? <h2 className="mb-4 text-lg font-semibold">{title}</h2> : null}{children}</section>;
}
