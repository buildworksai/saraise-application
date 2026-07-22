import { useQuery } from '@tanstack/react-query';
import { Activity, BookOpen, DatabaseBackup, PlayCircle, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, DomainEmptyState, MetricCard, MODULE_PATHS, ModuleErrorState, PageHeader, PageShell, PageSkeleton, StatusPill, formatDateTime } from '../components/ModuleUi';

// Explicit branches keep degraded and partial readiness states independently visible.
// eslint-disable-next-line complexity
export const DisasterRecoveryDashboardPage = () => {
  const navigate = useNavigate();
  const configuration = useBackupDisasterRecoveryConfiguration();
  const query = useQuery({ queryKey: ['bdr', 'readiness'], queryFn: backupDisasterRecoveryService.getReadiness, refetchInterval: configuration.data?.document.polling.dashboard_ms });
  if (query.isLoading || configuration.isLoading) return <PageSkeleton cards={4} />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  const readiness = query.data;
  if (!readiness || !configuration.data) return <PageSkeleton cards={4} />;
  const presentation = configuration.data.document.presentation;
  const empty = !readiness.last_verified_recovery_point && !readiness.latest_passed_exercise;
  return (
    <PageShell>
      <BackgroundProgress active={query.isFetching} />
      <PageHeader
        title="Disaster recovery readiness"
        description="Protect critical operations with verified recovery points, rehearsed runbooks, and measurable recovery objectives."
        actions={<><Button variant="outline" onClick={() => navigate(MODULE_PATHS.backupNew)}><DatabaseBackup className="mr-2 h-4 w-4" />Request backup</Button><Button onClick={() => navigate(MODULE_PATHS.restoreNew)}><RotateCcw className="mr-2 h-4 w-4" />Start restore</Button></>}
      />
      {(readiness.queue_state !== 'operational' || readiness.provider_state !== 'operational') ? (
        <section role="status" className="flex flex-col gap-3 rounded-lg border border-primary/50 bg-primary/5 p-4 text-foreground sm:flex-row sm:items-center sm:justify-between">
          <div><p className="font-semibold">Some recovery operations are degraded</p><p className="text-sm">{readiness.provider_message || 'Queue or storage provider health is below the operational threshold.'}</p></div>
          <div className="flex gap-2"><StatusPill status={readiness.queue_state} presentation={presentation} /><StatusPill status={readiness.provider_state} presentation={presentation} /></div>
        </section>
      ) : null}
      <section aria-label="Recovery objective compliance" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="RPO compliance" value={`${readiness.rpo_compliance_percent.toFixed(1)}%`} hint={`${readiness.current_rpo_breaches} current breaches`} state={readiness.current_rpo_breaches ? 'bad' : 'good'} />
        <MetricCard label="RTO compliance" value={`${readiness.rto_compliance_percent.toFixed(1)}%`} hint={`${readiness.current_rto_breaches} current breaches`} state={readiness.current_rto_breaches ? 'bad' : 'good'} />
        <MetricCard label="Runbooks needing attention" value={String(readiness.stale_runbook_count + readiness.unpublished_runbook_count)} hint={`${readiness.stale_runbook_count} stale · ${readiness.unpublished_runbook_count} unpublished`} state={readiness.stale_runbook_count ? 'warning' : 'good'} />
        <MetricCard label="Provider readiness" value={readiness.provider_state} hint={readiness.provider_message || 'Recovery adapter is responding'} state={readiness.provider_state === 'operational' ? 'good' : 'warning'} />
      </section>
      {empty ? <DomainEmptyState icon={Activity} title="Establish your recovery baseline" description="Request a backup, verify its recovery point, and run your first exercise to begin measuring readiness." actionLabel="Request your first backup" onAction={() => navigate(MODULE_PATHS.backupNew)} /> : (
        <section className="grid gap-4 lg:grid-cols-2">
          <Card><CardHeader><CardTitle>Latest protection</CardTitle></CardHeader><CardContent className="space-y-3">
            {readiness.last_verified_recovery_point ? <><div className="flex items-center justify-between"><span className="font-medium">{readiness.last_verified_recovery_point.scope_ref}</span><StatusPill status={readiness.last_verified_recovery_point.status} presentation={presentation} /></div><p className="text-sm text-muted-foreground">Verified {formatDateTime(readiness.last_verified_recovery_point.verified_at)}</p></> : <p className="text-sm text-muted-foreground">No verified recovery point yet.</p>}
            {readiness.next_scheduled_exercise ? <p className="text-sm">Next exercise: <strong>{readiness.next_scheduled_exercise.name}</strong> · {formatDateTime(readiness.next_scheduled_exercise.scheduled_for)}</p> : <p className="text-sm text-muted-foreground">No exercise is currently scheduled.</p>}
          </CardContent></Card>
          <Card><CardHeader><CardTitle>Recent restoration outcomes</CardTitle></CardHeader><CardContent className="space-y-3">
            {readiness.latest_successful_restore ? <div className="flex items-center justify-between"><div><p className="font-medium">Successful restore</p><p className="text-sm text-muted-foreground">{formatDateTime(readiness.latest_successful_restore.completed_at)}</p></div><StatusPill status="succeeded" presentation={presentation} /></div> : <p className="text-sm text-muted-foreground">No successful restore recorded.</p>}
            {readiness.latest_failed_restore ? <div className="flex items-center justify-between"><div><p className="font-medium">Latest failed restore</p><p className="text-sm text-muted-foreground">{formatDateTime(readiness.latest_failed_restore.completed_at)}</p></div><StatusPill status="failed" presentation={presentation} /></div> : null}
          </CardContent></Card>
        </section>
      )}
      <section aria-label="Recovery workflows" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { title: 'Recovery points', detail: 'Inspect verified restore sources', icon: DatabaseBackup, path: MODULE_PATHS.recoveryPoints },
          { title: 'Runbooks', detail: 'Design controlled recovery sequences', icon: BookOpen, path: MODULE_PATHS.runbooks },
          { title: 'Exercises', detail: 'Rehearse recovery safely', icon: PlayCircle, path: MODULE_PATHS.exercises },
          { title: 'Objectives', detail: 'Measure RPO and RTO outcomes', icon: Activity, path: MODULE_PATHS.objectives },
        ].map(({ title, detail, icon: Icon, path }) => <button key={title} type="button" onClick={() => navigate(path)} className="rounded-xl border bg-card p-5 text-left transition hover:border-primary hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Icon className="h-6 w-6 text-primary" /><span className="mt-3 block font-semibold">{title}</span><span className="mt-1 block text-sm text-muted-foreground">{detail}</span></button>)}
      </section>
    </PageShell>
  );
};
