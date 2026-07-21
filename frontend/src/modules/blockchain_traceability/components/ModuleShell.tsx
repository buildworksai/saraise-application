/* eslint-disable react-refresh/only-export-components */
import { useState, type ReactNode } from 'react';
import { AlertTriangle, Check, Clipboard, Download, FileQuestion, RefreshCw, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/auth-store';
import type { ApiV2Pagination, JsonValue, ProofStatus, VerificationAttempt, VerificationOutcome } from '../contracts';
import { BlockchainTraceabilityApiError } from '../services/blockchain_traceability-service';

export function useCanMutateTraceability(): boolean {
  // Presentation hint only. The governed API remains authoritative and every 403 is surfaced.
  return useAuthStore((state) => state.user?.is_superuser === true || state.user?.is_staff === true || state.user?.tenant_role === 'tenant_admin');
}

export function Breadcrumbs({ items }: { items: readonly { label: string; to?: string }[] }) {
  return <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground"><ol className="flex flex-wrap items-center gap-2">{items.map((item, index) => <li key={`${item.label}-${index}`} className="flex items-center gap-2">{index > 0 && <span aria-hidden="true">/</span>}{item.to ? <Link className="hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}</li>)}</ol></nav>;
}

export function PageHeader({ title, description, actions, breadcrumbs }: { title: string; description: string; actions?: ReactNode; breadcrumbs?: ReactNode }) {
  return <header className="space-y-4">{breadcrumbs}<div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h1 className="text-3xl font-bold tracking-tight">{title}</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</div></header>;
}

export function PageSkeleton({ label = 'Loading traceability evidence' }: { label?: string }) {
  return <main className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label={label}><div className="space-y-3"><Skeleton className="h-5 w-48" /><Skeleton className="h-10 w-80" /><Skeleton className="h-4 w-full max-w-2xl" /></div><div className="grid gap-4 sm:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><TableSkeleton rows={6} columns={5} /></main>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <Card className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><div className="rounded-full bg-muted p-4"><FileQuestion className="h-8 w-8 text-muted-foreground" /></div><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action && <div className="mt-5">{action}</div>}</Card>;
}

export function ApiProblem({ error, onRetry, mutation = false }: { error: unknown; onRetry?: () => void; mutation?: boolean }) {
  const apiError: BlockchainTraceabilityApiError | null = error instanceof BlockchainTraceabilityApiError ? error : null;
  const denied = apiError !== null && (apiError.status === 401 || apiError.status === 403);
  const title = denied ? 'Permission required' : apiError?.status === 503 ? 'Verification dependency unavailable' : 'Traceability request failed';
  const description = denied ? 'Your session is valid, but the required tenant capability was not granted.' : apiError !== null ? apiError.message : 'The operation could not be completed. No success has been assumed.';
  return <Card className={`${mutation ? 'p-4' : 'min-h-72 p-8'} flex flex-col items-center justify-center text-center`} role="alert"><div className={`rounded-full p-4 ${denied ? 'bg-amber-500/10' : 'bg-destructive/10'}`}>{denied ? <ShieldAlert className="h-8 w-8 text-amber-700" /> : <AlertTriangle className="h-8 w-8 text-destructive" />}</div><h2 className="mt-4 text-lg font-semibold">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{apiError?.correlationId && <p className="mt-3 font-mono text-xs text-muted-foreground">Correlation ID: {apiError.correlationId}</p>}{onRetry && !denied && <Button className="mt-5" variant="secondary" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>}</Card>;
}

export function Pagination({ value, onPage }: { value: ApiV2Pagination; onPage: (page: number) => void }) {
  return <nav className="flex flex-col gap-3 border-t p-4 sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination"><p className="text-sm text-muted-foreground">Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}>Previous</Button><Button variant="outline" size="sm" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next</Button></div></nav>;
}

