import { AlertCircle, Ban, Box, ChevronLeft, ChevronRight, LockKeyhole, RefreshCw, ServerOff } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ApiV2PageMeta, CapabilityState } from "../contracts";

export function PageHeader({ title, description, actions }: { readonly title: string; readonly description: string; readonly actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ rows = 5 }: { readonly rows?: number }) {
  return <main aria-busy="true" aria-label="Loading customization data" className="space-y-6"><Skeleton className="h-20 w-full"/><Skeleton className="h-14 w-full"/><div className="space-y-3 rounded-xl border p-4">{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-14 w-full"/>)}</div></main>;
}

function errorPresentation(error: Error): { title: string; message: string; icon: typeof AlertCircle; correlation?: string } {
  if (error instanceof ApiError && error.status === 403) return { title: "Access denied", message: "Your current role cannot access this customization. Its existence has not been disclosed.", icon: LockKeyhole, correlation: error.correlationId };
  if (error instanceof ApiError && (error.status === 503 || error.code === "capability_unavailable")) return { title: "Capability unavailable", message: "The target module is currently unavailable. Existing configuration remains safe and readable.", icon: ServerOff, correlation: error.correlationId };
  if (error instanceof ApiError && error.status === 409) return { title: "A newer revision exists", message: "Someone changed this item after you opened it. Reload the latest revision, review the differences, and apply your change again.", icon: RefreshCw, correlation: error.correlationId };
  return { title: "We could not load this view", message: error.message || "A governed request failed safely.", icon: AlertCircle, correlation: error instanceof ApiError ? error.correlationId : undefined };
}

export function GovernedError({ error, retry }: { readonly error: Error; readonly retry?: () => void }) {
  const view = errorPresentation(error); const Icon = view.icon;
  return <section role="alert" className="rounded-xl border bg-card p-8 text-center"><Icon className="mx-auto h-10 w-10 text-muted-foreground" aria-hidden/><h2 className="mt-4 text-lg font-semibold">{view.title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{view.message}</p>{view.correlation ? <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {view.correlation}</p> : null}{retry ? <Button className="mt-5" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</section>;
}

export function EmptyPanel({ filtered, noun, create }: { readonly filtered: boolean; readonly noun: string; readonly create?: () => void }) {
  return <section className="rounded-xl border border-dashed bg-card p-10 text-center"><Box className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-4 text-lg font-semibold">{filtered ? `No ${noun} match` : `No ${noun} yet`}</h2><p className="mt-2 text-sm text-muted-foreground">{filtered ? "Adjust or clear the server-side filters." : "Create the first governed customization for this tenant."}</p>{!filtered && create ? <Button className="mt-5" onClick={create}>Create {noun.replace(/s$/u, "")}</Button> : null}</section>;
}

export function StatusChip({ status }: { readonly status: string }) {
  const positive = ["active", "published", "matched", "healthy"].includes(status);
  const warning = ["draft", "paused", "deprecated", "candidate", "degraded"].includes(status);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${positive ? "bg-primary/10 text-primary" : warning ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"}`}>{status.replaceAll("_", " ")}</span>;
}

export function CapabilityNotice({ state }: { readonly state?: CapabilityState }) {
  return state === "capability_unavailable" ? <div role="status" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground"><Ban className="h-5 w-5 shrink-0 text-destructive"/><p>The owning module is unavailable. You can inspect this configuration, but publishing and evaluation are disabled until capability is restored.</p></div> : null;
}

export function Pagination({ meta, onPage }: { readonly meta?: ApiV2PageMeta; readonly onPage: (page: number) => void }) {
  if (!meta || meta.total_pages <= 1) return null;
  return <nav aria-label="Pagination" className="flex items-center justify-between border-t px-4 py-3 text-sm"><span>Page {meta.page} of {meta.total_pages} · {meta.count} results</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!meta.has_previous} onClick={() => onPage(meta.page - 1)}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><Button variant="outline" size="sm" disabled={!meta.has_next} onClick={() => onPage(meta.page + 1)}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></div></nav>;
}

export function ConfirmAction({ open, title, description, confirmLabel, pending, onOpenChange, onConfirm }: { readonly open: boolean; readonly title: string; readonly description: string; readonly confirmLabel: string; readonly pending?: boolean; readonly onOpenChange: (open: boolean) => void; readonly onConfirm: () => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description}><div className="flex justify-end gap-3 p-6 pt-0"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={pending} onClick={onConfirm}>{pending ? "Working…" : confirmLabel}</Button></div></Dialog>;
}

export function DetailGrid({ children }: { readonly children: ReactNode }) { return <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>; }
export function Detail({ label, children }: { readonly label: string; readonly children: ReactNode }) { return <div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
export function Surface({ children }: { readonly children: ReactNode }) { return <Card><CardContent className="p-5 sm:p-6">{children}</CardContent></Card>; }
