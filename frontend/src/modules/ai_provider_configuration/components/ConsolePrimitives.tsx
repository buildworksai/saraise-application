import type { ReactNode } from 'react';
import { AlertCircle, Bot, KeyRound, RefreshCw } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { AI_PROVIDER_ROUTES, type DeploymentStatus } from '../contracts';

export function ConsoleHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b bg-gradient-to-br from-primary/10 via-background to-background px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-primary">
            <span className="rounded-lg bg-primary/10 p-2"><Bot className="h-4 w-4" aria-hidden="true" /></span>
            AI foundation
          </div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">{description}</p>
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      <nav className="mx-auto mt-7 flex max-w-7xl gap-1 overflow-x-auto" aria-label="AI provider configuration">
        <NavLink
          end
          to={AI_PROVIDER_ROUTES.HOME}
          className={({ isActive }) => `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:bg-background/60 hover:text-foreground'}`}
        >
          Provider console
        </NavLink>
        <NavLink
          to={AI_PROVIDER_ROUTES.CONFIGURATION}
          className={({ isActive }) => `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:bg-background/60 hover:text-foreground'}`}
        >
          Runtime configuration
        </NavLink>
        <NavLink
          to={AI_PROVIDER_ROUTES.SECRETS}
          className={({ isActive }) => `flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:bg-background/60 hover:text-foreground'}`}
        >
          <KeyRound className="h-4 w-4" aria-hidden="true" /> Secret operations
        </NavLink>
      </nav>
    </header>
  );
}

export function ConsoleSkeleton() {
  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8" aria-label="Loading AI provider configuration" role="status">
      <span className="sr-only">Loading AI provider configuration</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-28 rounded-lg" />)}
      </div>
      <Skeleton className="h-12 rounded-lg" />
      <Skeleton className="h-80 rounded-lg" />
    </div>
  );
}

export function ApiProblem({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const accessDenied = apiError?.status === 401 || apiError?.status === 403;
  const title = accessDenied ? 'Access unavailable' : 'Provider configuration unavailable';
  const message = accessDenied
    ? 'Your account does not have permission to view or change AI provider configuration.'
    : apiError?.message ?? 'The service could not be reached. Check the connection and try again.';
  return (
    <Card className="mx-auto flex min-h-72 max-w-3xl flex-col items-center justify-center p-8 text-center" role="alert">
      <span className="rounded-full bg-destructive/10 p-4"><AlertCircle className="h-8 w-8 text-destructive" aria-hidden="true" /></span>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-xl text-sm text-muted-foreground">{message}</p>
      {apiError?.correlationId && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {apiError.correlationId}</p>}
      <Button className="mt-5" variant="outline" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>
    </Card>
  );
}

export function EmptyPanel({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center">
      <span className="rounded-full bg-muted p-3 text-muted-foreground">{icon}</span>
      <h3 className="mt-3 font-medium">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function DeploymentStatusPill({ status }: { status: DeploymentStatus }) {
  const styles = status === 'active'
    ? 'bg-primary/10 text-primary'
    : status === 'error'
      ? 'bg-destructive/15 text-destructive'
      : 'bg-muted text-muted-foreground';
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${styles}`}>{status}</span>;
}