export function StatusPill({ status }: { status: string }) {
  const positive = ['active', 'confirmed', 'finalized', 'healthy', 'pass'].includes(status);
  const warning = ['draft', 'queued', 'submitting', 'submitted', 'degraded', 'recalled', 'warning'].includes(status);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${positive ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : warning ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300' : 'bg-muted text-muted-foreground'}`}>{status.replaceAll('_', ' ')}</span>;
}

export const PROOF_LABELS: Readonly<Record<ProofStatus, string>> = {
  locally_consistent: 'Locally consistent — not externally anchored',
  externally_verified: 'Externally verified',
  invalid: 'Invalid proof',
  unavailable: 'Verification unavailable',
};

export function proofStatusForAttempt(attempt: VerificationAttempt): ProofStatus {
  if (attempt.proof_evidence.simulated_provider) return 'unavailable';
  if (attempt.outcome === 'verified') return attempt.proof_evidence.externally_anchored ? 'externally_verified' : 'locally_consistent';
  if (attempt.outcome === 'dependency_unavailable' || attempt.outcome === 'inconclusive') return 'unavailable';
  return 'invalid';
}

export function ProofBadge({ status, simulated = false }: { status: ProofStatus; simulated?: boolean }) {
  const safeStatus = simulated && status === 'externally_verified' ? 'unavailable' : status;
  const color = safeStatus === 'externally_verified' ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : safeStatus === 'locally_consistent' ? 'bg-blue-500/15 text-blue-700 dark:text-blue-300' : safeStatus === 'invalid' ? 'bg-destructive/15 text-destructive' : 'bg-amber-500/15 text-amber-700 dark:text-amber-300';
  return <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${color}`}>{simulated ? 'Simulated provider — verification unavailable' : PROOF_LABELS[safeStatus]}</span>;
}

export function OutcomeBadge({ outcome, simulated = false }: { outcome: VerificationOutcome; simulated?: boolean }) {
  const status: ProofStatus = simulated || outcome === 'dependency_unavailable' || outcome === 'inconclusive'
    ? 'unavailable'
    : outcome === 'verified'
      ? 'externally_verified'
      : 'invalid';
  return <ProofBadge status={status} simulated={simulated} />;
}

export function HashValue({ value, label }: { value: string; label: string }) {
  return <div className="min-w-0"><p className="text-xs font-medium text-muted-foreground">{label}</p><div className="mt-1 flex items-center gap-2"><code className="block min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs" title={value}>{value || 'Genesis (no previous hash)'}</code>{value && <CopyButton value={value} label={`Copy ${label}`} />}</div></div>;
}

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1600); };
  return <Button type="button" size="icon" variant="ghost" aria-label={label} onClick={() => { void copy(); }}>{copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}</Button>;
}

export function JsonEvidence<T extends JsonValue | object>({ value, label = 'Evidence JSON' }: { value: T; label?: string }) {
  return <div><p className="mb-2 text-sm font-medium">{label}</p><pre className="max-h-80 overflow-auto rounded-lg border bg-muted/40 p-4 text-xs">{JSON.stringify(value, null, 2)}</pre></div>;
}

function canonicalizeEvidence(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalizeEvidence);
  if (value === null || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, entry]) => [key, canonicalizeEvidence(entry)]));
}

/** Stable property ordering makes independently exported evidence byte-for-byte comparable. */
export function stableEvidenceJson(value: JsonValue | object): string {
  return JSON.stringify(canonicalizeEvidence(value), null, 2);
}

export function EvidenceExport<T extends JsonValue | object>({ filename, value, signed = false }: { filename: string; value: T; signed?: boolean }) {
  const download = () => { const content = stableEvidenceJson(value); const url = URL.createObjectURL(new Blob([content], { type: 'application/json' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); };
  return <Button variant="outline" onClick={download}><Download className="mr-2 h-4 w-4" />Export {signed ? 'signed' : 'local unsigned'} JSON</Button>;
}

export function DefinitionGrid({ children }: { children: ReactNode }) {
  return <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>;
}

export function Definition({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 rounded-lg border p-4"><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-2 break-words text-sm">{children}</dd></div>;
}
