import type { ReactNode } from "react";
import { AlertTriangle, Copy, LockKeyhole, ServerOff, Workflow } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { WorkflowApiError } from "../services/workflow-service";

export function PageHeader({ eyebrow = "Workflow automation", title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between"><div className="max-w-3xl"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>;
}

export function PageSkeleton({ label = "Loading workflow data", rows = 5 }: { label?: string; rows?: number }) {
  return <div aria-label={label} aria-busy="true" className="space-y-4"><Skeleton className="h-10 w-72"/><Skeleton className="h-20 w-full"/>{Array.from({ length: rows }, (_, index) => <Skeleton key={index} className="h-16 w-full"/>)}</div>;
}

export function WorkflowProblem({ error, retry }: { error: Error; retry: () => void }) {
  const api = error instanceof WorkflowApiError ? error : null;
  const denied = api?.status === 403;
  const missing = api?.status === 404;
  const degraded = api?.status === 503;
  const Icon = denied ? LockKeyhole : degraded ? ServerOff : AlertTriangle;
  const title = denied ? "Permission required" : missing ? "Workflow record not found" : degraded ? "Workflow capability unavailable" : "Workflow data is unavailable";
  const message = denied ? "Your role is not allowed to use this workflow surface." : missing ? "The record may have been removed or belongs to another tenant." : degraded ? "A required workflow handler or delivery dependency is unavailable. No success has been assumed." : error.message;
  return <Card role="alert" className="border-destructive/30"><CardContent className="flex min-h-72 flex-col items-center justify-center text-center"><Icon className="mb-4 h-10 w-10 text-destructive" aria-hidden="true"/><h2 className="text-xl font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{message}</p>{api?.correlationId ? <div className="mt-4 flex items-center gap-2 rounded bg-muted px-3 py-2 font-mono text-xs"><span>Correlation: {api.correlationId}</span><Button size="icon" variant="ghost" aria-label="Copy correlation ID" onClick={() => void navigator.clipboard.writeText(api.correlationId ?? "")}><Copy className="h-3 w-3"/></Button></div> : null}<Button className="mt-5" variant="outline" onClick={retry}>Retry</Button></CardContent></Card>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <Card><CardContent className="flex min-h-64 flex-col items-center justify-center text-center"><span className="mb-4 rounded-2xl bg-primary/10 p-3 text-primary"><Workflow aria-hidden="true"/></span><h2 className="text-xl font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</CardContent></Card>;
}

const colors: Readonly<Record<string, string>> = { draft: "bg-amber-100 text-amber-800", published: "bg-emerald-100 text-emerald-800", archived: "bg-zinc-100 text-zinc-700", pending: "bg-amber-100 text-amber-800", running: "bg-blue-100 text-blue-800", waiting: "bg-violet-100 text-violet-800", completed: "bg-emerald-100 text-emerald-800", failed: "bg-red-100 text-red-800", rejected: "bg-red-100 text-red-800", cancelled: "bg-zinc-100 text-zinc-700", expired: "bg-orange-100 text-orange-800", available: "bg-emerald-100 text-emerald-800", locked: "bg-zinc-100 text-zinc-700", setup_required: "bg-amber-100 text-amber-800", degraded: "bg-red-100 text-red-800" };
export function StatusPill({ status }: { status: string }) { return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${colors[status] ?? "bg-muted text-muted-foreground"}`}>{status.replaceAll("_", " ")}</span>; }
export function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) { return <nav aria-label="Pagination" className="flex items-center justify-end gap-3 pt-4"><span className="text-sm text-muted-foreground">Page {page} of {Math.max(1, totalPages)}</span><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button><Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button></nav>; }
