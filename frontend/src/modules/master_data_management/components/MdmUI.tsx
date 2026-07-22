/* eslint-disable react-refresh/only-export-components -- shared MDM presentation helpers intentionally colocate pure formatters. */
import { useState, type ReactNode } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Database, LockKeyhole, RefreshCw, SearchX, ServerOff } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ApiErrorEnvelope, IssueSeverity, PaginationMeta } from "../contracts";

export const QUERY_KEYS = {
  dashboard: (type?: string) => ["mdm", "dashboard", type] as const,
  entityTypes: (filters: object) => ["mdm", "entity-types", filters] as const,
  entityType: (id: string) => ["mdm", "entity-type", id] as const,
  entities: (filters: object) => ["mdm", "entities", filters] as const,
  entity: (id: string) => ["mdm", "entity", id] as const,
  versions: (id: string, page: number) => ["mdm", "entity", id, "versions", page] as const,
  version: (id: string, version: number) => ["mdm", "entity", id, "version", version] as const,
  qualityRules: (filters: object) => ["mdm", "quality-rules", filters] as const,
  qualityRule: (id: string) => ["mdm", "quality-rule", id] as const,
  qualityIssues: (filters: object) => ["mdm", "quality-issues", filters] as const,
  qualityIssue: (id: string) => ["mdm", "quality-issue", id] as const,
  matchingRules: (filters: object) => ["mdm", "matching-rules", filters] as const,
  matchingRule: (id: string) => ["mdm", "matching-rule", id] as const,
  candidates: (filters: object) => ["mdm", "match-candidates", filters] as const,
  candidate: (id: string) => ["mdm", "match-candidate", id] as const,
  merges: (filters: object) => ["mdm", "merges", filters] as const,
  merge: (id: string) => ["mdm", "merge", id] as const,
  job: (id: string) => ["mdm", "job", id] as const,
};

export function idempotencyKey(scope: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `mdm-ui:${scope}:${random}`;
}

export function PageHeader({ title, description, actions }: { readonly title: string; readonly description: string; readonly actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ cards = 5, label = "Loading master data" }: { readonly cards?: number; readonly label?: string }) {
  return <main aria-busy="true" aria-label={label} className="space-y-6"><Skeleton className="h-20 w-full"/><Skeleton className="h-14 w-full"/><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: cards }, (_, index) => <Skeleton key={index} className="h-32 w-full"/>)}</div></main>;
}

function errorPresentation(error: Error) {
  if (error instanceof ApiError && error.status === 403) return { title: "Access denied", message: "Your current policy does not permit this master-data action.", icon: LockKeyhole };
  if (error instanceof ApiError && error.status === 404) return { title: "Record not found", message: "The record does not exist or is outside your tenant.", icon: SearchX };
  if (error instanceof ApiError && error.status === 503) return { title: "Capability unavailable", message: "The authoritative master-data service is not ready. No success has been assumed.", icon: ServerOff };
  if (error instanceof ApiError && error.status === 409) return { title: "Concurrent change detected", message: "Reload the latest version and review the conflict before trying again.", icon: RefreshCw };
  return { title: "Master-data request failed", message: error.message || "The request failed safely.", icon: AlertTriangle };
}

export function GovernedError({ error, retry }: { readonly error: Error; readonly retry?: () => void }) {
  const view = errorPresentation(error); const Icon = view.icon;
  const correlation = error instanceof ApiError ? error.correlationId : undefined;
  return <section role="alert" className="rounded-xl border bg-card p-8 text-center"><Icon aria-hidden className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{view.message}</p>{correlation ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {correlation}</p> : null}{retry ? <Button className="mt-5" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</section>;
}

export function EmptyState({ title, description, action }: { readonly title: string; readonly description: string; readonly action?: ReactNode }) {
  return <section className="rounded-xl border border-dashed bg-card p-10 text-center"><Database className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</section>;
}

export function Pagination({ value, onPage }: { readonly value: PaginationMeta; readonly onPage: (page: number) => void }) {
  return <nav aria-label="Pagination" className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between"><p>Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><Button variant="outline" size="sm" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></div></nav>;
}

export function Surface({ title, children, className = "" }: { readonly title?: string; readonly children: ReactNode; readonly className?: string }) {
  return <section className={`rounded-xl border bg-card p-5 shadow-sm ${className}`}>{title ? <h2 className="mb-4 text-lg font-semibold">{title}</h2> : null}{children}</section>;
}

export function DetailGrid({ children }: { readonly children: ReactNode }) { return <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>; }
export function Detail({ label, children }: { readonly label: string; readonly children: ReactNode }) { return <div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
export function formatDate(value: string | null | undefined): string { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
export function formatScore(value: string | number | null | undefined): string { return value === null || value === undefined ? "Not evaluated" : `${Number(value).toFixed(1)}%`; }
export function successMessage(state: unknown): string | undefined { if (!state || typeof state !== "object" || !("success" in state)) return undefined; const value = state.success; return typeof value === "string" ? value : undefined; }

export function StatusPill({ value }: { readonly value: string }) {
  const positive = ["active", "resolved", "confirmed", "applied", "succeeded", "ready"].includes(value);
  const danger = ["critical", "failed", "timed_out", "rejected"].includes(value);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${danger ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200" : positive ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"}`}>{value.replaceAll("_", " ")}</span>;
}

export function SeverityPill({ value }: { readonly value: IssueSeverity }) { return <StatusPill value={value}/>; }

export function ConfirmAction({ label, title, description, pending, danger = false, onConfirm }: { readonly label: string; readonly title: string; readonly description: string; readonly pending: boolean; readonly danger?: boolean; readonly onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return <><Button variant={danger ? "danger" : "outline"} disabled={pending} onClick={() => setOpen(true)}>{pending ? "Working…" : label}</Button><Dialog open={open} onOpenChange={setOpen} title={title} description={description} size="sm"><div className="flex justify-end gap-3 pt-3"><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button variant={danger ? "danger" : "primary"} disabled={pending} onClick={() => { onConfirm(); setOpen(false); }}>{label}</Button></div></Dialog></>;
}

function governedDetails(error: ApiError): ApiErrorEnvelope | undefined {
  if (!error.details || typeof error.details !== "object") return undefined;
  return error.details as ApiErrorEnvelope;
}

export function fieldErrors(error: Error | null, field: string): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  return governedDetails(error)?.error.field_errors?.find((entry) => entry.field === field)?.message;
}

export function MutationNotice({ error, success }: { readonly error: Error | null; readonly success?: string }) {
  if (error) return <GovernedError error={error}/>;
  return success ? <p role="status" aria-live="polite" className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">{success}</p> : null;
}
