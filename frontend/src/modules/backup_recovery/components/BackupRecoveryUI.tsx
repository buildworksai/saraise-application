import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Copy,
  FolderOpen,
  LockKeyhole,
  RefreshCw,
  SearchX,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ActionCapability, PaginationMeta } from "../contracts";
import { BackupRecoveryApiError } from "../services/backup-recovery-service";

export function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

export function formatDate(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value)
      )
    : "—";
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "0 B";
  const unit = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
  return `${(value / 1024 ** unit).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${["B", "KiB", "MiB", "GiB", "TiB"][unit]}`;
}

export function duration(start: string | null, end: string | null): string {
  if (!start) return "Not started";
  const seconds = Math.max(
    0,
    Math.round(((end ? new Date(end) : new Date()).getTime() - new Date(start).getTime()) / 1000)
  );
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60
    ? `${minutes}m ${seconds % 60}s`
    : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
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
          <Button variant="ghost" className="mb-2 -ml-3" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            {backLabel ?? "Back"}
          </Button>
        )}
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {description && (
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function PageSkeleton({ table = false }: { table?: boolean }) {
  return (
    <main
      className="space-y-6 p-4 sm:p-8"
      aria-label="Loading backup recovery information"
      aria-busy="true"
    >
      <span className="sr-only" role="status">
        Loading
      </span>
      <div className="space-y-3">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <div className={table ? "space-y-2" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-4"}>
        {Array.from({ length: table ? 7 : 4 }, (_, index) => (
          <Skeleton key={index} className={table ? "h-12 w-full" : "h-32 w-full"} />
        ))}
      </div>
    </main>
  );
}

export function ProblemState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof BackupRecoveryApiError ? error : null;
  const forbidden = apiError?.status === 403;
  const missing = apiError?.status === 404;
  const Icon = forbidden ? LockKeyhole : missing ? SearchX : AlertTriangle;
  const title = forbidden
    ? "Access denied"
    : missing
      ? "Record not found"
      : "This view is unavailable";
  const message = forbidden
    ? "Your current tenant policy does not grant this capability."
    : missing
      ? "The record is unavailable or belongs to another tenant."
      : apiError?.message ??
        (error instanceof Error ? error.message : "The governed request failed safely.");
  const copy = async () => {
    if (!apiError?.correlationId) return;
    await navigator.clipboard.writeText(apiError.correlationId);
    toast.success("Correlation ID copied");
  };
  return (
    <Card
      role="alert"
      className="flex min-h-72 flex-col items-center justify-center p-8 text-center"
    >
      <div className="rounded-full bg-destructive/10 p-4">
        <Icon className="h-8 w-8 text-destructive" />
      </div>
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>
      {apiError?.correlationId && (
        <Button variant="ghost" size="sm" className="mt-3 font-mono" onClick={() => void copy()}>
          <Copy className="mr-2 h-3.5 w-3.5" />
          Correlation ID: {apiError.correlationId}
        </Button>
      )}
      {onRetry && !forbidden && !missing && (
        <Button className="mt-5" variant="secondary" onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Retry
        </Button>
      )}
    </Card>
  );
}

export function EmptyPanel({
  filtered,
  title,
  description,
  onReset,
  action,
}: {
  filtered?: boolean;
  title: string;
  description: string;
  onReset?: () => void;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <Card className="flex min-h-72 flex-col items-center justify-center p-8 text-center">
      <FolderOpen className="h-10 w-10 text-muted-foreground" />
      <h2 className="mt-4 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      <div className="mt-5 flex gap-2">
        {filtered && onReset && (
          <Button variant="secondary" onClick={onReset}>
            Reset filters
          </Button>
        )}
        {action && <Button onClick={action.onClick}>{action.label}</Button>}
      </div>
    </Card>
  );
}

export function Pagination({
  meta,
  onPage,
}: {
  meta: PaginationMeta;
  onPage: (page: number) => void;
}) {
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between border-t p-4">
      <p className="text-sm text-muted-foreground">
        Page {meta.page} of {Math.max(meta.total_pages, 1)} · {meta.count} records
      </p>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          disabled={!meta.has_previous}
          onClick={() => onPage(meta.page - 1)}
        >
          Previous
        </Button>
        <Button variant="secondary" disabled={!meta.has_next} onClick={() => onPage(meta.page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}

export function StaleIndicator({ fetching }: { fetching: boolean }) {
  return (
    <span role="status" aria-live="polite" className="text-xs text-muted-foreground">
      {fetching ? (
        <>
          <RefreshCw className="mr-1 inline h-3 w-3 animate-spin" />
          Refreshing verified server data…
        </>
      ) : (
        "Up to date"
      )}
    </span>
  );
}

export function StatusPill({ value }: { value: string }) {
  const danger = ["failed", "corrupt", "unavailable"].includes(value);
  const success = ["completed", "passed", "verified", "available", "healthy", "active"].includes(
    value
  );
  const progress = ["pending", "running", "verifying"].includes(value);
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${danger ? "border-destructive/30 bg-destructive/10 text-destructive" : success ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300" : progress ? "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300" : "border-border bg-muted text-muted-foreground"}`}
    >
      {titleCase(value)}
    </span>
  );
}

export function CommandButton({
  capability,
  children,
  pending,
  onClick,
  variant = "secondary",
}: {
  capability?: ActionCapability;
  children: ReactNode;
  pending?: boolean;
  onClick: () => void;
  variant?: "primary" | "secondary" | "danger";
}) {
  const allowed = capability?.allowed ?? false;
  return (
    <span
      title={!allowed ? capability?.reason ?? "The server did not grant this command." : undefined}
    >
      <Button
        variant={variant}
        disabled={!allowed || pending}
        aria-disabled={!allowed || pending}
        onClick={onClick}
      >
        {children}
      </Button>
      {!allowed && <span className="sr-only">{capability?.reason ?? "Command unavailable"}</span>}
    </span>
  );
}

export function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`mt-1 break-words text-sm ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

export function MutationError({ error }: { error: unknown }) {
  return error ? <ProblemState error={error} /> : null;
}
