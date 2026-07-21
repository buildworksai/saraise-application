import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Edit3, Send, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { BackgroundProgress, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, StatusPill, createIdempotencyKey, formatDateTime, formatDuration } from '../components/ModuleUi';

// Lifecycle-specific controls remain explicit so forbidden transitions are never rendered.
// eslint-disable-next-line complexity
export const DRRunbookDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const query = useQuery({ queryKey: ['bdr','runbook',id], queryFn: () => id ? backupDisasterRecoveryService.getRunbook(id) : Promise.reject(new Error('Runbook not found')), enabled: Boolean(id) });
  const stepsQuery = useQuery({ queryKey: ['bdr','runbook-steps',id], queryFn: () => id ? backupDisasterRecoveryService.listRunbookSteps(id) : Promise.reject(new Error('Runbook not found')), enabled: Boolean(id) });
  const publish = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.publishRunbook(id, { transition_key: createIdempotencyKey('publish') }) : Promise.reject(new Error('Runbook not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','runbook',id] }); } });
  const retire = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.retireRunbook(id, { transition_key: createIdempotencyKey('retire') }) : Promise.reject(new Error('Runbook not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','runbook',id] }); } });
  const clone = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.cloneRunbook(id) : Promise.reject(new Error('Runbook not found')), onSuccess: (draft) => navigate(`${MODULE_PATHS.runbooks}/${draft.id}/edit`) });
  const remove = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.deleteRunbook(id) : Promise.reject(new Error('Runbook not found')), onSuccess: () => navigate(MODULE_PATHS.runbooks) });
  if (query.isLoading || stepsQuery.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (stepsQuery.error) return <ModuleErrorState error={stepsQuery.error} onRetry={() => { void stepsQuery.refetch(); }} />;
  const book = query.data;
  if (!book) return <PageSkeleton />;
  const steps = stepsQuery.data?.items ?? [];
  const pending = publish.isPending || retire.isPending || clone.isPending || remove.isPending;
  const mutationError = [publish.error, retire.error, clone.error, remove.error].find((error) => error instanceof Error);
  return <PageShell><BackgroundProgress active={query.isFetching || stepsQuery.isFetching || pending} /><PageHeader title={`${book.name} · v${book.version}`} description={book.description || 'No description provided.'} parentLabel="DR runbooks" parentPath={MODULE_PATHS.runbooks} actions={<><StatusPill status={book.status} />{book.status === 'draft' ? <><Button variant="outline" onClick={() => navigate(`${MODULE_PATHS.runbooks}/${book.id}/edit`)}><Edit3 className="mr-2 h-4 w-4" />Edit steps</Button><Button disabled={pending || steps.length === 0} onClick={() => publish.mutate()}><Send className="mr-2 h-4 w-4" />Publish</Button></> : null}{book.status === 'published' ? <><Button variant="outline" disabled={pending} onClick={() => clone.mutate()}><Copy className="mr-2 h-4 w-4" />Clone draft</Button><Button variant="outline" disabled={pending} onClick={() => retire.mutate()}>Retire</Button></> : null}</>} />
    <MutationError error={mutationError instanceof Error ? mutationError : null} />
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">{[['Scope',`${book.scope_type}: ${book.scope_ref}`],['RPO target',formatDuration(book.rpo_target_seconds)],['RTO target',formatDuration(book.rto_target_seconds)],['Last updated',formatDateTime(book.updated_at)]].map(([label,value]) => <Card key={label}><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{label}</CardTitle></CardHeader><CardContent className="font-semibold">{value}</CardContent></Card>)}</section>
    <Card><CardHeader><CardTitle>Recovery sequence</CardTitle></CardHeader><CardContent>{steps.length ? <ol className="space-y-3">{steps.map((step) => <li key={step.id} className="grid grid-cols-[2.5rem_1fr_auto] items-start gap-3 rounded-lg border p-4"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{step.position}</span><div><p className="font-medium">{step.name}</p><p className="text-sm text-muted-foreground">{step.description}</p></div><StatusPill status={step.action_type} /></li>)}</ol> : <p className="text-sm text-muted-foreground">This draft has no active steps. Add at least one validated step before publishing.</p>}</CardContent></Card>
    {book.status === 'draft' ? <Card className="border-destructive/30"><CardHeader><CardTitle>Delete draft</CardTitle></CardHeader><CardContent>{confirmDelete ? <div role="alert" className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><p className="text-sm">Soft-delete this draft and its active editing surface? Published evidence is unaffected.</p><div className="flex gap-2"><Button variant="outline" onClick={() => setConfirmDelete(false)}>Keep draft</Button><Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>{remove.isPending ? 'Deleting…' : 'Confirm delete'}</Button></div></div> : <Button variant="outline" onClick={() => setConfirmDelete(true)}><Trash2 className="mr-2 h-4 w-4" />Delete draft</Button>}</CardContent></Card> : null}
  </PageShell>;
};
