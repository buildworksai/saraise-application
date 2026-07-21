/* eslint-disable react-refresh/only-export-components -- module-scoped UI helpers are intentionally colocated. */
import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, Box, ChevronLeft, ChevronRight, LockKeyhole, RefreshCw, SearchX, ServerOff, ShieldCheck } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { QUERY_KEYS, ROUTES, type PaginatedResult, type SecurityAuditLog, type UUID, type V2PageMeta } from "../contracts";
import { securityService } from "../services/security-service";

export function PageHeader({ title, description, actions }: { readonly title: string; readonly description: string; readonly actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ rows = 6, label = "Loading security administration data" }: { readonly rows?: number; readonly label?: string }) {
  return <main aria-busy="true" aria-label={label} className="space-y-6"><Skeleton className="h-20 w-full"/><Skeleton className="h-14 w-full"/><div className="space-y-3 rounded-xl border p-4">{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-16 w-full"/>)}</div></main>;
}

function presentError(error: Error): { title: string; message: string; Icon: typeof AlertTriangle; correlation?: string } {
  if (error instanceof ApiError && error.status === 403) return { title: "Access denied", message: "Your current security policy does not allow this action.", Icon: LockKeyhole, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 404) return { title: "Record not found", message: "This record does not exist or belongs to another tenant.", Icon: SearchX, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 503) return { title: "Security capability unavailable", message: "The security authority is not ready. Access remains denied until it recovers.", Icon: ServerOff, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 409) return { title: "Change conflict", message: "The record changed or is protected by active assignments. Reload and review before retrying.", Icon: RefreshCw, correlation: error.correlationId };
  return { title: "Security request failed", message: error.message || "The governed request failed safely.", Icon: AlertTriangle, correlation: error instanceof ApiError ? error.correlationId : undefined };
}

export function GovernedError({ error, retry }: { readonly error: Error; readonly retry?: () => void }) {
  const view = presentError(error); const Icon = view.Icon;
  return <section role="alert" className="rounded-xl border bg-card p-8 text-center"><Icon aria-hidden className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{view.message}</p>{view.correlation ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {view.correlation}</p> : null}{retry ? <Button className="mt-5" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</section>;
}

export function MutationError({ error }: { readonly error: Error }) { return <GovernedError error={error}/>; }

export function EmptyPanel({ filtered, noun, onReset, create }: { readonly filtered: boolean; readonly noun: string; readonly onReset?: () => void; readonly create?: () => void }) {
  return <section className="rounded-xl border border-dashed bg-card p-10 text-center"><Box className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{filtered ? `No ${noun} match these filters` : `No ${noun} yet`}</h2><p className="mt-2 text-sm text-muted-foreground">{filtered ? "Reset or broaden the server-side filters." : "No governed records exist for this tenant."}</p>{filtered && onReset ? <Button className="mt-5" variant="outline" onClick={onReset}>Reset filters</Button> : !filtered && create ? <Button className="mt-5" onClick={create}>Create first record</Button> : null}</section>;
}

export function Pagination({ value, onPage }: { readonly value: V2PageMeta; readonly onPage: (page: number) => void }) {
  return <nav aria-label="Pagination" className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between"><p>Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><Button variant="outline" size="sm" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></div></nav>;
}

export function StatusChip({ active, label }: { readonly active: boolean; readonly label?: string }) {
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"}`}>{label ?? (active ? "Active" : "Inactive")}</span>;
}

export interface Column<T> { readonly label: string; readonly render: (item: T) => ReactNode }
export function ResourceTable<T extends { readonly id: UUID }>({ result, columns, detailRoute, loadingMore }: { readonly result: PaginatedResult<T>; readonly columns: readonly Column<T>[]; readonly detailRoute: (id: UUID) => string; readonly loadingMore?: boolean }) {
  return <section className="overflow-hidden rounded-xl border bg-card"><div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[820px] text-sm"><thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr>{columns.map((column) => <th key={column.label} className="px-4 py-3">{column.label}</th>)}<th className="px-4 py-3"><span className="sr-only">Open</span></th></tr></thead><tbody className="divide-y">{result.items.map((item) => <tr key={item.id} className="hover:bg-muted/30">{columns.map((column) => <td key={column.label} className="px-4 py-4 align-top">{column.render(item)}</td>)}<td className="px-4 py-4 text-right"><Link className="rounded px-2 py-1 font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={detailRoute(item.id)}>View</Link></td></tr>)}</tbody></table></div><div className="grid gap-3 p-3 md:hidden">{result.items.map((item) => <Link key={item.id} to={detailRoute(item.id)} className="rounded-lg border p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><dl className="space-y-3">{columns.map((column) => <div key={column.label}><dt className="text-xs font-medium uppercase text-muted-foreground">{column.label}</dt><dd className="mt-1 text-sm">{column.render(item)}</dd></div>)}</dl></Link>)}</div><Pagination value={result.pagination} onPage={() => undefined}/>{loadingMore ? <p role="status" aria-live="polite" className="border-t px-4 py-2 text-xs text-muted-foreground">Loading updated security records…</p> : null}</section>;
}

export function ResourceGrid<T extends { readonly id: UUID }>({ result, render, onPage, loadingMore }: { readonly result: PaginatedResult<T>; readonly render: (item: T) => ReactNode; readonly onPage: (page: number) => void; readonly loadingMore?: boolean }) {
  return <section className="overflow-hidden rounded-xl border bg-card"><div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">{result.items.map((item) => <div key={item.id}>{render(item)}</div>)}</div><Pagination value={result.pagination} onPage={onPage}/>{loadingMore ? <p role="status" aria-live="polite" className="border-t px-4 py-2 text-xs text-muted-foreground">Loading updated security records…</p> : null}</section>;
}

export function DetailGrid({ children }: { readonly children: ReactNode }) { return <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>; }
export function Detail({ label, children }: { readonly label: string; readonly children: ReactNode }) { return <div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
export function Surface({ title, children }: { readonly title?: string; readonly children: ReactNode }) { return <Card>{title ? <CardHeader><CardTitle>{title}</CardTitle></CardHeader> : null}<CardContent className={title ? undefined : "p-6"}>{children}</CardContent></Card>; }
export function formatDate(value: string | null | undefined): string { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, [dirty]);
}

export function AuditTimeline({ resourceType, resourceId }: { readonly resourceType: string; readonly resourceId: UUID }) {
  const query = useQuery({ queryKey: [...QUERY_KEYS.auditLogs({ resource_type: resourceType, resource_id: resourceId }), "timeline"], queryFn: () => securityService.auditLogs.list({ resource_type: resourceType, resource_id: resourceId, ordering: "-timestamp", page_size: 10 }) });
  return <Surface title="Audit evidence">{query.isLoading ? <Skeleton className="h-24 w-full"/> : query.error ? <GovernedError error={query.error} retry={() => void query.refetch()}/> : query.data?.items.length ? <ol className="border-l pl-5">{query.data.items.map((entry: SecurityAuditLog) => <li key={entry.id} className="mb-5"><div className="flex flex-wrap items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary"/><Link to={ROUTES.AUDIT_LOG_DETAIL(entry.id)} className="font-medium text-primary hover:underline">{entry.action}</Link>{entry.decision ? <StatusChip active={entry.decision === "allow"} label={entry.decision}/> : null}</div><p className="mt-1 text-xs text-muted-foreground">{formatDate(entry.timestamp)} · actor {entry.actor_id}</p><Link to={`${ROUTES.AUDIT_LOGS}?correlation_id=${encodeURIComponent(entry.correlation_id)}`} className="font-mono text-xs text-muted-foreground hover:text-primary">{entry.correlation_id}</Link></li>)}</ol> : <p className="text-sm text-muted-foreground">No audit event is linked to this resource.</p>}</Surface>;
}

export function ConfirmButton({ label, question, pending, onConfirm }: { readonly label: string; readonly question: string; readonly pending: boolean; readonly onConfirm: () => void }) {
  return <Button variant="danger" disabled={pending} onClick={() => { if (window.confirm(question)) onConfirm(); }}>{pending ? "Working…" : label}</Button>;
}
