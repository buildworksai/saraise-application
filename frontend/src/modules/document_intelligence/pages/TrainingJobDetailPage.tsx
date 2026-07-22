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
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';

// Durable job evidence, polling, retry, and cancellation are intentionally one route-level boundary.
// eslint-disable-next-line complexity
export function TrainingJobDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canManage = useCanManageDocumentIntelligence();
  const configuration = useDocumentIntelligenceConfiguration();
  const [action, setAction] = useState<'retry' | 'cancel' | null>(null);
  const query = useQuery({ queryKey: ['document-intelligence', 'training-job', id], queryFn: () => documentIntelligenceService.getTrainingJob(id), enabled: Boolean(id) && Boolean(configuration.data), refetchInterval: (state) => state.state.data && ['queued', 'training'].includes(state.state.data.status) ? configuration.data?.document.ui.poll_interval_ms : false });
  const mutation = useMutation<void, Error, 'retry' | 'cancel'>({ mutationFn: async (kind) => { if (kind === 'retry') await documentIntelligenceService.retryTrainingJob(id, { idempotency_key: deterministicKey('retry-training', id, query.data?.async_job_id ?? '') }); else await documentIntelligenceService.cancelTrainingJob(id, { reason: 'Cancelled by operator' }); }, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['document-intelligence', 'training-job', id] }); } });
  if (query.isLoading || configuration.isLoading) return <PageSkeleton cards={3} table={false} />;
  if (query.error || configuration.error || !query.data || !configuration.data) return <div className="p-4 sm:p-8"><ApiProblem error={query.error ?? configuration.error} onRetry={() => { void query.refetch(); void configuration.refetch(); }} /></div>;
  const active = ['queued', 'training'].includes(query.data.status);
  const confirm = action ? () => mutation.mutateAsync(action).then(() => undefined) : () => Promise.resolve();
  const categoryCounts = Object.entries(query.data.category_counts);
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={query.data.name} description={`Durable training evidence for requested model ${query.data.requested_version}.`} actions={<><Button variant="ghost" onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TRAINING.LIST)}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>{canManage && ['failed', 'timed_out'].includes(query.data.status) && <Button variant="outline" onClick={() => setAction('retry')}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button>}{canManage && active && <Button variant="danger" onClick={() => setAction('cancel')}><Square className="mr-2 h-4 w-4" />Cancel</Button>}</>} /><div className="flex flex-wrap items-center gap-3"><StatusPill status={query.data.status} /><StaleIndicator updatedAt={query.dataUpdatedAt} active={active} /></div>{mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()} inline />}<section className="grid gap-4 sm:grid-cols-3"><Card className="p-5"><p className="text-sm text-muted-foreground">Training examples</p><p className="mt-2 text-3xl font-bold">{query.data.training_data_count}</p></Card><Card className="p-5"><p className="text-sm text-muted-foreground">Categories</p><p className="mt-2 text-3xl font-bold">{categoryCounts.length}</p></Card><Card className="p-5"><p className="text-sm text-muted-foreground">Measured accuracy</p><p className="mt-2 text-3xl font-bold">{formatConfidence(query.data.accuracy)}</p></Card></section><div className="grid gap-4 lg:grid-cols-2"><Card className="p-5"><h2 className="font-semibold">Category distribution</h2><div className="mt-4 space-y-3">{categoryCounts.map(([category, count]) => <div key={category}><div className="flex justify-between text-sm"><span>{category}</span><strong>{count}</strong></div><div className="mt-1 h-2 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${(count / query.data.training_data_count) * 100}%` }} /></div></div>)}</div></Card><Card className="p-5"><h2 className="font-semibold">Durable job transitions</h2><ol className="mt-4 space-y-3">{query.data.job.transitions.map((transition) => <li key={transition.id} className="border-l-2 border-primary pl-4 text-sm"><div className="flex flex-wrap justify-between gap-2"><span><strong>{transition.from_status || 'created'}</strong> → <strong>{transition.to_status}</strong></span><time className="text-xs text-muted-foreground">{new Date(transition.created_at).toLocaleString()}</time></div><p className="mt-1 text-muted-foreground">{transition.reason || 'No reason recorded'}</p></li>)}</ol><p className="mt-4 font-mono text-xs text-muted-foreground">Job {query.data.job.id} · {query.data.job.attempts} attempt(s)</p></Card></div>{query.data.failure_code && <Card className="border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" role="alert">{query.data.failure_code}: {query.data.failure_message}</Card>}<ActionDialog open={action !== null} onOpenChange={(open) => { if (!open) setAction(null); }} title={action === 'cancel' ? 'Cancel training?' : 'Retry training?'} description="The state transition is guarded and previous training evidence remains retained." confirmLabel={action === 'cancel' ? 'Cancel training' : 'Queue retry'} pending={mutation.isPending} destructive={action === 'cancel'} onConfirm={confirm} /></main>;
}
