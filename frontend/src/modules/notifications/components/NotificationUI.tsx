/* eslint-disable react-refresh/only-export-components -- UI primitives intentionally share semantic helpers. */
import type { FormEvent, ReactNode } from "react";
import { AlertTriangle, Ban, ChevronLeft, ChevronRight, Inbox, LoaderCircle, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

export const PERMISSIONS = {
  inboxUpdate: "notifications.inbox:update", templateCreate: "notifications.template:create", templateUpdate: "notifications.template:update",
  templateActivate: "notifications.template:activate", templateArchive: "notifications.template:archive", deliveryDispatch: "notifications.delivery:dispatch",
  deliveryRetry: "notifications.delivery:retry", deliveryCancel: "notifications.delivery:cancel", preferenceUpdate: "notifications.preference:update",
  endpointCreate: "notifications.endpoint:create", endpointVerify: "notifications.endpoint:verify", endpointUpdate: "notifications.endpoint:update",
  endpointDelete: "notifications.endpoint:delete", configurationUpdate: "notifications.configuration:update", configurationImport: "notifications.configuration:import",
  configurationExport: "notifications.configuration:export", configurationRollback: "notifications.configuration:rollback",
} as const;

export function can(capabilities: readonly string[] | undefined, permission: string): boolean {
  return capabilities?.includes(permission) ?? false;
}

export function transitionKey(action: string): string {
  return `${action}:${crypto.randomUUID()}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown time" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function PageShell({ title, description, actions, children, back }: { readonly title: string; readonly description: string; readonly actions?: ReactNode; readonly children: ReactNode; readonly back?: { readonly label: string; readonly to: string } }) {
  return <main id="main-content" className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    {back ? <Link className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={back.to}><ChevronLeft className="h-4 w-4" />{back.label}</Link> : null}
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div className="min-w-0"><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground sm:text-base">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>
    {children}
  </main>;
}

export function PageSkeleton({ cards = 4 }: { readonly cards?: number }) {
  return <main aria-busy="true" aria-label="Loading notifications" className="mx-auto max-w-7xl space-y-6 p-4 sm:p-8"><Skeleton className="h-9 w-64"/><Skeleton className="h-5 w-full max-w-xl"/><div className="grid gap-4 sm:grid-cols-2">{Array.from({ length: cards }, (_, index) => <Skeleton key={index} className="h-36 w-full"/>)}</div><span className="sr-only" role="status">Loading</span></main>;
}

export function GovernedError({ error, retry, subject = "Notifications" }: { readonly error: unknown; readonly retry?: () => void; readonly subject?: string }) {
  const apiError = error instanceof ApiError ? error : null;
  const denied = apiError?.status === 401 || apiError?.status === 403;
  const unavailable = apiError?.status === 503;
  return <Card role="alert" className="p-8 text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">{denied ? <Ban className="h-6 w-6 text-destructive"/> : <AlertTriangle className="h-6 w-6 text-destructive"/>}</div><h2 className="mt-4 text-lg font-semibold">{denied ? "Permission denied" : unavailable ? `${subject} unavailable` : `Could not load ${subject.toLowerCase()}`}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{denied ? "Your current policy does not grant access to this area. Ask a tenant administrator if you need it." : apiError?.message ?? "The request did not complete. No success has been assumed."}</p>{apiError?.correlationId ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation {apiError.correlationId}</p> : null}{retry && !denied ? <Button className="mt-5" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</Card>;
}

export function EmptyPanel({ title, description, action }: { readonly title: string; readonly description: string; readonly action?: { readonly label: string; readonly to: string } }) {
  return <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center"><Inbox className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>{action ? <Link className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={action.to}>{action.label}</Link> : null}</Card>;
}

export function MutationError({ error }: { readonly error: unknown }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const denied = apiError?.status === 401 || apiError?.status === 403;
  return <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"><strong>{denied ? "Permission denied." : "Change not saved."}</strong> {denied ? "Your current tenant policy does not grant this action." : apiError?.message ?? "The operation failed and the previous state was retained."}{apiError?.correlationId ? <span className="mt-1 block font-mono text-xs">Correlation {apiError.correlationId}</span> : null}</div>;
}

export function PendingLabel({ pending, idle }: { readonly pending: boolean; readonly idle: string }) {
  return <>{pending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" aria-hidden="true"/> : null}{pending ? "Working…" : idle}</>;
}

export function Pagination({ page, totalPages, onPage }: { readonly page: number; readonly totalPages: number; readonly onPage: (page: number) => void }) {
  if (totalPages <= 1) return null;
  return <nav aria-label="Pagination" className="flex items-center justify-between gap-4 border-t p-4"><Button variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span><Button variant="outline" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></nav>;
}

export function StatusPill({ value }: { readonly value: string }) {
  const normalized = value.replaceAll("_", " ");
  const danger = ["failed", "unavailable", "error", "revoked"].includes(value);
  const good = ["active", "delivered", "healthy", "ready", "read", "sent"].includes(value);
  return <span role="status" className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs font-medium capitalize", danger ? "border-destructive/30 bg-destructive/10 text-destructive" : good ? "border-primary/30 bg-primary/10 text-primary" : "border-border bg-muted text-muted-foreground")}>{normalized}</span>;
}

export const fieldClass = "min-h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60";
export const labelClass = "space-y-1 text-sm font-medium";

export function JsonEditor({ id, label, value, onChange, rows = 8, help }: { readonly id: string; readonly label: string; readonly value: string; readonly onChange: (value: string) => void; readonly rows?: number; readonly help?: string }) {
  return <label className={labelClass} htmlFor={id}><span>{label}</span>{help ? <span className="block text-xs font-normal text-muted-foreground">{help}</span> : null}<textarea id={id} rows={rows} spellCheck={false} className={`${fieldClass} font-mono`} value={value} onChange={(event) => onChange(event.target.value)}/></label>;
}

export function submitForm(handler: () => void): (event: FormEvent<HTMLFormElement>) => void {
  return (event) => { event.preventDefault(); handler(); };
}
