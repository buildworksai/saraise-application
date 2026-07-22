import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, RefreshCw, Square } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ActionDialog } from '../components/ActionDialog';
import { ApiProblem, PageHeader, PageSkeleton, StaleIndicator, StatusPill } from '../components/ModuleShell';
import { deterministicKey, formatConfidence, useCanManageDocumentIntelligence } from '../components/module-utils';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import type { DocumentExtraction, DocumentExtractionPage } from '../contracts';
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';

const ACTIVE = new Set(['queued', 'processing']);

function SourceEvidence({ extraction }: { extraction: DocumentExtraction }) {
  return <Card className="p-5"><h2 className="font-semibold">Immutable DMS source</h2><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-muted-foreground">Document</dt><dd className="break-all font-mono">{extraction.document_id}</dd></div><div><dt className="text-muted-foreground">Version</dt><dd className="break-all font-mono">{extraction.document_version_id}</dd></div><div><dt className="text-muted-foreground">Pages</dt><dd>{extraction.page_count ?? 'Awaiting provider evidence'}</dd></div></dl><p className="mt-5 rounded-md bg-muted p-3 text-xs text-muted-foreground">Document bytes remain in DMS. This record preserves only validated references and extraction evidence.</p></Card>;
}

function PageResult({ page, tab }: { page: DocumentExtractionPage | undefined; tab: 'text' | 'structured' | 'table' }) {
  if (!page) return <p className="p-6 text-sm text-muted-foreground">Page evidence is not available yet.</p>;
  if (tab === 'text') return <pre className="max-h-[32rem] whitespace-pre-wrap overflow-auto p-5 font-sans text-sm">{page.raw_text || 'No text found on this page.'}</pre>;
  if (tab === 'structured') return <div className="space-y-3 p-5">{page.structured_data.fields.length === 0 ? <p className="text-sm text-muted-foreground">No structured fields returned.</p> : page.structured_data.fields.map((field) => <div key={`${field.key}:${field.page_number}`} className="rounded-md border p-3"><div className="flex justify-between gap-3"><strong>{field.key}</strong><span>{formatConfidence(field.confidence)}</span></div><p className="mt-1 break-words text-sm text-muted-foreground">{Array.isArray(field.normalized_value) ? field.normalized_value.join(', ') : String(field.normalized_value ?? '—')}</p></div>)}</div>;
  return <div className="space-y-4 p-5">{page.table_data.length === 0 ? <p className="text-sm text-muted-foreground">No tables returned.</p> : page.table_data.map((table, index) => <div key={`${table.page_number}:${index}`} className="overflow-x-auto rounded-md border"><table className="w-full text-sm"><caption className="p-3 text-left font-medium">Table {index + 1} · {table.rows} × {table.columns}</caption><tbody>{table.cells.map((cell) => <tr key={`${cell.row}:${cell.column}`}><th className="w-32 border p-2 text-left">R{cell.row} C{cell.column}</th><td className="border p-2">{cell.value}</td><td className="border p-2 text-right">{formatConfidence(cell.confidence)}</td></tr>)}</tbody></table></div>)}</div>;
}

function EvidencePanel({ extraction, pages }: { extraction: DocumentExtraction; pages: readonly DocumentExtractionPage[] }) {
  const [pageNumber, setPageNumber] = useState(1);
  const [tab, setTab] = useState<'text' | 'structured' | 'table'>('text');
  const page = pages.find((candidate) => candidate.page_number === pageNumber);
  const confidence = page?.confidence ?? extraction.confidence;
  return <Card className="overflow-hidden"><div className="border-b p-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Result evidence</h2><label className="text-sm">Page <select className="ml-2 rounded-md border bg-background p-2" value={pageNumber} onChange={(event) => setPageNumber(Number(event.target.value))}>{pages.map((item) => <option key={item.id} value={item.page_number}>{item.page_number} · {formatConfidence(item.confidence)}</option>)}</select></label></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-muted" aria-label={`Page confidence ${formatConfidence(confidence)}`}><div className="h-full bg-primary" style={{ width: confidence === null ? '0%' : formatConfidence(confidence) }} /></div><div className="mt-4 flex gap-1" role="tablist">{(['text', 'structured', 'table'] as const).map((value) => <Button key={value} variant={tab === value ? 'primary' : 'ghost'} size="sm" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{value}</Button>)}</div></div><PageResult page={page} tab={tab} /></Card>;
}

