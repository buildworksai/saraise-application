import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, RotateCcw, ShieldCheck } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, ResourceLookup, StatusPill, createIdempotencyKey, formatBytes, formatDateTime } from '../components/ModuleUi';

// Verification, expiry, and immutable evidence states intentionally remain explicit.
// eslint-disable-next-line complexity
export const RecoveryPointDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [verificationKey] = useState(() => createIdempotencyKey('verify'));
  const configuration = useBackupDisasterRecoveryConfiguration();
  const query = useQuery({ queryKey: ['bdr', 'recovery-point', id], queryFn: () => id ? backupDisasterRecoveryService.getRecoveryPoint(id) : Promise.reject(new Error('Recovery point not found')), enabled: Boolean(id), refetchInterval: (state) => state.state.data?.status === 'verifying' ? configuration.data?.document.polling.recovery_point_ms : false });
  const verify = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.verifyRecoveryPoint(id, { idempotency_key: verificationKey }) : Promise.reject(new Error('Recovery point not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'recovery-point', id] }); } });
  const expire = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.expireRecoveryPoint(id, { transition_key: createIdempotencyKey('expire') }) : Promise.reject(new Error('Recovery point not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr', 'recovery-point', id] }); } });
  if (!id) return <ResourceLookup title="Open recovery point" description="Open a tenant-owned recovery point by its UUID." label="Recovery point UUID" destination={(value) => `${MODULE_PATHS.recoveryPoints}/${value}`} />;
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  const point = query.data;
  if (!point || !configuration.data) return <PageSkeleton />;
  const presentation = configuration.data.document.presentation;
  const possibleError = verify.error ?? expire.error;
  const mutationError = possibleError instanceof Error ? possibleError : null;
  return <PageShell><BackgroundProgress active={query.isFetching || verify.isPending || expire.isPending} label="Updating recovery point" /><PageHeader title={point.scope_ref} description={`Recovery point captured ${formatDateTime(point.captured_at)}`} parentLabel="Recovery points" parentPath={MODULE_PATHS.recoveryPoints} actions={<><StatusPill status={point.status} presentation={presentation} />{['discovered','available'].includes(point.status) ? <Button variant="outline" disabled={verify.isPending} onClick={() => verify.mutate()}><ShieldCheck className="mr-2 h-4 w-4" />{verify.isPending ? 'Queuing…' : 'Verify'}</Button> : null}{point.status === 'available' ? <Button onClick={() => navigate(`${MODULE_PATHS.restoreNew}?recovery_point=${point.id}`)}><RotateCcw className="mr-2 h-4 w-4" />Restore</Button> : null}</>} />
    <MutationError error={mutationError} />
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{[
      ['Backup type', point.backup_type], ['Scope', `${point.scope_type}: ${point.scope_ref}`], ['Size', formatBytes(point.size_bytes, presentation)], ['Data cutoff', formatDateTime(point.data_cutoff_at)], ['Verified', formatDateTime(point.verified_at)], ['Expires', formatDateTime(point.expires_at)],
    ].map(([label,value]) => <Card key={label}><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{label}</CardTitle></CardHeader><CardContent className="font-medium capitalize">{value}</CardContent></Card>)}</section>
    <Card><CardHeader><CardTitle>Integrity evidence</CardTitle></CardHeader><CardContent>{point.verification_evidence ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[
      ['Checksum', point.verification_evidence.checksum_valid],['Artifact available',point.verification_evidence.artifact_available],['Encryption metadata',point.verification_evidence.encryption_metadata_valid],['Provider acknowledged',point.verification_evidence.provider_acknowledged],
    ].map(([label,value]) => <div key={String(label)} className="flex items-center gap-2"><CheckCircle2 className={`h-5 w-5 ${value ? 'text-primary' : 'text-destructive'}`} /><span className="text-sm">{label}</span></div>)}</div> : <p className="text-sm text-muted-foreground">Verification evidence has not been recorded yet.</p>}</CardContent></Card>
    {point.status === 'available' && point.expires_at && new Date(point.expires_at) < new Date() ? <Card className="border-primary/50"><CardContent className="flex flex-col justify-between gap-4 pt-6 sm:flex-row sm:items-center"><div><p className="font-semibold">Retention has elapsed</p><p className="text-sm text-muted-foreground">Expire this recovery point to prevent new restores.</p></div><Button variant="outline" disabled={expire.isPending} onClick={() => expire.mutate()}>{expire.isPending ? 'Expiring…' : 'Mark expired'}</Button></CardContent></Card> : null}
  </PageShell>;
};
