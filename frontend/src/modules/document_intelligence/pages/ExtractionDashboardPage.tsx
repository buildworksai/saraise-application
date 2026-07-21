import { useQuery } from '@tanstack/react-query';
import { FileSearch, Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { ApiProblem, EmptyPanel, MetricCard, PageHeader, PageSkeleton, Pagination, StaleIndicator, StatusPill } from '../components/ModuleShell';
import { formatConfidence, useCanManageDocumentIntelligence } from '../components/module-utils';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import { parseExtractionStatus, type DocumentExtractionListItem, type ExtractionEngine, type ExtractionStatus } from '../contracts';

const ACTIVE = new Set<ExtractionStatus>(['queued', 'processing']);

function ExtractionRows({ items, open }: { items: readonly DocumentExtractionListItem[]; open: (id: string) => void }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground"><tr><th className="p-4">Document</th><th className="p-4">Status</th><th className="p-4">Engine</th><th className="p-4">Confidence</th><th className="p-4">Latency</th><th className="p-4"><span className="sr-only">Open</span></th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className="border-b hover:bg-muted/40"><td className="p-4"><button className="font-mono text-xs font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => open(item.id)}>{item.document_id}</button><p className="mt-1 text-xs text-muted-foreground">{item.extraction_type} · v{item.document_version_id.slice(0, 8)}</p></td><td className="p-4"><StatusPill status={item.status} /></td><td className="p-4">{item.engine}</td><td className="p-4 font-semibold">{formatConfidence(item.confidence)}</td><td className="p-4">{item.processing_time_ms === null ? '—' : `${item.processing_time_ms} ms`}</td><td className="p-4 text-right"><Button variant="ghost" size="sm" onClick={() => open(item.id)}>View evidence</Button></td></tr>)}</tbody></table></div>
  );
}

export function ExtractionDashboardPage() {
  const navigate = useNavigate();
  const canManage = useCanManageDocumentIntelligence();
  const [params, setParams] = useSearchParams();
  const page = Number(params.get('page') ?? '1');
  const status = parseExtractionStatus(params.get('status'));
  const engine: ExtractionEngine | undefined = params.get('engine') ?? undefined;
  const confidence = params.get('confidence') ?? 'all';
  const query = useQuery({
    queryKey: ['document-intelligence', 'extractions', page, status, engine],
    queryFn: () => documentIntelligenceService.listExtractions({ page, page_size: 25, status, engine, confidence_min: confidence === 'all' ? undefined : confidence, ordering: '-created_at' }),
    refetchInterval: (state) => state.state.data?.items.some((item) => ACTIVE.has(item.status)) ? 5_000 : false,
  });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data) return <div className="p-4 sm:p-8"><ApiProblem error={query.error} onRetry={() => { void query.refetch(); }} /></div>;
  const items = query.data.items;
  const completed = items.filter((item) => item.status === 'completed').length;
  const measuredLatency = items.filter((item) => item.processing_time_ms !== null);
  const avgLatency = measuredLatency.length ? `${Math.round(measuredLatency.reduce((sum, item) => sum + (item.processing_time_ms ?? 0), 0) / measuredLatency.length)} ms` : '—';
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value === 'all') next.delete(key); else next.set(key, value); next.set('page', '1'); setParams(next); };
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader title="Extraction evidence" description="Trace OCR and structured extraction outcomes back to immutable DMS versions, providers, pages, and timing evidence." actions={canManage ? <Button onClick={() => navigate('/document-intelligence/extractions/new')}><Plus className="mr-2 h-4 w-4" />New extraction</Button> : undefined} />
      <StaleIndicator updatedAt={query.dataUpdatedAt} active={items.some((item) => ACTIVE.has(item.status))} />
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Current page outcomes"><MetricCard label="Completed" value={completed} detail="Validated outcomes on this page" /><MetricCard label="Needs review" value={items.filter((item) => item.status === 'needs_review').length} detail="Evidence kept visible" /><MetricCard label="Average latency" value={avgLatency} detail="Completed records on this page" /></section>
      <Card className="p-4"><div className="grid gap-3 sm:grid-cols-3"><Select value={status ?? 'all'} onValueChange={(value) => update('status', value)}><SelectTrigger aria-label="Filter by status"><SelectValue placeholder="All statuses" /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{['queued', 'processing', 'completed', 'needs_review', 'failed', 'cancelled', 'timed_out'].map((value) => <SelectItem key={value} value={value}>{value.replaceAll('_', ' ')}</SelectItem>)}</SelectContent></Select><Select value={engine ?? 'all'} onValueChange={(value) => update('engine', value)}><SelectTrigger aria-label="Filter by engine"><SelectValue placeholder="All engines" /></SelectTrigger><SelectContent><SelectItem value="all">All engines</SelectItem>{['tesseract', 'aws_textract', 'azure_form_recognizer', 'google_vision'].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select><Select value={confidence} onValueChange={(value) => update('confidence', value)}><SelectTrigger aria-label="Minimum confidence"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Any confidence</SelectItem><SelectItem value="0.5">50%+</SelectItem><SelectItem value="0.8">80%+</SelectItem><SelectItem value="0.95">95%+</SelectItem></SelectContent></Select></div></Card>
      {items.length === 0 ? <EmptyPanel title="No extraction evidence" description="No extraction records match the selected server filters." action={canManage ? <Button onClick={() => navigate('/document-intelligence/extractions/new')}><FileSearch className="mr-2 h-4 w-4" />Process a document</Button> : undefined} /> : <Card className="overflow-hidden"><ExtractionRows items={items} open={(id) => navigate(`/document-intelligence/extractions/${id}`)} /><Pagination value={query.data.pagination} onPage={(next) => update('page', String(next))} /></Card>}
    </main>
  );
}
