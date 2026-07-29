/* eslint-disable react-refresh/only-export-components -- module UI primitives are intentionally colocated. */
import type { ReactNode } from "react";
import { AlertTriangle, Inbox, LockKeyhole, RefreshCw, SearchX, ServerOff } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { CommunicationHubApiError } from "../services/communication-hub-service";

export function PageShell({
  title,
  description,
  children,
}: {
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>
      </header>
      {children}
    </main>
  );
}

export function PageSkeleton({ label }: { readonly label: string }) {
  return (
    <main aria-busy="true" aria-label={label} className="mx-auto max-w-7xl space-y-6 p-4 sm:p-8">
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-5 w-full max-w-xl" />
      <div className="space-y-2">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    </main>
  );
}

function describeError(error: unknown): {
  readonly message: string;
  readonly status?: number;
  readonly correlationId?: string | null;
} {
  if (error instanceof CommunicationHubApiError) {
    return { message: error.message, status: error.status, correlationId: error.correlationId };
  }
  if (error instanceof ApiError) {
    return { message: error.message, status: error.status, correlationId: error.correlationId };
  }
  return {
    message: error instanceof Error ? error.message : "The governed request failed safely.",
  };
}

export function ProblemState({
  error,
  onRetry,
}: {
  readonly error: unknown;
  readonly onRetry?: () => void;
}) {
  const problem = describeError(error);
  const denied = problem.status === 401 || problem.status === 403;
  const missing = problem.status === 404;
  const Icon = denied ? LockKeyhole : missing ? SearchX : AlertTriangle;
  return (
    <Card
      role="alert"
      className="flex min-h-64 flex-col items-center justify-center p-8 text-center"
    >
      <Icon className="h-10 w-10 text-destructive" aria-hidden="true" />
      <h2 className="mt-4 text-lg font-semibold">
        {denied
          ? "Access denied"
          : missing
            ? "Record not found"
            : "Communication Hub request failed"}
      </h2>
      <p className="mt-2 max-w-lg text-sm text-muted-foreground">
        {denied
          ? "Your current policy does not grant access to this Communication Hub area."
          : problem.message}
      </p>
      {problem.correlationId ? (
        <p className="mt-3 font-mono text-xs text-muted-foreground">
          Correlation ID: {problem.correlationId}
        </p>
      ) : null}
      {onRetry && !denied ? (
        <Button className="mt-5" variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
          Retry
        </Button>
      ) : null}
    </Card>
  );
}

export function EmptyState({
  title,
  description,
}: {
  readonly title: string;
  readonly description: string;
}) {
  return (
    <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
      <Inbox className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
    </Card>
  );
}

export function UnavailableCapabilityPage({
  title,
  description,
  limitation,
}: {
  readonly title: string;
  readonly description: string;
  readonly limitation: string;
}) {
  return (
    <PageShell title={title} description={description}>
      <Card
        role="status"
        className="flex min-h-64 flex-col items-center justify-center p-8 text-center"
      >
        <ServerOff className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
        <h2 className="mt-4 text-lg font-semibold">Capability unavailable</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{limitation}</p>
      </Card>
    </PageShell>
  );
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
