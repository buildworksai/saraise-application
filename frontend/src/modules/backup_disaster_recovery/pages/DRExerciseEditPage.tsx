import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ExerciseForm, type ExerciseFormValues } from '../components/ExerciseForm';
import { MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, ResourceLookup, createIdempotencyKey } from '../components/ModuleUi';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';

export const DRExerciseEditPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [key] = useState(() => createIdempotencyKey('exercise-edit'));
  const query = useQuery({ queryKey: ['bdr','exercise',id], queryFn: () => id ? backupDisasterRecoveryService.getExercise(id) : Promise.reject(new Error('Exercise not found')), enabled: Boolean(id) });
  const mutation = useMutation({ mutationFn: (payload: Parameters<typeof backupDisasterRecoveryService.updateExercise>[1]) => id ? backupDisasterRecoveryService.updateExercise(id,payload) : Promise.reject(new Error('Exercise not found')), onSuccess: (exercise) => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`) });
  const configuration = useBackupDisasterRecoveryConfiguration();
  if (!id) return <ResourceLookup title="Edit DR exercise" description="Open an editable tenant-owned scheduled exercise by its UUID." label="Exercise UUID" destination={(value) => `${MODULE_PATHS.exercises}/${value}/edit`} />;
  if (query.isLoading || configuration.isLoading) return <PageSkeleton />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  const exercise = query.data;
  if (!exercise || !configuration.data) return <PageSkeleton />;
  if (exercise.status !== 'scheduled') return <ModuleErrorState error={new Error('Only scheduled exercises can be edited. Execution evidence is immutable.')} onRetry={() => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`)} />;
  const initial: ExerciseFormValues = { name: exercise.name, runbookId: exercise.runbook_id, recoveryPointId: exercise.recovery_point_id ?? '', exerciseType: exercise.exercise_type, environment: exercise.environment, scheduledFor: new Date(exercise.scheduled_for).toISOString().slice(0,16) };
  const error = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title={`Edit ${exercise.name}`} description="Scheduled exercises may change their name, recovery point, or planned time." parentLabel={exercise.name} parentPath={`${MODULE_PATHS.exercises}/${exercise.id}`} /><MutationError error={error} /><ExerciseForm initial={initial} editMode submitting={mutation.isPending} serverError={error} submitLabel="Save schedule" idempotencyKey={key} productionEnabled={configuration.data.document.exercises.production_enabled} onCancel={() => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`)} onSubmit={(payload) => mutation.mutate({ name: payload.name, scheduled_for: payload.scheduled_for, recovery_point_id: payload.recovery_point_id })} /></PageShell>;
};
