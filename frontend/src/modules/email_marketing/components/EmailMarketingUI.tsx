/* eslint-disable react-refresh/only-export-components -- helpers and hooks form one module-owned UI surface. */
import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CheckCircle2, Inbox, RefreshCw, XCircle } from 'lucide-react';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import type { ApiV2PaginationMeta, CampaignPreflight } from '../contracts';
import {
  configuredStatusTone,
  useEmailMarketingConfiguration,
} from '../hooks/use-email-marketing-configuration';

export function Page({ title, description, back, actions, children }: { readonly title: string; readonly description: string; readonly back?: { readonly label: string; readonly to: string }; readonly actions?: ReactNode; readonly children: ReactNode }) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · SARAISE`;
    return () => {
      document.title = previous;
    };
  }, [title]);
  return <main className="space-y-6 p-4 sm:p-6 lg:p-8"><header className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start"><div>{back ? <Link className="mb-3 inline-flex items-center text-sm text-muted-foreground hover:text-foreground" to={back.to}><ArrowLeft className="mr-2 h-4 w-4"/>{back.label}</Link> : null}<h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p></div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>{children}</main>;
}
export function Surface({ title, description, children }: { readonly title?: string; readonly description?: string; readonly children: ReactNode }) { return <section className="rounded-xl border bg-card p-4 shadow-sm sm:p-6">{title ? <h2 className="text-lg font-semibold">{title}</h2> : null}{description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}<div className={title || description ? 'mt-4' : ''}>{children}</div></section>; }
export function PageSkeleton({ rows = 5, label = 'Loading email marketing data' }: { readonly rows?: number; readonly label?: string }) { return <div className="space-y-6 p-4 sm:p-8" aria-busy="true" aria-label={label} role="status"><span className="sr-only">{label}</span><div className="h-9 w-72 animate-pulse rounded bg-muted"/><div className="h-5 w-96 max-w-full animate-pulse rounded bg-muted"/><div className="rounded-xl border p-5">{Array.from({ length: rows }, (_, index) => <div key={index} className="mb-4 h-12 animate-pulse rounded bg-muted last:mb-0"/>)}</div></div>; }

const messageFor = (error: unknown) => {
  if (!(error instanceof ApiError)) return { title: 'Email marketing is unavailable', message: error instanceof Error ? error.message : 'An unexpected error occurred.', code: 'UNKNOWN_ERROR', correlation: undefined };
  const messages: Record<number, [string, string]> = { 401: ['Sign in required', 'Your session is no longer valid. Sign in and retry.'], 403: ['Access or entitlement denied', 'Your role or subscription does not authorize this operation.'], 404: ['Record not found', 'The record does not exist or belongs to another tenant.'], 409: ['State conflict', 'The record changed or its current lifecycle state rejects this operation.'], 429: ['Quota or rate limit reached', 'Wait for the limit window or ask an administrator to review quota.'], 500: ['Service failure', 'The server could not complete the operation.'], 502: ['Invalid service response', 'The service response did not match the governed v2 contract.'], 503: ['Delivery dependency unavailable', 'A required delivery, queue, or resolver dependency is unavailable.'] };
  const selected = messages[error.status] ?? (error.status >= 500 ? messages[500] : undefined) ?? ['Request failed', error.message];
  return { title: selected[0], message: selected[1], code: error.code ?? `HTTP_${error.status}`, correlation: error.correlationId };
};
export function GovernedError({ error, retry }: { readonly error: unknown; readonly retry?: () => void }) { const info = messageFor(error); return <section role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-6"><div className="flex gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 text-destructive"/><div><h2 className="font-semibold">{info.title}</h2><p className="mt-1 text-sm text-muted-foreground">{info.message}</p><p className="mt-3 font-mono text-xs">{info.code}{info.correlation ? ` · correlation ${info.correlation}` : ''}</p>{retry ? <Button className="mt-4" variant="outline" onClick={retry}><RefreshCw className="mr-2 h-4 w-4"/>Retry</Button> : null}</div></div></section>; }
export function EmptyPanel({ filtered, noun, reset, create }: { readonly filtered: boolean; readonly noun: string; readonly reset?: () => void; readonly create?: () => void }) { return <Surface><div className="py-10 text-center"><Inbox className="mx-auto h-10 w-10 text-muted-foreground"/><h2 className="mt-3 font-semibold">{filtered ? `No ${noun} match these filters` : `No ${noun} yet`}</h2><p className="mt-1 text-sm text-muted-foreground">{filtered ? 'Reset or broaden the filters without losing your place.' : 'Your first record will appear here with durable evidence.'}</p><div className="mt-4 flex justify-center gap-2">{filtered && reset ? <Button variant="outline" onClick={reset}>Reset filters</Button> : null}{!filtered && create ? <Button onClick={create}>Create {noun.replace(/s$/u, '')}</Button> : null}</div></div></Surface>; }
const semanticStatusClasses = {
  success: 'border border-primary/20 bg-primary/10 text-primary',
  error: 'border border-destructive/20 bg-destructive/10 text-destructive',
  warning: 'border border-accent bg-accent text-accent-foreground',
  neutral: 'border border-border bg-muted text-muted-foreground',
} as const;
export function Status({ value }: { readonly value: string }) {
  const configuration = useEmailMarketingConfiguration();
  const tone = configuredStatusTone(value, configuration.data?.data.document);
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${semanticStatusClasses[tone]}`}>{value.replaceAll('_', ' ')}</span>;
}
export function Pagination({ value, onPage }: { readonly value: ApiV2PaginationMeta; readonly onPage: (page: number) => void }) { return <nav aria-label="Pagination" className="flex items-center justify-between gap-3 border-t px-4 py-3"><p className="text-xs text-muted-foreground">Page {value.page} of {Math.max(value.total_pages, 1)} · {value.count} records</p><div className="flex gap-2"><Button size="sm" variant="outline" disabled={!value.has_previous} onClick={() => onPage(value.page - 1)}>Previous</Button><Button size="sm" variant="outline" disabled={!value.has_next} onClick={() => onPage(value.page + 1)}>Next</Button></div></nav>; }
export function RefreshNotice({ active }: { readonly active: boolean }) { return active ? <p role="status" className="text-xs text-muted-foreground">Refreshing verified data…</p> : null; }
export function DetailGrid({ children }: { readonly children: ReactNode }) { return <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>; }
export function Detail({ label, children }: { readonly label: string; readonly children: ReactNode }) { return <div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
export function History({ entries }: { readonly entries: readonly { readonly key: string; readonly from_state: string; readonly to_state: string; readonly occurred_at: string; readonly actor_id: string | null; readonly correlation_id?: string }[] }) { return entries.length ? <ol className="space-y-3">{entries.map((entry) => <li key={entry.key} className="border-l-2 border-primary/40 pl-3 text-sm"><strong>{entry.from_state} → {entry.to_state}</strong><p className="text-muted-foreground">{new Date(entry.occurred_at).toLocaleString()} · actor {entry.actor_id ?? 'system'}</p>{entry.correlation_id ? <p className="font-mono text-xs">correlation {entry.correlation_id}</p> : null}</li>)}</ol> : <p className="text-sm text-muted-foreground">No lifecycle transition has been recorded.</p>; }

export function ConfirmAction({ label, title, description, pending, danger = false, onConfirm }: { readonly label: string; readonly title: string; readonly description: string; readonly pending: boolean; readonly danger?: boolean; readonly onConfirm: () => void }) { const [open, setOpen] = useState(false); return <><Button variant={danger ? 'danger' : 'outline'} disabled={pending} onClick={() => setOpen(true)}>{pending ? 'Working…' : label}</Button><Dialog open={open} onOpenChange={setOpen} title={title} description={description}><div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setOpen(false)}>Keep unchanged</Button><Button variant={danger ? 'danger' : 'primary'} disabled={pending} onClick={() => { onConfirm(); setOpen(false); }}>Confirm {label.toLowerCase()}</Button></div></Dialog></>; }
export function useUnsavedChanges(dirty: boolean) { useEffect(() => { const protect = (event: BeforeUnloadEvent) => { if (!dirty) return; event.preventDefault(); event.returnValue = ''; }; window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect); }, [dirty]); }
export const formatDate = (value: string | null) => value ? new Date(value).toLocaleString() : '—';

