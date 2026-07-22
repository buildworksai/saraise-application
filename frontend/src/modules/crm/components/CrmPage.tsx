/* eslint-disable complexity -- each governed status has a distinct recovery path */
import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { CrmApiError } from '../services/crm-service';
import type { PaginationMeta } from '../contracts';

export function CrmPage({ title, description, parent, actions, children }: { title: string; description?: string; parent?: { label: string; to: string }; actions?: React.ReactNode; children: React.ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [title]);
  return <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground"><Link to="/crm/dashboard" className="hover:text-foreground">CRM</Link>{parent ? <> / <Link to={parent.to} className="hover:text-foreground">{parent.label}</Link></> : null} / <span aria-current="page">{title}</span></nav>
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><h1 ref={heading} tabIndex={-1} className="text-2xl font-bold outline-none sm:text-3xl">{title}</h1>{description ? <p className="mt-1 text-muted-foreground">{description}</p> : null}</div>{actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}</header>
    {children}
  </main>;
}

export function PageSkeleton({ label = 'Loading CRM data' }: { label?: string }) {
  return <div role="status" aria-label={label} className="space-y-4"><span className="sr-only">{label}</span><div className="h-10 w-2/5 animate-pulse rounded bg-muted"/><div className="h-24 animate-pulse rounded bg-muted"/><div className="h-64 animate-pulse rounded bg-muted"/></div>;
}

export function GovernedError({ error, onRetry, subject = 'CRM data' }: { error: unknown; onRetry?: () => void; subject?: string }) {
  const crmError = error instanceof CrmApiError ? error : null;
  const title = crmError?.kind === 'permission' ? 'Access denied' : crmError?.kind === 'not_found' ? `${subject} not found` : crmError?.kind === 'conflict' ? 'This record changed' : crmError?.kind === 'unavailable' ? 'Capability unavailable' : 'Unable to load CRM data';
  const recovery = crmError?.kind === 'authentication' ? 'Sign in again, then retry.' : crmError?.kind === 'permission' ? 'Ask an administrator for the required CRM permission.' : crmError?.kind === 'conflict' ? 'Reload the latest version before applying your changes.' : crmError?.kind === 'rate_limit' ? 'Wait briefly, then retry.' : crmError?.kind === 'not_found' ? 'Return to the list and choose another record.' : 'Check your connection and retry.';
  return <section role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-6"><AlertCircle className="mb-3 h-6 w-6 text-destructive"/><h2 className="text-lg font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{crmError?.message ?? recovery}</p><p className="mt-2 text-sm">{recovery}</p>{crmError?.correlationId ? <p className="mt-3 font-mono text-xs text-muted-foreground">Support reference: {crmError.correlationId}</p> : null}{onRetry && crmError?.kind !== 'permission' && crmError?.kind !== 'not_found' ? <Button className="mt-4" onClick={onRetry}>Retry</Button> : null}</section>;
}

export function EmptyPanel({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) { return <section className="rounded-lg border border-dashed p-10 text-center"><h2 className="text-lg font-semibold">{title}</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</section>; }
export function LiveRegion({ message }: { message?: string | null }) { return <p aria-live="polite" aria-atomic="true" className="sr-only">{message}</p>; }

export function Pagination({ meta, onPage }: { meta: PaginationMeta; onPage: (page: number) => void }) { return <div className="flex items-center justify-between border-t px-4 py-3 text-sm"><span>{meta.count} results · Page {meta.page} of {Math.max(meta.total_pages, 1)}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!meta.has_previous} onClick={() => onPage(meta.page - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4"/></Button><Button variant="outline" size="sm" disabled={!meta.has_next} onClick={() => onPage(meta.page + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4"/></Button></div></div>; }

export function SubmitButton({ pending, label }: { pending: boolean; label: string }) { return <Button type="submit" disabled={pending}>{pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true"/> : null}{pending ? 'Saving…' : label}</Button>; }

export const fieldClass = 'block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-60';
export function Field({ id, label, error, required, children, hint }: { id: string; label: string; error?: string; required?: boolean; children: React.ReactNode; hint?: string }) { return <div><label htmlFor={id} className="mb-1 block text-sm font-medium">{label}{required ? <span aria-hidden="true"> *</span> : null}</label>{children}{hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}{error ? <p role="alert" className="mt-1 text-sm text-destructive">{error}</p> : null}</div>; }
