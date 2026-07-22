import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit3, Play, XCircle } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, ResourceLookup, StatusPill, createIdempotencyKey, formatDateTime, formatDuration } from '../components/ModuleUi';

// The timeline intentionally renders every governed lifecycle state without collapsing evidence.
// eslint-disable-next-line complexity
export const DRExerciseDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [startKey] = useState(() => createIdempotencyKey('exercise-start'));
  const configuration = useBackupDisasterRecoveryConfiguration();
  const liveExerciseStatuses = configuration.data?.document.polling.active_exercise_statuses ?? [];
  const exerciseQuery = useQuery({ queryKey: ['bdr','exercise',id], queryFn: () => id ? backupDisasterRecoveryService.getExercise(id) : Promise.reject(new Error('Exercise not found')), enabled: Boolean(id), refetchInterval: (state) => liveExerciseStatuses.includes(state.state.data?.status ?? 'cancelled') ? configuration.data?.document.polling.exercise_ms : false });
  const stepsQuery = useQuery({ queryKey: ['bdr','step-executions',id], queryFn: () => id && configuration.data ? backupDisasterRecoveryService.listStepExecutions({ exercise: id, page_size: configuration.data.document.polling.exercise_page_size }) : Promise.reject(new Error('Configuration unavailable')), enabled: Boolean(id && configuration.data), refetchInterval: () => liveExerciseStatuses.includes(exerciseQuery.data?.status ?? 'cancelled') ? configuration.data?.document.polling.exercise_ms : false });
  const start = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.startExercise(id,{ idempotency_key: startKey }) : Promise.reject(new Error('Exercise not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','exercise',id] }); } });
  const cancel = useMutation({ mutationFn: () => id ? backupDisasterRecoveryService.cancelExercise(id,{ transition_key: createIdempotencyKey('exercise-cancel') }) : Promise.reject(new Error('Exercise not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','exercise',id] }); } });
  if (!id) return <ResourceLookup title="Open DR exercise" description="Open a tenant-owned exercise by its UUID." label="Exercise UUID" destination={(value) => `${MODULE_PATHS.exercises}/${value}`} />;
  if (exerciseQuery.isLoading || stepsQuery.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (exerciseQuery.error) return <ModuleErrorState error={exerciseQuery.error} onRetry={() => { void exerciseQuery.refetch(); }} />;
  if (stepsQuery.error) return <ModuleErrorState error={stepsQuery.error} onRetry={() => { void stepsQuery.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  const exercise = exerciseQuery.data;
  if (!exercise || !configuration.data) return <PageSkeleton />;
  const presentation = configuration.data.document.presentation;
  const executions = [...(stepsQuery.data?.items ?? [])].sort((left,right) => left.created_at.localeCompare(right.created_at));
  const mutationError = start.error instanceof Error ? start.error : cancel.error instanceof Error ? cancel.error : null;
  const active = liveExerciseStatuses.includes(exercise.status);
  return <PageShell><BackgroundProgress active={exerciseQuery.isFetching || stepsQuery.isFetching || start.isPending || cancel.isPending} label="Exercise status updating" /><PageHeader title={exercise.name} description={`${exercise.exercise_type} exercise · ${exercise.environment} environment · scheduled ${formatDateTime(exercise.scheduled_for)}`} parentLabel="DR exercises" parentPath={MODULE_PATHS.exercises} actions={<><StatusPill status={exercise.status} presentation={presentation} />{exercise.status === 'scheduled' ? <><Button variant="outline" onClick={() => navigate(`${MODULE_PATHS.exercises}/${exercise.id}/edit`)}><Edit3 className="mr-2 h-4 w-4" />Edit</Button><Button disabled={start.isPending} onClick={() => start.mutate()}><Play className="mr-2 h-4 w-4" />{start.isPending ? 'Starting…' : 'Start exercise'}</Button></> : null}{['scheduled', ...liveExerciseStatuses].includes(exercise.status) ? <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}><XCircle className="mr-2 h-4 w-4" />Cancel</Button> : null}</>} /><MutationError error={mutationError} />
    {active ? <section role="status" aria-live="polite" className="rounded-lg border bg-primary/5 p-4"><p className="font-semibold">Exercise in progress</p><p className="text-sm text-muted-foreground">The execution timeline refresh interval is tenant-configured and polling stops automatically at a terminal status.</p></section> : null}
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[['Observed RPO',formatDuration(exercise.observed_rpo_seconds, presentation)],['Observed RTO',formatDuration(exercise.observed_rto_seconds, presentation)],['RPO result',exercise.rpo_met === null ? 'Pending' : exercise.rpo_met ? 'Met' : 'Breached'],['RTO result',exercise.rto_met === null ? 'Pending' : exercise.rto_met ? 'Met' : 'Breached']].map(([label,value]) => <Card key={label}><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">{label}</CardTitle></CardHeader><CardContent className="font-semibold">{value}</CardContent></Card>)}</section>
    <Card><CardHeader><CardTitle>Step execution timeline</CardTitle></CardHeader><CardContent>{executions.length ? <ol className="relative space-y-4 border-l-2 border-border pl-6">{executions.map((execution) => <li key={execution.id} className="relative rounded-lg border p-4"><span aria-hidden="true" className="absolute -left-[1.95rem] top-4 h-3 w-3 rounded-full border-2 border-background bg-primary" /><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">Step {execution.runbook_step_id.slice(0,8)} · attempt {execution.attempt}</p><StatusPill status={execution.status} presentation={presentation} /></div><p className="mt-1 text-xs text-muted-foreground">{formatDateTime(execution.started_at)} → {formatDateTime(execution.completed_at)}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">Step executions appear here after the exercise begins.</p>}</CardContent></Card>
    {exercise.summary ? <Card><CardHeader><CardTitle>Exercise summary</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm">{exercise.summary}</p></CardContent></Card> : null}
  </PageShell>;
};
