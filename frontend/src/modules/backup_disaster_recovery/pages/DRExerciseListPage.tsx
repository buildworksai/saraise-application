import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, TestTube2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { ExerciseStatus } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, DomainEmptyState, MODULE_PATHS, ModuleErrorState, PageHeader, PageShell, PageSkeleton, ResponsiveTable, StatusPill, formatDateTime, formatDuration, inputClass } from '../components/ModuleUi';

export const DRExerciseListPage = () => {
  const navigate = useNavigate();
  const [status,setStatus] = useState<ExerciseStatus | ''>('');
  const query = useQuery({ queryKey: ['bdr','exercises',status], queryFn: () => backupDisasterRecoveryService.listExercises({ status: status || undefined }) });
  const configuration = useBackupDisasterRecoveryConfiguration();
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (!configuration.data) return <PageSkeleton />;
  const presentation = configuration.data.document.presentation;
  const exercises = query.data?.items ?? [];
  return <PageShell><BackgroundProgress active={query.isFetching} /><PageHeader title="DR exercises" description="Safe rehearsals that preserve step-by-step evidence and objective measurements." actions={<Button onClick={() => navigate(MODULE_PATHS.exerciseNew)}><Plus className="mr-2 h-4 w-4" />Schedule exercise</Button>} />
    <select aria-label="Filter by exercise status" className={`${inputClass} max-w-xs`} value={status} onChange={(event) => setStatus(event.target.value as ExerciseStatus | '')}><option value="">All statuses</option>{['scheduled','queued','running','passed','failed','cancelled'].map((value) => <option key={value}>{value}</option>)}</select>
    {exercises.length === 0 ? <DomainEmptyState icon={TestTube2} title="No exercises match" description="Schedule an isolated or standby rehearsal against a published runbook to prove recoverability." actionLabel="Schedule exercise" onAction={() => navigate(MODULE_PATHS.exerciseNew)} /> : <ResponsiveTable label="DR exercises" headers={['Exercise','Type','Environment','Status','Scheduled','Observed RTO']}>
      {exercises.map((exercise) => <tr key={exercise.id} className="hover:bg-muted/40"><td className="px-4 py-3"><button className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`)}>{exercise.name}</button></td><td className="px-4 py-3 capitalize">{exercise.exercise_type}</td><td className="px-4 py-3 capitalize">{exercise.environment}</td><td className="px-4 py-3"><StatusPill status={exercise.status} presentation={presentation} /></td><td className="px-4 py-3">{formatDateTime(exercise.scheduled_for)}</td><td className="px-4 py-3">{formatDuration(exercise.observed_rto_seconds, presentation)}</td></tr>)}
    </ResponsiveTable>}
  </PageShell>;
};
