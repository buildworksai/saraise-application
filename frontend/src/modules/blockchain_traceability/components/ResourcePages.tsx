/* eslint-disable react-refresh/only-export-components */
import { useState, type FormEvent, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { JsonObject, JsonValue, PageFilters, PageResult } from '../contracts';
import { ROUTE_PATHS } from '../contracts';
import { ApiProblem, Breadcrumbs, ConfiguredStatusPill, EmptyPanel, PageHeader, PageSkeleton, Pagination, useCanMutateTraceability } from './ModuleShell';
import { BlockchainTraceabilityApiError } from '../services/blockchain_traceability-service';
import { useTraceabilityCapabilities } from '../hooks/use-traceability-configuration';

export interface ListPageConfig<T extends { id: string }, F extends PageFilters> {
  queryKey: string;
  title: string;
  description: string;
  noun: string;
  createLabel?: string;
  createPath?: string;
  detailPath: (id: string) => string;
  list: (filters: F) => Promise<PageResult<T>>;
  filters: (params: URLSearchParams, pageSize: number) => F;
  titleFor: (item: T) => string;
  subtitleFor: (item: T) => string;
  statusFor: (item: T) => string;
  facts: (item: T) => readonly { label: string; value: ReactNode }[];
  statusOptions?: readonly string[];
  orderingOptions: readonly { value: string; label: string }[];
  emptyGuidance: string;
}

function positivePage(value: string | null): number {
  const parsed = Number(value ?? '1');
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

const EFFECTIVE_PAGE_SIZE_PARAMETER = '__traceability_effective_page_size';

export function defaultPageFilters(params: URLSearchParams, pageSize?: number): PageFilters {
  const effectivePageSize = pageSize ?? Number(params.get(EFFECTIVE_PAGE_SIZE_PARAMETER));
  if (!Number.isInteger(effectivePageSize) || effectivePageSize < 1) throw new Error('The governed API did not provide a valid list page size.');
  return { page: positivePage(params.get('page')), page_size: effectivePageSize, search: params.get('search') ?? undefined, ordering: params.get('ordering') ?? undefined };
}

type DisplayConfig<T extends { id: string }> = Pick<ListPageConfig<T, PageFilters>, 'titleFor' | 'subtitleFor' | 'statusFor' | 'facts'>;

function ResourceCard<T extends { id: string }>({ item, config, open }: { item: T; config: DisplayConfig<T>; open: () => void }) {
  return <Card className="p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><button className="truncate text-left font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={open}>{config.titleFor(item)}</button><p className="mt-1 truncate text-xs text-muted-foreground">{config.subtitleFor(item)}</p></div><ConfiguredStatusPill status={config.statusFor(item)} /></div><dl className="mt-4 grid grid-cols-2 gap-3">{config.facts(item).slice(0, 4).map((fact) => <div key={fact.label}><dt className="text-xs text-muted-foreground">{fact.label}</dt><dd className="mt-1 truncate text-sm">{fact.value}</dd></div>)}</dl></Card>;
}

// Generic branching is deliberate: it owns the complete loading/error/empty/success state machine.
// eslint-disable-next-line complexity
export function ResourceListPage<T extends { id: string }, F extends PageFilters>({ config }: { config: ListPageConfig<T, F> }) {
  const navigate = useNavigate();
  const canMutate = useCanMutateTraceability();
  const capabilities = useTraceabilityCapabilities();
  const [params, setParams] = useSearchParams();
  const pageSize = capabilities.data?.document.list_policy.default_page_size;
  const governedParams = new URLSearchParams(params);
  if (pageSize !== undefined) governedParams.set(EFFECTIVE_PAGE_SIZE_PARAMETER, String(pageSize));
  const filters = pageSize === undefined ? ({} as F) : config.filters(governedParams, pageSize);
  const query = useQuery({ queryKey: ['blockchain-traceability', config.queryKey, params.toString(), pageSize], queryFn: () => config.list(filters), enabled: pageSize !== undefined });
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.set('page', '1'); setParams(next); };
  const submitSearch = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); const value = form.get('search'); update('search', typeof value === 'string' ? value.trim() : ''); };
  if (capabilities.isLoading || query.isLoading) return <PageSkeleton label={`Loading ${config.noun}`} />;
  if (capabilities.error || query.error || !query.data) return <main className="p-4 sm:p-8"><ApiProblem error={capabilities.error ?? query.error} onRetry={() => { void Promise.all([capabilities.refetch(), query.refetch()]); }} /></main>;
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title={config.title} description={config.description} breadcrumbs={<Breadcrumbs items={[{ label: 'Traceability', to: ROUTE_PATHS.ASSETS }, { label: config.title }]} />} actions={canMutate && config.createPath ? <Button onClick={() => navigate(config.createPath!)}><Plus className="mr-2 h-4 w-4" />{config.createLabel ?? `Create ${config.noun}`}</Button> : undefined} />
    <Card className="p-4"><form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem_12rem_auto]" role="search" onSubmit={submitSearch}><Input id={`${config.queryKey}-search`} name="search" defaultValue={params.get('search') ?? ''} aria-label={`Search ${config.noun}`} placeholder={`Search ${config.noun}…`} />{config.statusOptions ? <select className="rounded-md border border-input bg-background px-3 py-2 text-sm" aria-label="Filter by status" value={params.get('status') ?? ''} onChange={(event) => update('status', event.target.value)}><option value="">All statuses</option>{config.statusOptions.map((status) => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}</select> : <span /> }<select className="rounded-md border border-input bg-background px-3 py-2 text-sm" aria-label="Sort results" value={params.get('ordering') ?? config.orderingOptions[0]?.value ?? ''} onChange={(event) => update('ordering', event.target.value)}>{config.orderingOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><Button type="submit" variant="secondary"><Search className="mr-2 h-4 w-4" />Search</Button></form></Card>
    {query.data.items.length === 0 ? <EmptyPanel title={`No ${config.noun} found`} description={params.toString() ? 'No records match the selected server-side filters. Clear or adjust the filters and retry.' : config.emptyGuidance} action={canMutate && config.createPath ? <Button onClick={() => navigate(config.createPath!)}>{config.createLabel ?? `Create ${config.noun}`}</Button> : undefined} /> : <Card className="overflow-hidden"><div className="grid gap-3 p-3 md:hidden">{query.data.items.map((item) => <ResourceCard key={item.id} item={item} config={config} open={() => navigate(config.detailPath(item.id))} />)}</div><div className="hidden overflow-x-auto md:block"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground"><tr><th className="p-4">{config.noun}</th><th className="p-4">Status</th>{(query.data.items[0] ? config.facts(query.data.items[0]) : []).slice(0, 3).map((fact) => <th key={fact.label} className="p-4">{fact.label}</th>)}<th className="p-4"><span className="sr-only">Open</span></th></tr></thead><tbody>{query.data.items.map((item) => <tr key={item.id} className="border-b hover:bg-muted/40"><td className="p-4"><button className="font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(config.detailPath(item.id))}>{config.titleFor(item)}</button><p className="mt-1 max-w-xs truncate text-xs text-muted-foreground">{config.subtitleFor(item)}</p></td><td className="p-4"><ConfiguredStatusPill status={config.statusFor(item)} /></td>{config.facts(item).slice(0, 3).map((fact) => <td key={fact.label} className="max-w-xs truncate p-4">{fact.value}</td>)}<td className="p-4 text-right"><Button size="sm" variant="ghost" onClick={() => navigate(config.detailPath(item.id))}>View evidence</Button></td></tr>)}</tbody></table></div><Pagination value={query.data.pagination} onPage={(page) => update('page', String(page))} /></Card>}
  </main>;
}

