import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { RefreshCw, Search } from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { DeliveryFilters, DeliveryStatus } from '../contracts';
import { ROUTE_PATHS } from '../contracts';
import {
  BackgroundRefresh, Definition, DefinitionGrid, EmptyPanel, EvidenceCard, formatDate,
  GovernedError, newOperationKey, PageHeader, PageSkeleton, Pagination, RedactedJsonViewer,
  StatusBadge, SuccessEvidence, useCanManageIntegrations,
} from '../components/IntegrationPlatformUI';
import { integrationPlatformService as service } from '../services/integration-platform-service';

function positive(value: string | null): number {
  const parsed = Number(value ?? '1');
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

// eslint-disable-next-line complexity
export function DeliveryListPage() {
  const [params, setParams] = useSearchParams();
  const filters: DeliveryFilters = {
    page: positive(params.get('page')), page_size: 25,
    webhook_id: params.get('webhook') ?? undefined,
    status: (params.get('status') ?? undefined) as DeliveryStatus | undefined,
    event: params.get('event') ?? undefined, created_after: params.get('after') ?? undefined,
    created_before: params.get('before') ?? undefined,
  };
  const query = useQuery({
    queryKey: ['integration-platform', 'deliveries', params.toString()],
    queryFn: () => service.listDeliveries(filters), placeholderData: keepPreviousData, refetchInterval: 10000,
  });
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'page') next.set('page', '1');
    setParams(next);
  };
  if (query.isLoading) return <PageSkeleton label="Loading webhook deliveries" />;
  if (query.error || !query.data) return <main className="p-4 sm:p-8"><GovernedError error={query.error} retry={() => { void query.refetch(); }} /></main>;
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title="Webhook Deliveries" description="Append-only operational evidence, retries, timings, correlation, and dead-letter recovery." />
    <BackgroundRefresh active={query.isFetching && !query.isLoading} />
    <Card className="p-4"><form role="search" className="grid gap-3 lg:grid-cols-6" onSubmit={(event) => {
      event.preventDefault(); const value = new FormData(event.currentTarget).get('event');
      update('event', typeof value === 'string' ? value.trim() : '');
    }}>
      <Input name="event" aria-label="Filter delivery event" defaultValue={params.get('event') ?? ''} placeholder="Event name" />
      <Input aria-label="Filter webhook ID" value={params.get('webhook') ?? ''} onChange={(event) => update('webhook', event.target.value)} placeholder="Webhook ID" />
      <select aria-label="Filter delivery status" className="rounded-md border bg-background px-3 py-2" value={params.get('status') ?? ''} onChange={(event) => update('status', event.target.value)}><option value="">All statuses</option>{['queued', 'delivering', 'retrying', 'delivered', 'dead_letter', 'cancelled'].map((status) => <option key={status}>{status}</option>)}</select>
      <Input aria-label="Created after" type="datetime-local" value={params.get('after') ?? ''} onChange={(event) => update('after', event.target.value)} />
      <Input aria-label="Created before" type="datetime-local" value={params.get('before') ?? ''} onChange={(event) => update('before', event.target.value)} />
      <Button type="submit" variant="secondary"><Search className="mr-2 h-4 w-4" />Apply</Button>
    </form></Card>
    {query.data.items.length === 0
      ? <EmptyPanel filtered={params.toString().length > 0} title="deliveries" description="Delivery evidence appears only after a real webhook event is durably queued." reset={() => setParams(new URLSearchParams())} />
      : <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/50"><tr><th className="p-4">Event</th><th className="p-4">Webhook</th><th className="p-4">Status</th><th className="p-4">Attempts</th><th className="p-4">Response</th><th className="p-4">Duration</th><th className="p-4">Created</th></tr></thead><tbody>{query.data.items.map((delivery) => <tr key={delivery.id} className="border-b"><td className="p-4"><Link className="font-semibold text-primary" to={ROUTE_PATHS.DELIVERY_DETAIL(delivery.id)}>{delivery.event}</Link><p className="font-mono text-xs text-muted-foreground">{delivery.correlation_id}</p></td><td className="p-4">{delivery.webhook_name}</td><td className="p-4"><StatusBadge status={delivery.status} /></td><td className="p-4">{delivery.attempt_count}/{delivery.max_attempts}</td><td className="p-4">{delivery.response_code ?? (delivery.error_code || '—')}</td><td className="p-4">{delivery.duration_ms === null ? '—' : `${delivery.duration_ms} ms`}</td><td className="p-4">{formatDate(delivery.created_at)}</td></tr>)}</tbody></table></div><Pagination meta={query.data.meta} changePage={(page) => update('page', String(page))} /></Card>}
  </main>;
}