// The page orchestrates the explicit evidence/loading/failure/action state matrix.
// eslint-disable-next-line complexity
export function ExtractionDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canManage = useCanManageDocumentIntelligence();
  const configuration = useDocumentIntelligenceConfiguration();
  const [action, setAction] = useState<'retry' | 'cancel' | null>(null);
  const extraction = useQuery({ queryKey: ['document-intelligence', 'extraction', id], queryFn: () => documentIntelligenceService.getExtraction(id), enabled: Boolean(id) && Boolean(configuration.data), refetchInterval: (state) => state.state.data && ACTIVE.has(state.state.data.status) ? configuration.data?.document.ui.poll_interval_ms : false });
  const pages = useQuery({ queryKey: ['document-intelligence', 'extraction-pages', id], queryFn: () => documentIntelligenceService.listExtractionPages(id), enabled: Boolean(id) && Boolean(configuration.data), refetchInterval: extraction.data && ACTIVE.has(extraction.data.status) ? configuration.data?.document.ui.poll_interval_ms : false });
  const mutation = useMutation<void, Error, 'retry' | 'cancel'>({ mutationFn: async (kind) => { if (kind === 'retry') await documentIntelligenceService.retryExtraction(id, { idempotency_key: deterministicKey('retry-extraction', id, extraction.data?.async_job_id ?? '') }); else await documentIntelligenceService.cancelExtraction(id, { reason: 'Cancelled by operator' }); }, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['document-intelligence', 'extraction', id] }); } });
  if (extraction.isLoading || pages.isLoading || configuration.isLoading) return <PageSkeleton cards={2} />;
  if (extraction.error || configuration.error || !extraction.data || !configuration.data) return <div className="p-4 sm:p-8"><ApiProblem error={extraction.error ?? configuration.error} onRetry={() => { void extraction.refetch(); void configuration.refetch(); }} /></div>;
  const isActive = ACTIVE.has(extraction.data.status);
  const act = action ? () => mutation.mutateAsync(action).then(() => undefined) : () => Promise.resolve();
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Extraction evidence" description="Provider-neutral, immutable output with source version and page-level confidence." actions={<><Button variant="ghost" onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.EXTRACTIONS.LIST)}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>{canManage && ['failed', 'timed_out'].includes(extraction.data.status) && <Button variant="outline" onClick={() => setAction('retry')}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>}{canManage && isActive && <Button variant="danger" onClick={() => setAction('cancel')}><Square className="mr-2 h-4 w-4" />Cancel</Button>}</>} /><div className="flex flex-wrap items-center gap-3"><StatusPill status={extraction.data.status} /><StaleIndicator updatedAt={extraction.dataUpdatedAt} active={isActive} /></div>{mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()} inline />}<section className="grid gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]"><SourceEvidence extraction={extraction.data} />{pages.error ? <ApiProblem error={pages.error} onRetry={() => { void pages.refetch(); }} inline /> : <EvidencePanel extraction={extraction.data} pages={pages.data?.items ?? []} />}</section><Card className="p-5"><h2 className="font-semibold">Processing evidence</h2><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-muted-foreground">Engine</dt><dd>{extraction.data.engine}</dd></div><div><dt className="text-muted-foreground">Template</dt><dd className="break-all font-mono text-xs">{extraction.data.template ?? 'None'}</dd></div><div><dt className="text-muted-foreground">Confidence</dt><dd>{formatConfidence(extraction.data.confidence)}</dd></div><div><dt className="text-muted-foreground">Duration</dt><dd>{extraction.data.processing_time_ms === null ? '—' : `${extraction.data.processing_time_ms} ms`}</dd></div></dl>{extraction.data.failure_code && <p className="mt-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{extraction.data.failure_code}: {extraction.data.failure_message}</p>}</Card><ActionDialog open={action !== null} onOpenChange={(open) => { if (!open) setAction(null); }} title={action === 'cancel' ? 'Cancel extraction?' : 'Retry extraction?'} description={action === 'cancel' ? 'The provider will be cancelled when supported. Stored evidence is retained.' : 'A new durable attempt will be queued; previous failure evidence remains immutable.'} confirmLabel={action === 'cancel' ? 'Cancel extraction' : 'Queue retry'} pending={mutation.isPending} destructive={action === 'cancel'} onConfirm={act} /></main>;
}
