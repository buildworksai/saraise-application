import { useDeferredValue, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, Copy, DatabaseZap, Play, Plus, Search, TestTube2, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { DataMigrationApiError, dataMigrationService } from '../services/data-migration-service';
import type { JobFilters, MigrationJob, SourceType } from '../contracts';
import { EmptyPanel, FailureState, PageShell, PageSkeleton, StateBadge } from '../components/MigrationUI';

function key(): string { return crypto.randomUUID(); }
function can(job: MigrationJob, action: NonNullable<MigrationJob['allowed_actions']>[number]): boolean { return job.allowed_actions?.includes(action) ?? false; }

export const DataMigrationListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<JobFilters['status']>();
  const [sourceType, setSourceType] = useState<SourceType>();
  const [ordering, setOrdering] = useState<JobFilters['ordering']>('-updated_at');
  const filters: JobFilters = { page, page_size: 25, search: deferredSearch || undefined, status, source_type: sourceType, ordering };

  const query = useQuery({
    queryKey: ['data-migration', 'jobs', filters],
    queryFn: () => dataMigrationService.jobs.list(filters),
    placeholderData: keepPreviousData,
    refetchInterval: ({ state }) => document.visibilityState === 'visible' && state.data?.items.some((job) => job.latest_run?.status === 'queued' || job.latest_run?.status === 'running') ? 5000 : false,
  });

  const remove = useMutation({ mutationFn: dataMigrationService.jobs.delete, onSuccess: async () => { toast.success('Migration definition deleted'); await queryClient.invalidateQueries({ queryKey: ['data-migration', 'jobs'] }); }, onError: () => toast.error('The migration definition could not be deleted.') });
  const archive = useMutation({ mutationFn: (id: string) => dataMigrationService.jobs.archive(id, key()), onSuccess: async () => { toast.success('Migration definition archived'); await queryClient.invalidateQueries({ queryKey: ['data-migration', 'jobs'] }); }, onError: () => toast.error('The migration definition could not be archived.') });
  const start = useMutation({ mutationFn: ({ job, dry }: { job: MigrationJob; dry: boolean }) => dry ? dataMigrationService.runs.dryRun(job.id, { idempotency_key: key() }) : dataMigrationService.runs.start(job.id, { idempotency_key: key() }), onSuccess: (run) => { toast.success(run.mode === 'dry_run' ? 'Dry run accepted' : 'Migration run accepted'); navigate(`/data-migration/runs/${run.id}`); }, onError: () => toast.error('The run was not accepted. Review readiness and quota, then retry.') });

  const clone = async (job: MigrationJob) => {
    try {
      const document = await dataMigrationService.jobs.export(job.id);
      const preview = await dataMigrationService.jobs.import({ document: { ...document, job: { ...document.job, name: `${document.job.name} copy` } }, preview_only: false });
      if (!preview.job) throw new Error('Import returned no durable definition.');
      toast.success('Migration definition cloned'); navigate(`/data-migration/jobs/${preview.job.id}/edit`);
    } catch { toast.error('The migration definition could not be cloned.'); }
  };

  if (query.isLoading) return <PageSkeleton label="Loading migration definitions" />;
  if (query.error) return <PageShell title="Data migration" description="Safe, durable imports with traceable dry runs and conflict-aware rollback."><FailureState forbidden={query.error instanceof DataMigrationApiError && query.error.status === 403} message={query.error instanceof Error ? query.error.message : 'The server did not return migration definitions.'} onRetry={() => { void query.refetch(); }} /></PageShell>;

  const jobs = query.data?.items ?? [];
  return <PageShell title="Data migration" description="Inspect, map, validate, dry run, and commit tenant data with durable evidence." actions={<><Button variant="outline" onClick={() => navigate('/data-migration/settings/connections')}>Connections</Button><Button onClick={() => navigate('/data-migration/jobs/new')}><Plus className="mr-2 h-4 w-4" />New migration</Button></>}>
    <Card className="grid gap-3 p-4 md:grid-cols-[minmax(14rem,1fr)_repeat(3,minmax(9rem,auto))]" aria-label="Migration filters">
      <label className="relative"><span className="sr-only">Search migrations</span><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input className="pl-9" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search migration definitions" /></label>
      <label><span className="sr-only">Filter by status</span><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={status ?? ''} onChange={(event) => { setStatus((event.target.value || undefined) as JobFilters['status']); setPage(1); }}><option value="">All statuses</option><option value="draft">Draft</option><option value="ready">Ready</option><option value="archived">Archived</option></select></label>
      <label><span className="sr-only">Filter by source type</span><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={sourceType ?? ''} onChange={(event) => { setSourceType((event.target.value || undefined) as SourceType | undefined); setPage(1); }}><option value="">All sources</option>{(['csv','excel','json','xml','database','api'] as const).map((type) => <option key={type} value={type}>{type.toUpperCase()}</option>)}</select></label>
      <label><span className="sr-only">Sort migrations</span><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={ordering} onChange={(event) => setOrdering(event.target.value as JobFilters['ordering'])}><option value="-updated_at">Recently active</option><option value="name">Name A–Z</option><option value="-created_at">Newest first</option></select></label>
    </Card>

    {jobs.length === 0 ? <EmptyPanel title={search || status || sourceType ? 'No migrations match these filters' : 'No migration definitions yet'} description={search || status || sourceType ? 'Clear or adjust the server-side filters.' : 'The guided workflow will help you reach a safe dry run without needing documentation.'} action={!search && !status && !sourceType ? { label: 'Start guided migration', onClick: () => navigate('/data-migration/jobs/new') } : undefined} /> : <div className="space-y-3" aria-live="polite">
      {jobs.map((job) => <Card key={job.id} className="p-5"><div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <button className="min-w-0 text-left" onClick={() => navigate(`/data-migration/jobs/${job.id}`)}><div className="flex flex-wrap items-center gap-2"><h2 className="truncate text-lg font-semibold text-foreground">{job.name}</h2><StateBadge state={job.status} />{job.readiness.ready ? <span className="text-xs text-primary">Ready</span> : <span className="text-xs text-destructive">{job.readiness.blockers.length} blocker{job.readiness.blockers.length === 1 ? '' : 's'}</span>}</div><p className="mt-1 text-sm text-muted-foreground">{job.source_type.toUpperCase()} → {job.target_adapter} / {job.target_entity} · v{job.configuration_version}</p><p className="mt-1 text-xs text-muted-foreground">Last activity {new Date(job.updated_at).toLocaleString()}{job.latest_run ? ` · latest ${job.latest_run.mode.replace('_', ' ')} ${job.latest_run.status}` : ''}</p></button>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => navigate(`/data-migration/jobs/${job.id}`)}>Open</Button>
          {can(job, 'export') ? <Button size="sm" variant="outline" onClick={() => { void clone(job); }}><Copy className="mr-1 h-4 w-4" />Clone</Button> : null}
          {can(job, 'dry_run') ? <Button size="sm" variant="outline" disabled={start.isPending} onClick={() => { if (window.confirm(`Start a dry run for ${job.name}? No target records will be written.`)) start.mutate({ job, dry: true }); }}><TestTube2 className="mr-1 h-4 w-4" />Dry run</Button> : null}
          {can(job, 'run') ? <Button size="sm" disabled={start.isPending} onClick={() => { if (window.confirm(`Commit ${job.name} using configuration v${job.configuration_version}? Target writes may require conflict-safe rollback.`)) start.mutate({ job, dry: false }); }}><Play className="mr-1 h-4 w-4" />Run</Button> : null}
          {can(job, 'archive') ? <Button size="icon" variant="ghost" aria-label={`Archive ${job.name}`} onClick={() => archive.mutate(job.id)}><Archive className="h-4 w-4" /></Button> : null}
          {can(job, 'delete') ? <Button size="icon" variant="ghost" aria-label={`Delete ${job.name}`} onClick={() => { if (window.confirm(`Delete ${job.name}? Historical runs remain immutable.`)) remove.mutate(job.id); }}><Trash2 className="h-4 w-4" /></Button> : null}
        </div>
      </div></Card>)}
    </div>}
    {query.data && query.data.pagination.total_pages > 1 ? <nav className="flex items-center justify-between" aria-label="Migration pages"><Button variant="outline" disabled={!query.data.pagination.has_previous || query.isFetching} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</Button><span className="text-sm text-muted-foreground">Page {query.data.pagination.page} of {query.data.pagination.total_pages}</span><Button variant="outline" disabled={!query.data.pagination.has_next || query.isFetching} onClick={() => setPage((value) => value + 1)}>Next</Button></nav> : null}
  </PageShell>;
};