export function PreflightPanel({ value, campaignStatus }: { readonly value: CampaignPreflight; readonly campaignStatus: string }) {
  const consequence = campaignStatus === 'paused' ? 'Resume queues only recipients that remain eligible.' : campaignStatus === 'queueing' || campaignStatus === 'sending' ? 'Pause prevents new submissions; provider-accepted messages remain immutable.' : 'Send consumes recipient quota and durably queues eligible recipients. It does not claim delivery.';
  const checks = [
    ['Rendered content', value.content_valid && value.rendered, value.content_valid ? 'Validated and snapshotted' : 'Content needs attention'],
    ['Consent & suppression', value.consent_failure_count === 0 && value.suppression_failure_count === 0, `${value.eligible_count} eligible · ${value.suppressed_count} suppressed`],
    ['Sender configuration', value.sender_healthy, value.sender_detail],
    ['Recipient quota', value.quota_remaining === null || value.quota_remaining >= value.quota_required, `${value.quota_required} required · ${value.quota_remaining ?? 'unknown'} remaining`],
  ] as const;
  return <Surface title="Send-safety preflight" description="Authoritative service checks are visible before lifecycle commitment."><div className="grid gap-3 sm:grid-cols-2">{checks.map(([label, valid, detail]) => <div key={label} className="flex gap-3 rounded-lg border p-3">{valid ? <CheckCircle2 className="h-5 w-5 text-primary"/> : <XCircle className="h-5 w-5 text-destructive"/>}<div><p className="font-medium">{label}</p><p className="text-xs text-muted-foreground">{detail}</p></div></div>)}</div><div className="mt-4 rounded-lg bg-muted p-4 text-sm"><strong>Audience:</strong> {value.resolved_count} resolved, {value.eligible_count} eligible. <strong>Schedule:</strong> {value.scheduled_at ? formatDate(value.scheduled_at) : 'send when requested'} ({value.timezone}).<p className="mt-2">{consequence}</p></div>{value.blocking_reasons.length ? <ul className="mt-3 list-disc pl-5 text-sm text-destructive">{value.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : null}</Surface>;
}
