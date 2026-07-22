import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, XCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, ResourceLookup, StatusPill, createIdempotencyKey, formatDateTime, formatDuration } from '../components/ModuleUi';

// Controls and evidence vary by lifecycle state and are kept explicit for safety.
// eslint-disable-next-line complexity
export const RestoreRunDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [executionKey] = useState(() => createIdempotencyKey('restore-execute'));
  const configuration = useBackupDisasterRecoveryConfiguration();
  const activeStatuses = configuration.data?.document.polling.active_restore_statuses ?? [];
  const query = useQuery({ queryKey: ['bdr', 'restore-run', id], queryFn: () => id ? backupDisasterRecoveryService.getRestoreRun(id) : Promise.reject(new Error('Restore run not found')), enabled: Boolean(id), refetchInterval: (state) => activeStatuses.includes(state.state.data?.status ?? 'cancelled') ? configuration.data?.document.polling.restore_ms : false });
  const execute = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.executeRestoreRun(id, { idempotency_key: executionKey }) : Promise.reject(new Error('Restore run not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'restore-run', id] }); } });
  const cancel = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.cancelRestoreRun(id, { transition_key: createIdempotencyKey('restore-cancel') }) : Promise.reject(new Error('Restore run not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'restore-run', id] }); } });
  if (!id) return <ResourceLookup title="Open restore run" description="Open a tenant-owned restore run by its UUID." label="Restore run UUID" destination={(value) => `${MODULE_PATHS.restores}/${value}`} />;
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  const run = query.data;
  if (!run || !configuration.data) return <PageSkeleton />;
  const presentation = configuration.data.document.presentation;
  const mutationError = execute.error instanceof Error ? execute.error : cancel.error instanceof Error ? cancel.error : null;
  const cancellable = ['queued','validating','ready'].includes(run.status);
  return <PageShell><BackgroundProgress active={query.isFetching || execute.isPending || cancel.isPending} label="Restore status updating" /><PageHeader title={`Restore to ${run.target_ref}`} description={`Requested ${formatDateTime(run.requested_at)} · ${run.target_environment} environment`} parentLabel="Restore runs" parentPath={MODULE_PATHS.restores} actions={<><StatusPill status={run.status} presentation={presentation} />{run.status === 'ready' ? <Button disabled={execute.isPending} onClick={() => execute.mutate()}><Play className="mr-2 h-4 w-4" />{execute.isPending ? 'Starting…' : 'Execute restore'}</Button> : null}{cancellable ? <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}><XCircle className="mr-2 h-4 w-4" />Cancel</Button> : null}</>} /><MutationError error={mutationError} />
    {activeStatuses.includes(run.status) ? <div role="status" className="rounded-lg border bg-primary/5 p-4 text-sm"><strong>Background operation in progress.</strong> This page refreshes automatically; it is safe to navigate away.</div> : null}
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">{[['Mode',run.restore_mode],['Environment',run.target_environment],['Achieved RPO',formatDuration(run.achieved_rpo_seconds, presentation)],['Achieved RTO',formatDuration(run.achieved_rto_seconds, presentation)]].map(([label,value]) => <Card key={label}><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{label}</CardTitle></CardHeader><CardContent className="font-semibold capitalize">{value}</CardContent></Card>)}</section>
    <Card><CardHeader><CardTitle>Governed restore evidence</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">Provider validation, operation identifiers, and raw verification payloads are restricted to authorized operators and are not returned by this public API. This view exposes only the governed lifecycle outcome.</p></CardContent></Card>
    {run.status === 'failed' ? <section role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-4"><p className="font-semibold">Restore failed</p><p className="mt-1 text-sm">Review the narrowly authorized evidence endpoint or contact an administrator with the request correlation ID.</p></section> : null}
  </PageShell>;
};
