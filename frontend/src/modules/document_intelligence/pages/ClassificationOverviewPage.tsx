import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { ActionDialog } from '../components/ActionDialog';
import { ApiProblem, EmptyPanel, MetricCard, PageHeader, PageSkeleton, Pagination, StaleIndicator, StatusPill } from '../components/ModuleShell';
import { deterministicKey, formatConfidence, useCanManageDocumentIntelligence } from '../components/module-utils';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import { parseClassificationStatus, type DocumentClassificationListItem } from '../contracts';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';

function ClassificationRows({ items, open }: { items: readonly DocumentClassificationListItem[]; open: (id: string) => void }) {
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground"><tr><th className="p-4">Document</th><th className="p-4">Prediction</th><th className="p-4">Confidence</th><th className="p-4">Review</th><th className="p-4">Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} tabIndex={0} className="cursor-pointer border-b focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring hover:bg-muted/40" onClick={() => open(item.id)} onKeyDown={(event) => { if (event.key === 'Enter') open(item.id); }}><td className="p-4 font-mono text-xs">{item.document_id}</td><td className="p-4 font-medium">{item.category ?? 'Awaiting inference'}</td><td className="p-4">{formatConfidence(item.confidence)}</td><td className="p-4"><StatusPill status={item.review_status} /></td><td className="p-4"><StatusPill status={item.status} /></td></tr>)}</tbody></table></div>;
}

// The dashboard intentionally owns coordinated URL filters, polling, and review-state presentation.
// eslint-disable-next-line complexity
export function ClassificationOverviewPage() {
  const navigate = useNavigate();
  const canManage = useCanManageDocumentIntelligence();
  const configuration = useDocumentIntelligenceConfiguration();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const [documentId, setDocumentId] = useState('');
  const [versionId, setVersionId] = useState('');
  const page = Number(params.get('page') ?? '1');
  const status = parseClassificationStatus(params.get('status'));
  const category = params.get('category') ?? undefined;
  const review = params.get('review') === 'true';
  const query = useQuery({ queryKey: ['document-intelligence', 'classifications', page, status, category, review], queryFn: () => documentIntelligenceService.listClassifications({ page, page_size: configuration.data?.document.ui.page_size, status, category, needs_review: review || undefined, ordering: '-created_at' }), enabled: Boolean(configuration.data), refetchInterval: (state) => state.state.data?.items.some((item) => ['queued', 'processing'].includes(item.status)) ? configuration.data?.document.ui.poll_interval_ms : false });
  const create = useMutation({ mutationFn: () => documentIntelligenceService.createClassification({ document_id: documentId.trim(), document_version_id: versionId.trim(), idempotency_key: deterministicKey('classify', documentId, versionId) }), onSuccess: ({ classification }) => navigate(DOCUMENT_INTELLIGENCE_PATHS.CLASSIFICATIONS.DETAIL(classification.id)) });
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error || configuration.error || !query.data || !configuration.data) return <div className="p-4 sm:p-8"><ApiProblem error={query.error ?? configuration.error} onRetry={() => { void query.refetch(); void configuration.refetch(); }} /></div>;
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value === 'all' || !value) next.delete(key); else next.set(key, value); next.set('page', '1'); setParams(next); };
  const active = query.data.items.some((item) => ['queued', 'processing'].includes(item.status));
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Classification and review" description="All inferred categories remain visible. Low-confidence predictions stay in a keyboard-friendly review queue without overwriting original evidence." actions={canManage ? <Button onClick={() => setCreateOpen(true)}><Plus className="mr-2 h-4 w-4" />Classify document</Button> : undefined} /><StaleIndicator updatedAt={query.dataUpdatedAt} active={active} /><section className="grid gap-4 sm:grid-cols-3"><MetricCard label="On this page" value={query.data.items.length} detail="Server-paginated records" /><MetricCard label="Needs review" value={query.data.items.filter((item) => item.needs_review).length} detail="No low-confidence result hidden" /><MetricCard label="Completed" value={query.data.items.filter((item) => item.status === 'completed').length} detail="Validated inference results" /></section><Card className="p-4"><div className="grid gap-3 sm:grid-cols-3"><Select value={status ?? 'all'} onValueChange={(value) => update('status', value)}><SelectTrigger aria-label="Classification status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{['queued', 'processing', 'completed', 'failed', 'cancelled', 'timed_out'].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select><Input aria-label="Category filter" placeholder="Category slug" value={category ?? ''} onChange={(event) => update('category', event.target.value)} /><Button variant={review ? 'primary' : 'outline'} onClick={() => update('review', review ? 'all' : 'true')}>Manual review queue</Button></div></Card>{query.data.items.length === 0 ? <EmptyPanel title="No classifications found" description="No predictions match these server filters." action={canManage ? <Button onClick={() => setCreateOpen(true)}>Classify a DMS version</Button> : undefined} /> : <Card className="overflow-hidden"><ClassificationRows items={query.data.items} open={(id) => navigate(DOCUMENT_INTELLIGENCE_PATHS.CLASSIFICATIONS.DETAIL(id))} /><Pagination value={query.data.pagination} onPage={(next) => update('page', String(next))} /></Card>}<ActionDialog open={createOpen} onOpenChange={setCreateOpen} title="Classify a DMS version" description="The active tenant model will produce immutable prediction and score evidence." confirmLabel="Queue classification" pending={create.isPending} onConfirm={() => create.mutateAsync().then(() => undefined)}><div className="space-y-3"><Input id="classification-document" label="DMS document UUID" required value={documentId} onChange={(event) => setDocumentId(event.target.value)} /><Input id="classification-version" label="Immutable version UUID" required value={versionId} onChange={(event) => setVersionId(event.target.value)} />{create.error && <ApiProblem error={create.error} onRetry={() => create.reset()} inline />}</div></ActionDialog></main>;
}
