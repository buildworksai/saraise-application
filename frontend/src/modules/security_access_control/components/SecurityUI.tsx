/* eslint-disable react-refresh/only-export-components -- module-scoped UI helpers are intentionally colocated. */
import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, Box, ChevronLeft, ChevronRight, LockKeyhole, RefreshCw, SearchX, ServerOff, ShieldCheck } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { QUERY_KEYS, ROUTES, type DeletionReasonInput, type PaginatedResult, type SecurityAuditLog, type SecuritySemanticToken, type UUID, type V2PageMeta } from "../contracts";
import { useSecurityConfiguration } from "../hooks/use-security-configuration";
import { securityService } from "../services/security-service";

export function PageHeader({ title, description, actions }: { readonly title: string; readonly description: string; readonly actions?: ReactNode }) {
  useEffect(() => { document.title = `${title} · SARAISE`; }, [title]);
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ rows, label = "Loading security administration data" }: { readonly rows?: number; readonly label?: string }) {
  const configuration = useSecurityConfiguration();
  const configuredRows = rows ?? configuration.data?.data.document.ui.loading_skeleton_rows;
  return <main aria-busy="true" aria-label={label} className="space-y-6"><Skeleton className="h-20 w-full"/><Skeleton className="h-14 w-full"/>{configuredRows === undefined ? <Skeleton className="h-40 w-full"/> : <div className="space-y-3 rounded-xl border p-4">{Array.from({ length: configuredRows }, (_, index) => <Skeleton key={index} className="h-16 w-full"/>)}</div>}</main>;
}

function presentError(error: Error): { title: string; message: string; Icon: typeof AlertTriangle; correlation?: string } {
  if (error instanceof ApiError && error.status === 403) return { title: "Access denied", message: "Your current security policy does not allow this action.", Icon: LockKeyhole, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 404) return { title: "Record not found", message: "This record does not exist or belongs to another tenant.", Icon: SearchX, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 503) return { title: "Security capability unavailable", message: "The security authority is not ready. Access remains denied until it recovers.", Icon: ServerOff, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 409) return { title: "Change conflict", message: "The record changed or is protected by active assignments. Reload and review before retrying.", Icon: RefreshCw, correlation: error.correlationId };
  return { title: "Security request failed", message: error.message || "The governed request failed safely.", Icon: AlertTriangle, correlation: error instanceof ApiError ? error.correlationId : undefined };
}

export function GovernedError({ error, retry }: { readonly error: Error; readonly retry?: () => void }) {
  const view = presentError(error);
 const Icon = view.Icon;
  return <section role="alert" className="rounded-xl border bg-card p-8 text-center"><Icon aria-hidden className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{view.message}</p>{view.correlation ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {view.correlation}</p> : null}{retry ? <Button className="mt-5" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</section>;
}

export function MutationError({ error }: { readonly error: Error }) { return <GovernedError error={error}/>; }

export function EmptyPanel({ filtered, noun, onReset, create }: { readonly filtered: boolean; readonly noun: string; readonly onReset?: () => void; readonly create?: () => void }) {
  return <section className="rounded-xl border border-dashed bg-card p-10 text-center"><Box className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{filtered ? `No ${noun} match these filters` : `No ${noun} yet`}</h2><p className="mt-2 text-sm text-muted-foreground">{filtered ? "Reset or broaden the server-side filters." : "No governed records exist for this tenant."}</p>{filtered && onReset ? <Button className="mt-5" variant="outline" onClick={onReset}>Reset filters</Button> : !filtered && create ? <Button className="mt-5" onClick={create}>Create first record</Button> : null}</section>;
}

export function Pagination({ value, onPage }: { readonly value: V2PageMeta; readonly onPage: (page: number) => void }) {
  return <nav aria-label="Pagination" className="flex flex-col gap-3 border-t p-4 text-sm sm:flex-row sm:items-center sm:justify-between"><p>Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><Button variant="outline" size="sm" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></div></nav>;
}

const semanticTokenClasses: Readonly<Record<SecuritySemanticToken, string>> = {
  "status-success": "border border-primary/30 bg-primary/10 text-foreground",
  "status-danger": "border border-destructive/30 bg-destructive/10 text-destructive",
  "status-warning": "border border-accent bg-accent text-accent-foreground",
  "status-neutral": "border border-border bg-muted text-muted-foreground",
};

export function semanticClass(token: SecuritySemanticToken): string { return semanticTokenClasses[token]; }

export function StatusChip({ active, label }: { readonly active: boolean; readonly label?: string }) {
  const configuration = useSecurityConfiguration();
  const token = active ? configuration.data?.data.document.semantic_tokens.success : configuration.data?.data.document.semantic_tokens.neutral;
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${token ? semanticClass(token) : "border border-border bg-muted text-muted-foreground"}`}>{label ?? (active ? "Active" : "Inactive")}</span>;
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
  const configuration = useSecurityConfiguration();
  const pageSize = configuration.data?.data.document.ui.audit_timeline_page_size;
  const ordering = configuration.data?.data.document.ordering.audit_logs.join(",");
  const query = useQuery({ queryKey: [...QUERY_KEYS.auditLogs({ resource_type: resourceType, resource_id: resourceId }), "timeline", pageSize, ordering], queryFn: () => securityService.auditLogs.list({ resource_type: resourceType, resource_id: resourceId, ordering, page_size: pageSize }), enabled: pageSize !== undefined && ordering !== undefined });
  return <Surface title="Audit evidence">{configuration.error ? <GovernedError error={configuration.error} retry={() => void configuration.refetch()}/> : configuration.isLoading || query.isLoading ? <Skeleton className="h-24 w-full"/> : query.error ? <GovernedError error={query.error} retry={() => void query.refetch()}/> : query.data?.items.length ? <ol className="border-l pl-5">{query.data.items.map((entry: SecurityAuditLog) => <li key={entry.id} className="mb-5"><div className="flex flex-wrap items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary"/><Link to={ROUTES.AUDIT_LOG_DETAIL(entry.id)} className="font-medium text-primary hover:underline">{entry.action}</Link>{entry.decision ? <StatusChip active={entry.decision === "allow"} label={entry.decision}/> : null}</div><p className="mt-1 text-xs text-muted-foreground">{formatDate(entry.timestamp)} · actor type {entry.actor_type}</p><Link to={`${ROUTES.AUDIT_LOGS}?correlation_id=${encodeURIComponent(entry.correlation_id)}`} className="font-mono text-xs text-muted-foreground hover:text-primary">{entry.correlation_id}</Link></li>)}</ol> : <p className="text-sm text-muted-foreground">No audit event is linked to this resource.</p>}</Surface>;
}

export function ConfirmButton({ label, question, pending, onConfirm }: { readonly label: string; readonly question: string; readonly pending: boolean; readonly onConfirm: (input: DeletionReasonInput) => void }) {
  const configuration = useSecurityConfiguration();
  return <Button variant="danger" disabled={pending || !configuration.data} onClick={() => { const reason = window.prompt(`${question}\n\nEnter the mandatory audit reason:`)?.trim();
 const maximum = configuration.data?.data.document.limits.required_text_max_length;
 if (reason && maximum !== undefined && reason.length <= maximum) onConfirm({ reason }); }}>{pending ? "Working…" : label}</Button>;
}
