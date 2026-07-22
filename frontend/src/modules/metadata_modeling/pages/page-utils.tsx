/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from "react";
import { ShieldX } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between"><div>{eyebrow && <p className="text-sm font-medium text-primary">{eyebrow}</p>}<h1 className="text-3xl font-bold tracking-tight text-foreground">{title}</h1><p className="mt-2 max-w-3xl text-muted-foreground">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</header>;
}
export function PageSkeleton({ rows = 5 }: { rows?: number }) { return <div aria-label="Loading" role="status" className="space-y-5"><Skeleton className="h-10 w-2/5" /><Skeleton className="h-5 w-3/5" /><div className="rounded-lg border border-border p-4 space-y-3">{Array.from({ length: rows }, (_value, index) => <Skeleton key={index} className="h-12 w-full" />)}</div><span className="sr-only">Loading</span></div>; }
export function GovernedErrorState({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  if (apiError?.status === 403) return <div className="flex min-h-[400px] flex-col items-center justify-center text-center"><ShieldX className="h-12 w-12 text-muted-foreground" /><h2 className="mt-4 text-xl font-semibold">Access required</h2><p className="mt-2 max-w-md text-muted-foreground">Your role does not grant access to this metadata capability. Ask a tenant administrator for the required permission.</p>{apiError.correlationId && <p className="mt-4 text-xs text-muted-foreground">Correlation ID: {apiError.correlationId}</p>}</div>;
  if (apiError?.status === 404) return <ErrorState title="Not found" message="This item does not exist in your tenant or is no longer available." />;
  if (apiError?.status === 401) return <ErrorState title="Session expired" message="Sign in again to continue." />;
  const correlation = apiError?.correlationId ? ` Correlation ID: ${apiError.correlationId}` : "";
  return <ErrorState message={`${error.message}${correlation}`} onRetry={onRetry} />;
}
export function formatDate(value: string | null): string { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
export function idempotencyKey(): string { return crypto.randomUUID(); }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
export function fieldErrorsFrom(error: Error): Readonly<Record<string, string>> {
  if (!(error instanceof ApiError) || !isRecord(error.details)) return {};
  const source = isRecord(error.details.error) && isRecord(error.details.error.fields) ? error.details.error.fields : isRecord(error.details.fields) ? error.details.fields : null;
  if (!source) return {};
  const result: Record<string, string> = {};
  for (const [field, value] of Object.entries(source)) {
    if (typeof value === "string") result[field] = value;
    else if (Array.isArray(value) && value.length > 0) { const items: readonly unknown[] = value; const first = items[0]; if (typeof first === "string") result[field] = first; else if (isRecord(first) && typeof first.message === "string") result[field] = first.message; }
  }
  return result;
}