export interface DetailPageConfig<T> {
  queryKey: string;
  id: string;
  title: (item: T) => string;
  description: (item: T) => string;
  listLabel: string;
  listPath: string;
  get: (id: string) => Promise<T>;
  render: (item: T) => ReactNode;
  actions?: (item: T) => ReactNode;
}

export function ResourceDetailPage<T>({ config }: { config: DetailPageConfig<T> }) {
  const query = useQuery({ queryKey: ['blockchain-traceability', config.queryKey, config.id], queryFn: () => config.get(config.id), enabled: Boolean(config.id) });
  if (query.isLoading) return <PageSkeleton label={`Loading ${config.listLabel} evidence`} />;
  if (query.error || !query.data) return <main className="p-4 sm:p-8"><ApiProblem error={query.error} onRetry={() => { void query.refetch(); }} /></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={config.title(query.data)} description={config.description(query.data)} breadcrumbs={<Breadcrumbs items={[{ label: 'Traceability', to: ROUTE_PATHS.ASSETS }, { label: config.listLabel, to: config.listPath }, { label: config.title(query.data) }]} />} actions={config.actions?.(query.data)} />{config.render(query.data)}</main>;
}

export interface FormField {
  name: string;
  label: string;
  required?: boolean;
  type?: 'text' | 'number' | 'datetime-local' | 'textarea' | 'json' | 'password';
  placeholder?: string;
  help?: string;
  defaultValue?: string | number;
}