export function DeliveryDetailPage() {
  const id = useParams().id;
  if (!id) throw new Error('Delivery route requires an identifier.');
  const canManage = useCanManageIntegrations();
  const query = useQuery({
    queryKey: ['integration-platform', 'delivery', id], queryFn: () => service.getDelivery(id),
    refetchInterval: (state) => ['queued', 'delivering', 'retrying'].includes(state.state.data?.status ?? '') ? 5000 : false,
  });
  const redrive = useMutation({
    mutationFn: () => service.redriveDelivery(id, { transition_key: newOperationKey('redrive') }),
    onSuccess: (receipt) => { toast.success('Delivery redrive queued.', { description: `Correlation ${receipt.correlation_id}` }); void query.refetch(); },
    onError: (failure: Error) => toast.error(failure.message),
  });
  if (query.isLoading) return <PageSkeleton label="Loading delivery evidence" />;
  if (query.error || !query.data) return <main className="p-4 sm:p-8"><GovernedError error={query.error} retry={() => { void query.refetch(); }} /></main>;
  const delivery = query.data;
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title={delivery.event} description="Immutable webhook delivery evidence." backTo={{ label: 'Deliveries', path: ROUTE_PATHS.DELIVERIES }} actions={canManage ? <Button disabled={delivery.status !== 'dead_letter' || redrive.isPending} onClick={() => redrive.mutate()}><RefreshCw className="mr-2 h-4 w-4" />{redrive.isPending ? 'Queuing…' : 'Redrive'}</Button> : undefined} />
    {redrive.data && <SuccessEvidence title="Redrive accepted" correlationId={redrive.data.correlation_id} detail={`Durable job ${redrive.data.job_id}`} />}
    <EvidenceCard title="Delivery lifecycle"><DefinitionGrid><Definition label="Status"><StatusBadge status={delivery.status} /></Definition><Definition label="Attempt">{delivery.attempt_count} of {delivery.max_attempts}</Definition><Definition label="Next attempt">{formatDate(delivery.next_attempt_at)}</Definition><Definition label="Response code">{delivery.response_code ?? '—'}</Definition><Definition label="Duration">{delivery.duration_ms === null ? '—' : `${delivery.duration_ms} ms`}</Definition><Definition label="Delivered">{formatDate(delivery.delivered_at)}</Definition></DefinitionGrid></EvidenceCard>
    <EvidenceCard title="Traceability"><DefinitionGrid><Definition label="Correlation ID"><span className="font-mono text-xs">{delivery.correlation_id}</span></Definition><Definition label="Job ID"><span className="font-mono text-xs">{delivery.job_id}</span></Definition><Definition label="Idempotency key"><span className="font-mono text-xs">{delivery.idempotency_key}</span></Definition><Definition label="Payload SHA-256"><span className="font-mono text-xs">{delivery.payload_hash}</span></Definition><Definition label="Created">{formatDate(delivery.created_at)}</Definition><Definition label="Updated">{formatDate(delivery.updated_at)}</Definition></DefinitionGrid></EvidenceCard>
    {delivery.error_code && <EvidenceCard title="Failure evidence"><DefinitionGrid><Definition label="Error code">{delivery.error_code}</Definition><Definition label="Error message">{delivery.error_message}</Definition></DefinitionGrid></EvidenceCard>}
    <div className="grid gap-6 lg:grid-cols-2"><EvidenceCard title="Redacted payload"><RedactedJsonViewer label="Payload" value={delivery.payload} /></EvidenceCard><EvidenceCard title="Redacted provider response"><pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-4 text-xs">{delivery.response_body_excerpt || 'No response evidence.'}</pre><p className="mt-2 text-xs text-muted-foreground">Stored excerpts are bounded and redacted before persistence.</p></EvidenceCard></div>
    <EvidenceCard title="Transition history"><ol className="space-y-3">{delivery.transition_history.map((transition) => <li key={transition.transition_key} className="rounded-lg border p-3 text-sm"><strong>{transition.transition}</strong> · {transition.from_status} → {transition.to_status}<span className="float-right text-xs text-muted-foreground">{formatDate(transition.occurred_at)}</span></li>)}</ol></EvidenceCard>
  </main>;
}
