/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react';
import { AlertTriangle, ArrowLeft, Boxes, LockKeyhole, RefreshCw, SearchX } from 'lucide-react';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { AssetManagementApiError } from '../services/asset-service';

export function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

export function formatAmount(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function PageHeader({
  title,
  description,
  backLabel,
  onBack,
  actions,
}: {
  title: string;
  description?: string;
  backLabel?: string;
  onBack?: () => void;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        {onBack && (
          <Button variant="ghost" className="-ml-3 mb-2" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
            {backLabel ?? 'Back'}
          </Button>
        )}
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function PageSkeleton({ table = false }: { table?: boolean }) {
  return (
    <main
      className="space-y-6 p-4 sm:p-8"
      aria-label="Loading asset management information"
      aria-busy="true"
    >
      <div className="space-y-3">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-4 w-full max-w-xl" />
      </div>
      <div className={table ? 'space-y-2' : 'grid gap-4 sm:grid-cols-2 lg:grid-cols-4'}>
        {Array.from({ length: table ? 7 : 4 }, (_, index) => (
          <Skeleton key={index} className={table ? 'h-12 w-full' : 'h-28 w-full'} />
        ))}
      </div>
    </main>
  );
}

function describeError(error: unknown): {
  message: string;
  status?: number;
  correlationId?: string | null;
} {
  if (error instanceof AssetManagementApiError) {
    return { message: error.message, status: error.status, correlationId: error.correlationId };
  }
  if (error instanceof ApiError) {
    return { message: error.message, status: error.status, correlationId: error.correlationId };
  }
  return { message: error instanceof Error ? error.message : 'The request failed safely.' };
}

export function ProblemState({ error, onRetry, compact = false }: {
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const problem = describeError(error);
  const forbidden = problem.status === 403;
  const missing = problem.status === 404;
  const Icon = forbidden ? LockKeyhole : missing ? SearchX : AlertTriangle;
  const title = forbidden ? 'Access denied' : missing ? 'Asset not found' : 'We could not complete this request';
  const message = forbidden
    ? 'Your current policy does not allow this action.'
    : missing
      ? 'The record is unavailable or belongs to another tenant.'
      : problem.message;

  return (
    <Card role="alert" className={`flex flex-col items-center justify-center p-6 text-center ${compact ? '' : 'min-h-72'}`}>
      <div className="rounded-full bg-destructive/10 p-3">
        <Icon className="h-7 w-7 text-destructive" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>
      {problem.correlationId && (
        <p className="mt-3 font-mono text-xs text-muted-foreground">
          Correlation ID: {problem.correlationId}
        </p>
      )}
      {onRetry && !forbidden && !missing && (
        <Button variant="secondary" className="mt-5" onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
          Retry
        </Button>
      )}
    </Card>
  );
}

export function EmptyPanel({ title, description, action }: {
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
      <Boxes className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <Button className="mt-5" onClick={action.onClick}>{action.label}</Button>}
    </Card>
  );
}

export function StatusPill({ active }: { active: boolean }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${
      active
        ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
        : 'border-border bg-muted text-muted-foreground'
    }`}>
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}