export function MutationForm({ fields, submitLabel, onSubmit, onCancel, caution }: { fields: readonly FormField[]; submitLabel: string; onSubmit: (data: FormData) => Promise<void>; onCancel: () => void; caution?: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<ReadonlyMap<string, string>>(new Map());
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setPending(true); setError(null); setFieldErrors(new Map()); try { await onSubmit(new FormData(event.currentTarget)); } catch (failure) { setError(failure); if (failure instanceof BlockchainTraceabilityApiError) { const apiFailure: BlockchainTraceabilityApiError = failure; setFieldErrors(apiFailure.fieldErrors); } } finally { setPending(false); } };
  return <form className="space-y-6" onSubmit={(event) => { void submit(event); }} aria-busy={pending}>{caution && <div className="rounded-lg border text-accent-foreground bg-accent p-4 text-sm text-accent-foreground" role="note">{caution}</div>}{error !== null && <ApiProblem error={error} mutation /> }<Card className="grid gap-5 p-6 md:grid-cols-2">{fields.map((field) => { const errorMessage = fieldErrors.get(field.name); const common = { id: field.name, name: field.name, label: field.label, required: field.required, placeholder: field.placeholder, defaultValue: field.defaultValue, error: errorMessage, 'aria-describedby': field.help ? `${field.name}-help` : undefined }; return <div key={field.name} className={field.type === 'textarea' || field.type === 'json' ? 'md:col-span-2' : undefined}>{field.type === 'textarea' || field.type === 'json' ? <Textarea {...common} rows={field.type === 'json' ? 8 : 4} spellCheck={field.type !== 'json'} /> : <Input {...common} type={field.type ?? 'text'} />}{field.help && <p id={`${field.name}-help`} className="mt-1 text-xs text-muted-foreground">{field.help}</p>}</div>; })}</Card><div className="flex flex-wrap justify-end gap-3"><Button type="button" variant="secondary" disabled={pending} onClick={onCancel}>Cancel</Button><Button type="submit" disabled={pending}>{pending ? 'Saving…' : submitLabel}</Button></div></form>;
}

export function requiredId(id: string | undefined, entity: string): string {
  if (!id) throw new Error(`${entity} route requires an identifier.`);
  return id;
}

export function formString(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === 'string' ? value.trim() : '';
}

export function formOptional(data: FormData, name: string): string | undefined {
  const value = formString(data, name);
  return value || undefined;
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(isJsonValue);
  return isJsonObject(value);
}

function isJsonObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.values(value).every(isJsonValue);
}

export function parseJsonObject(data: FormData, name: string): JsonObject {
  const raw = formString(data, name) || '{}';
  const parsed: unknown = JSON.parse(raw);
  if (!isJsonObject(parsed)) throw new Error(`${name} must be a finite JSON object.`);
  return parsed;
}
