import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Play, XCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { BackgroundProgress, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, StatusPill, createIdempotencyKey, formatDateTime, formatDuration } from '../components/ModuleUi';

const activeStatuses = ['queued', 'validating', 'restoring', 'verifying'];

// Controls and evidence vary by lifecycle state and are kept explicit for safety.
// eslint-disable-next-line complexity
export const RestoreRunDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [executionKey] = useState(() => createIdempotencyKey('restore-execute'));
  const query = useQuery({ queryKey: ['bdr', 'restore-run', id], queryFn: () => id ? backupDisasterRecoveryService.getRestoreRun(id) : Promise.reject(new Error('Restore run not found')), enabled: Boolean(id), refetchInterval: (state) => activeStatuses.includes(state.state.data?.status ?? '') ? 4_000 : false });
  const execute = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.executeRestoreRun(id, { idempotency_key: executionKey }) : Promise.reject(new Error('Restore run not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'restore-run', id] }); } });
  const cancel = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.cancelRestoreRun(id, { transition_key: createIdempotencyKey('restore-cancel') }) : Promise.reject(new Error('Restore run not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'restore-run', id] }); } });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  const run = query.data;
  if (!run) return <PageSkeleton />;
  const mutationError = execute.error instanceof Error ? execute.error : cancel.error instanceof Error ? cancel.error : null;
  const cancellable = ['queued','validating','ready'].includes(run.status);
  return <PageShell><BackgroundProgress active={query.isFetching || execute.isPending || cancel.isPending} label="Restore status updating" /><PageHeader title={`Restore to ${run.target_ref}`} description={`Requested ${formatDateTime(run.requested_at)} · ${run.target_environment} environment`} parentLabel="Restore runs" parentPath={MODULE_PATHS.restores} actions={<><StatusPill status={run.status} />{run.status === 'ready' ? <Button disabled={execute.isPending} onClick={() => execute.mutate()}><Play className="mr-2 h-4 w-4" />{execute.isPending ? 'Starting…' : 'Execute restore'}</Button> : null}{cancellable ? <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}><XCircle className="mr-2 h-4 w-4" />Cancel</Button> : null}</>} /><MutationError error={mutationError} />
    {activeStatuses.includes(run.status) ? <div role="status" className="rounded-lg border bg-primary/5 p-4 text-sm"><strong>Background operation in progress.</strong> This page refreshes automatically; it is safe to navigate away.</div> : null}
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">{[['Mode',run.restore_mode],['Environment',run.target_environment],['Achieved RPO',formatDuration(run.achieved_rpo_seconds)],['Achieved RTO',formatDuration(run.achieved_rto_seconds)]].map(([label,value]) => <Card key={label}><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{label}</CardTitle></CardHeader><CardContent className="font-semibold capitalize">{value}</CardContent></Card>)}</section>
    <section className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle>Pre-restore validation</CardTitle></CardHeader><CardContent>{run.validation_evidence ? <ul className="space-y-2">{[['Artifact integrity',run.validation_evidence.artifact_valid],['Target registration',run.validation_evidence.target_registered],['Capacity',run.validation_evidence.capacity_available],['Compatibility',run.validation_evidence.compatible],['No target conflict',run.validation_evidence.conflict_free]].map(([label,valid]) => <li key={String(label)} className="flex items-center gap-2 text-sm"><CheckCircle2 className={`h-4 w-4 ${valid ? 'text-emerald-600' : 'text-destructive'}`} />{label}</li>)}</ul> : <p className="text-sm text-muted-foreground">Validation evidence is pending.</p>}</CardContent></Card>
      <Card><CardHeader><CardTitle>Post-restore verification</CardTitle></CardHeader><CardContent>{run.verification_evidence ? <><div className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-emerald-600" /><span className="font-medium">Integrity verified</span></div><p className="mt-2 text-sm text-muted-foreground">Components: {run.verification_evidence.components_verified.join(', ') || 'Full target'}</p></> : <p className="text-sm text-muted-foreground">Verification evidence is recorded only after provider execution.</p>}</CardContent></Card></section>
    {run.status === 'failed' ? <section role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-4"><p className="font-semibold">Restore failed: {run.error_code}</p><p className="mt-1 text-sm">{run.error_message}</p></section> : null}
  </PageShell>;
};
