import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, Plus, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { RunbookStatus } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { BackgroundProgress, DomainEmptyState, MODULE_PATHS, ModuleErrorState, PageHeader, PageShell, PageSkeleton, ResponsiveTable, StatusPill, formatDateTime, formatDuration, inputClass } from '../components/ModuleUi';

export const DRRunbookListPage = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<RunbookStatus | ''>('');
  const [search, setSearch] = useState('');
  const query = useQuery({ queryKey: ['bdr','runbooks',status,search], queryFn: () => backupDisasterRecoveryService.listRunbooks({ status: status || undefined, search: search || undefined, ordering: '-updated_at' }) });
  if (query.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  const runbooks = query.data?.items ?? [];
  return <PageShell><BackgroundProgress active={query.isFetching} /><PageHeader title="DR runbooks" description="Versioned recovery plans with governed steps, targets, and failure policies." actions={<Button onClick={() => navigate(MODULE_PATHS.runbookNew)}><Plus className="mr-2 h-4 w-4" />Create runbook</Button>} />
    <div className="grid gap-3 sm:grid-cols-[1fr_14rem]"><label className="relative"><span className="sr-only">Search runbooks</span><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><input className={`${inputClass} pl-9`} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or slug…" /></label><select aria-label="Filter by status" className={inputClass} value={status} onChange={(event) => setStatus(event.target.value as RunbookStatus | '')}><option value="">All statuses</option><option value="draft">Draft</option><option value="published">Published</option><option value="retired">Retired</option></select></div>
    {runbooks.length === 0 ? <DomainEmptyState icon={BookOpen} title="No runbooks match" description="Create a runbook to turn recovery knowledge into a repeatable, measurable operating procedure." actionLabel="Create runbook" onAction={() => navigate(MODULE_PATHS.runbookNew)} /> : <ResponsiveTable label="DR runbooks" headers={['Runbook','Status','Scope','RPO target','RTO target','Updated']}>
      {runbooks.map((book) => <tr key={book.id} className="hover:bg-muted/40"><td className="px-4 py-3"><button className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(`${MODULE_PATHS.runbooks}/${book.id}`)}>{book.name}</button><p className="text-xs text-muted-foreground">{book.slug} · v{book.version}</p></td><td className="px-4 py-3"><StatusPill status={book.status} /></td><td className="px-4 py-3">{book.scope_type}: {book.scope_ref}</td><td className="px-4 py-3">{formatDuration(book.rpo_target_seconds)}</td><td className="px-4 py-3">{formatDuration(book.rto_target_seconds)}</td><td className="px-4 py-3">{formatDateTime(book.updated_at)}</td></tr>)}
    </ResponsiveTable>}
  </PageShell>;
};
