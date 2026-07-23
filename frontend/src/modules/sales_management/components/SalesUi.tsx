import { useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react';
import type { ApiV2Page, TransitionRecord } from '../contracts';

export const newIdempotencyKey = (): string => crypto.randomUUID();

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);
}

export function SalesPage({ title, description, actions, children }: { title: string; description: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div><h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>{children}
  </main>;
}

export function GovernedError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : undefined;
  const title = api?.status === 403 ? 'Access denied' : api?.status === 404 ? 'Record not found' : api?.status === 409 ? 'This record changed' : api?.status === 503 ? 'Capability unavailable' : 'Sales data unavailable';
  const message = `${api?.message ?? 'The request could not be completed.'}${api?.correlationId ? ` Reference: ${api.correlationId}` : ''}`;
  return <div role="alert"><ErrorState title={title} message={message} onRetry={onRetry} /></div>;
}

export interface ListColumn<T> { key: string; label: string; render: (row: T) => React.ReactNode }
export function ResourceList<T extends { id: string }>({
  title, description, createLabel, createPath, detailPath, queryResult, columns, emptyTitle, searchPlaceholder, orderingOptions, filterOptions = [],
}: {
  title: string; description: string; createLabel: string; createPath: string; detailPath: (id: string) => string;
  queryResult: { data?: ApiV2Page<T>; isLoading: boolean; isFetching: boolean; error: unknown; refetch: () => Promise<unknown> };
  columns: ListColumn<T>[]; emptyTitle: string; searchPlaceholder: string; orderingOptions: Array<{ value: string; label: string }>; filterOptions?: Array<{ key: string; label: string; options: Array<{ value: string; label: string }> }>;
}) {
  const [parameters, setParameters] = useSearchParams();
  const page = Math.max(1, Number(parameters.get('page') ?? 1) || 1);
  const update = (key: string, value: string) => { const next = new URLSearchParams(parameters); value ? next.set(key, value) : next.delete(key); if (key !== 'page') next.set('page', '1'); setParameters(next); };
  if (queryResult.isLoading) return <SalesPage title={title} description={description}><div aria-label={`Loading ${title.toLowerCase()}`}><TableSkeleton rows={6} columns={columns.length + 1} /></div></SalesPage>;
  if (queryResult.error) return <SalesPage title={title} description={description}><GovernedError error={queryResult.error} onRetry={() => void queryResult.refetch()} /></SalesPage>;
  const records = queryResult.data?.data ?? [];
  const pagination = queryResult.data?.meta.pagination;
  return <SalesPage title={title} description={description} actions={<Link to={createPath}><Button><Plus className="mr-2 h-4 w-4" />{createLabel}</Button></Link>}>
    <Card><CardContent className="pt-6"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label className="relative"><span className="sr-only">Search</span><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"/><input className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm text-foreground" placeholder={searchPlaceholder} value={parameters.get('search') ?? ''} onChange={(event) => update('search', event.target.value)} /></label>
      <label><span className="sr-only">Order records</span><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={parameters.get('ordering') ?? orderingOptions[0]?.value ?? ''} onChange={(event) => update('ordering', event.target.value)}>{orderingOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      {filterOptions.map((filter) => <label key={filter.key}><span className="sr-only">{filter.label}</span><select aria-label={filter.label} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={parameters.get(filter.key) ?? ''} onChange={(event) => update(filter.key, event.target.value)}><option value="">All {filter.label.toLowerCase()}</option>{filter.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>)}
      <span aria-live="polite" className="self-center text-sm text-muted-foreground">{queryResult.isFetching ? 'Refreshing…' : pagination ? `${pagination.count} records` : ''}</span>
    </div></CardContent></Card>
    {records.length === 0 ? <EmptyState icon={Plus} title={emptyTitle} description={`Create the first ${title.toLowerCase().replace(/s$/, '')} to continue the quote-to-delivery flow.`} action={{ label: createLabel, onClick: () => { window.location.assign(createPath); } }} /> : <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="min-w-full divide-y divide-border"><thead className="bg-muted/50"><tr>{columns.map((column) => <th key={column.key} scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{column.label}</th>)}<th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground">Action</th></tr></thead><tbody className="divide-y divide-border">{records.map((record) => <tr key={record.id} className="hover:bg-muted/40">{columns.map((column) => <td key={column.key} className="whitespace-nowrap px-4 py-3 text-sm text-foreground">{column.render(record)}</td>)}<td className="px-4 py-3 text-right"><Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" to={detailPath(record.id)}>View</Link></td></tr>)}</tbody></table></div>
      {pagination && <nav aria-label="Pagination" className="flex items-center justify-between border-t border-border px-4 py-3"><Button variant="outline" size="sm" disabled={!pagination.has_previous} onClick={() => update('page', String(page - 1))}><ChevronLeft className="mr-1 h-4 w-4"/>Previous</Button><span className="text-sm text-muted-foreground">Page {pagination.page} of {Math.max(1, pagination.total_pages)}</span><Button variant="outline" size="sm" disabled={!pagination.has_next} onClick={() => update('page', String(page + 1))}>Next<ChevronRight className="ml-1 h-4 w-4"/></Button></nav>}
    </Card>}
  </SalesPage>;
}

export function StatusPill({ status }: { status: string }) { return <span className="inline-flex rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-foreground">{status.replaceAll('_', ' ')}</span>; }
export function DetailGrid({ entries }: { entries: Array<[string, React.ReactNode]> }) { return <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{entries.map(([label, value]) => <div key={label}><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 text-sm text-foreground">{value || '—'}</dd></div>)}</dl>; }
export function Timeline({ records }: { records: TransitionRecord[] }) { return <Card><CardHeader><CardTitle>Transition evidence</CardTitle></CardHeader><CardContent>{records.length === 0 ? <p className="text-sm text-muted-foreground">No transitions have occurred.</p> : <ol className="space-y-4 border-l border-border pl-5">{records.map((record, index) => <li key={`${record.occurred_at}-${index}`}><p className="font-medium text-foreground">{record.from_status} → {record.to_status}</p><p className="text-sm text-muted-foreground">{record.command} · {new Date(record.occurred_at).toLocaleString()}</p>{record.reason && <p className="text-sm text-muted-foreground">{record.reason}</p>}</li>)}</ol>}</CardContent></Card>; }
export function useListFilters(): Record<string, string | number | boolean | undefined> { const [parameters] = useSearchParams(); return useMemo(() => { const result: Record<string,string|number|boolean|undefined>={page:1,page_size:25}; parameters.forEach((value,key)=>{result[key]=key==='page'||key==='page_size'?Number(value):key==='is_active'?value==='true':value;}); return result; }, [parameters]); }
