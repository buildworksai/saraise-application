import type { ReactNode } from "react";
import { AlertTriangle, LockKeyhole, Workflow } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export function PageHeader({
  eyebrow = "Automation orchestration",
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

export function PageSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-label="Loading orchestration data" aria-busy="true" className="space-y-4">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-20 w-full" />
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  );
}

export function PermissionDenied() {
  return (
    <Card role="alert" className="border-amber-500/40">
      <CardContent className="flex min-h-72 flex-col items-center justify-center text-center">
        <LockKeyhole className="mb-4 h-10 w-10 text-amber-600" aria-hidden="true" />
        <h2 className="text-xl font-semibold">Permission required</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Your role cannot access this orchestration surface. Ask a tenant administrator for the
          corresponding orchestration permission.
        </p>
      </CardContent>
    </Card>
  );
}

export function LoadError({ error, retry }: { error: Error; retry: () => void }) {
  if (error instanceof ApiError && error.status === 403) return <PermissionDenied />;
  return (
    <Card role="alert" className="border-destructive/40">
      <CardContent className="flex min-h-72 flex-col items-center justify-center text-center">
        <AlertTriangle className="mb-4 h-10 w-10 text-destructive" aria-hidden="true" />
        <h2 className="text-xl font-semibold">Orchestration data is unavailable</h2>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">{error.message}</p>
        <Button className="mt-5" variant="outline" onClick={retry}>Try again</Button>
      </CardContent>
    </Card>
  );
}

export function EmptyPanel({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex min-h-72 flex-col items-center justify-center text-center">
        <span className="mb-4 rounded-2xl bg-primary/10 p-3 text-primary"><Workflow aria-hidden="true" /></span>
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </CardContent>
    </Card>
  );
}

const STATUS_COLORS: Readonly<Record<string, string>> = {
  draft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  published: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  active: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  queued: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
  retry_wait: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  paused: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  cancelling: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
  succeeded: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  cancelled: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200",
  retired: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200",
};

export function StatusPill({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-muted text-muted-foreground";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>{status.replace("_", " ")}</span>;
}

// Formatting helpers are colocated so every orchestration state uses identical evidence labels.
// eslint-disable-next-line react-refresh/only-export-components
export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

// eslint-disable-next-line react-refresh/only-export-components
export function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const milliseconds = Math.max(0, new Date(end ?? Date.now()).getTime() - new Date(start).getTime());
  if (milliseconds < 60_000) return `${Math.round(milliseconds / 1_000)}s`;
  return `${Math.floor(milliseconds / 60_000)}m ${Math.round((milliseconds % 60_000) / 1_000)}s`;
}

export function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  return (
    <nav aria-label="Pagination" className="flex items-center justify-end gap-3 pt-4">
      <span className="text-sm text-muted-foreground">Page {page} of {Math.max(1, totalPages)}</span>
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
    </nav>
  );
}
