/* eslint-disable react-refresh/only-export-components, complexity, @typescript-eslint/prefer-nullish-coalescing -- shared BI state/error helpers intentionally handle complete API state variants */
import { useEffect } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, LockKeyhole } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui";
import type { LifecycleState, PaginatedMeta } from "../contracts";

export const BI_PATH = "/business-intelligence";
export const useTenantIdentity = () =>
  useAuthStore((state) => state.user?.tenant_id ?? state.user?.id ?? "anonymous");
export const useDocumentTitle = (title: string) =>
  useEffect(() => {
    document.title = `${title} | SARAISE`;
  }, [title]);
export const formatDate = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value)
      )
    : "—";

export function PageShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{title}</h1>
          {description && (
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </header>
      {children}
    </main>
  );
}

export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-8" aria-label="Loading">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export function RequestError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : undefined;
  const title =
    apiError?.status === 403
      ? "Permission denied"
      : apiError?.status === 404
        ? "Not found"
        : apiError && apiError.status < 500
          ? "Request could not be completed"
          : "Service temporarily unavailable";
  return (
    <div className="space-y-3">
      <ErrorState
        title={title}
        message={apiError?.message ?? "An unexpected error occurred. Please try again."}
        onRetry={onRetry}
      />
      {apiError?.correlationId && (
        <details className="mx-auto max-w-md rounded-md border border-border p-3 text-sm">
          <summary className="cursor-pointer font-medium">Technical details</summary>
          <p className="mt-2 text-muted-foreground">
            Correlation ID: <code>{apiError.correlationId}</code>
          </p>
        </details>
      )}
    </div>
  );
}

export function MutationError({ error }: { error: unknown }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : undefined;
  const details =
    apiError?.details && typeof apiError.details === "object" && !Array.isArray(apiError.details)
      ? (apiError.details as Record<string, unknown>)
      : undefined;
  const nested =
    details?.error && typeof details.error === "object" && !Array.isArray(details.error)
      ? (details.error as Record<string, unknown>)
      : undefined;
  const fieldErrors =
    nested?.field_errors &&
    typeof nested.field_errors === "object" &&
    !Array.isArray(nested.field_errors)
      ? (nested.field_errors as Record<string, unknown>)
      : undefined;
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <p className="font-medium">{apiError?.message ?? "The change could not be saved."}</p>
      {fieldErrors && (
        <ul className="mt-2 list-disc pl-5">
          {Object.entries(fieldErrors).map(([field, messages]) => (
            <li key={field}>
              <span className="font-medium">{field}:</span>{" "}
              {Array.isArray(messages)
                ? messages.filter((message) => typeof message === "string").join(", ")
                : "Invalid value"}
            </li>
          ))}
        </ul>
      )}
      {(apiError?.correlationId || apiError?.code) && (
        <details className="mt-2">
          <summary className="cursor-pointer">Error details</summary>
          {apiError.code && <span className="mr-3">Code: {apiError.code}</span>}
          {apiError.correlationId && <span>Correlation ID: {apiError.correlationId}</span>}
        </details>
      )}
    </div>
  );
}

export function LifecycleBadge({ state }: { state: LifecycleState }) {
  const style =
    state === "published"
      ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300"
      : state === "archived"
        ? "border-border bg-muted text-muted-foreground"
        : "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${style}`}>
      {state}
    </span>
  );
}

export function Pagination({
  meta,
  onPage,
}: {
  meta: PaginatedMeta;
  onPage: (page: number) => void;
}) {
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-3 border-t border-border px-4 py-3"
    >
      <span className="text-sm text-muted-foreground">
        Page {meta.page} of {Math.max(meta.total_pages, 1)} · {meta.count} items
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!meta.has_previous}
          onClick={() => onPage(meta.page - 1)}
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!meta.has_next}
          onClick={() => onPage(meta.page + 1)}
        >
          Next
          <ChevronRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

export function LockedNotice({ entitlement }: { entitlement?: string }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-5">
        <LockKeyhole className="mt-0.5 h-5 w-5 text-muted-foreground" />
        <div>
          <p className="font-semibold">Additional entitlement required</p>
          <p className="text-sm text-muted-foreground">
            Ask an administrator for <code>{entitlement ?? "the required entitlement"}</code>.
            Dataset schema and data remain protected until access is granted.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function UnsavedWarning({ when }: { when: boolean }) {
  useEffect(() => {
    const listener = (event: BeforeUnloadEvent) => {
      if (when) event.preventDefault();
    };
    window.addEventListener("beforeunload", listener);
    return () => window.removeEventListener("beforeunload", listener);
  }, [when]);
  return when ? (
    <p className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">
      <AlertTriangle className="h-3.5 w-3.5" />
      Unsaved draft is stored on this device. Leaving may discard recent changes.
    </p>
  ) : null;
}
