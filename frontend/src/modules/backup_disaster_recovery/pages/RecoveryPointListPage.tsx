import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DatabaseBackup, Plus, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { RecoveryPointStatus } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { BackgroundProgress, DomainEmptyState, MODULE_PATHS, ModuleErrorState, PageHeader, PageShell, PageSkeleton, ResponsiveTable, StatusPill, formatBytes, formatDateTime, inputClass } from '../components/ModuleUi';

export const RecoveryPointListPage = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<RecoveryPointStatus | ''>('');
  const [search, setSearch] = useState('');
  const query = useQuery({ queryKey: ['bdr', 'recovery-points', status, search], queryFn: () => backupDisasterRecoveryService.listRecoveryPoints({ status: status || undefined, search: search || undefined, ordering: '-captured_at' }) });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  const points = query.data?.items ?? [];
  return <PageShell><BackgroundProgress active={query.isFetching} /><PageHeader title="Recovery points" description="Immutable restore sources with provider-confirmed integrity evidence." actions={<Button onClick={() => navigate(MODULE_PATHS.backupNew)}><Plus className="mr-2 h-4 w-4" />Request backup</Button>} />
    <div className="grid gap-3 sm:grid-cols-[1fr_14rem]"><label className="relative"><span className="sr-only">Search recovery points</span><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><input className={`${inputClass} pl-9`} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search job or scope…" /></label><label><span className="sr-only">Filter by status</span><select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value as RecoveryPointStatus | '')}><option value="">All statuses</option>{['discovered','verifying','available','corrupt','expired','deleted'].map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>
    {points.length === 0 ? <DomainEmptyState icon={DatabaseBackup} title="No recovery points match" description="Request a backup to create a recovery point, or clear filters to inspect existing protection evidence." actionLabel="Request backup" onAction={() => navigate(MODULE_PATHS.backupNew)} /> : <ResponsiveTable label="Recovery points" headers={['Scope','Backup type','Status','Captured','Expires','Size']}>
      {points.map((point) => <tr key={point.id} className="cursor-pointer hover:bg-muted/40 focus-within:bg-muted/40"><td className="px-4 py-3"><button className="text-left font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(`${MODULE_PATHS.recoveryPoints}/${point.id}`)}>{point.scope_ref}</button><p className="text-xs text-muted-foreground">{point.scope_type}</p></td><td className="px-4 py-3 capitalize">{point.backup_type}</td><td className="px-4 py-3"><StatusPill status={point.status} /></td><td className="px-4 py-3">{formatDateTime(point.captured_at)}</td><td className="px-4 py-3">{formatDateTime(point.expires_at)}</td><td className="px-4 py-3">{formatBytes(point.size_bytes)}</td></tr>)}
    </ResponsiveTable>}
  </PageShell>;
};
