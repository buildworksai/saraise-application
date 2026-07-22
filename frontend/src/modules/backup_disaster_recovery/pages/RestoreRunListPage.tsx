import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { RestoreRunStatus } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, DomainEmptyState, MODULE_PATHS, ModuleErrorState, PageHeader, PageShell, PageSkeleton, ResponsiveTable, StatusPill, formatDateTime, formatDuration, inputClass } from '../components/ModuleUi';

export const RestoreRunListPage = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<RestoreRunStatus | ''>('');
  const query = useQuery({ queryKey: ['bdr', 'restore-runs', status], queryFn: () => backupDisasterRecoveryService.listRestoreRuns({ status: status || undefined }) });
  const configuration = useBackupDisasterRecoveryConfiguration();
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (!configuration.data) return <PageSkeleton />;
  const presentation = configuration.data.document.presentation;
  const runs = query.data?.items ?? [];
  return <PageShell><BackgroundProgress active={query.isFetching} /><PageHeader title="Restore runs" description="Governed validation, execution, and post-restore evidence for every recovery operation." actions={<Button onClick={() => navigate(MODULE_PATHS.restoreNew)}><Plus className="mr-2 h-4 w-4" />Plan restore</Button>} />
    <label className="block max-w-xs"><span className="sr-only">Filter by status</span><select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value as RestoreRunStatus | '')}><option value="">All statuses</option>{['queued','validating','ready','restoring','verifying','succeeded','failed','cancelled'].map((value) => <option key={value}>{value}</option>)}</select></label>
    {runs.length === 0 ? <DomainEmptyState icon={RotateCcw} title="No restore runs match" description="Plan a restore from an available recovery point. Every run is validated before provider execution begins." actionLabel="Plan a restore" onAction={() => navigate(MODULE_PATHS.restoreNew)} /> : <ResponsiveTable label="Restore runs" headers={['Target','Environment','Status','Requested','RPO','RTO']}>
      {runs.map((run) => <tr key={run.id} className="hover:bg-muted/40"><td className="px-4 py-3"><button onClick={() => navigate(`${MODULE_PATHS.restores}/${run.id}`)} className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{run.target_ref}</button><p className="text-xs capitalize text-muted-foreground">{run.restore_mode} restore</p></td><td className="px-4 py-3 capitalize">{run.target_environment}</td><td className="px-4 py-3"><StatusPill status={run.status} presentation={presentation} /></td><td className="px-4 py-3">{formatDateTime(run.requested_at)}</td><td className="px-4 py-3">{formatDuration(run.achieved_rpo_seconds, presentation)}</td><td className="px-4 py-3">{formatDuration(run.achieved_rto_seconds, presentation)}</td></tr>)}
    </ResponsiveTable>}
  </PageShell>;
};
