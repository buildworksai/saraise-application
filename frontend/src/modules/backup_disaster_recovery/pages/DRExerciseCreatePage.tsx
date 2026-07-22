import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ExerciseForm, defaultExerciseValues } from '../components/ExerciseForm';
import { MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, createIdempotencyKey } from '../components/ModuleUi';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';

export const DRExerciseCreatePage = () => {
  const navigate = useNavigate();
  const [key] = useState(() => createIdempotencyKey('exercise'));
  const mutation = useMutation({ mutationFn: backupDisasterRecoveryService.createExercise, onSuccess: (exercise) => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`) });
  const configuration = useBackupDisasterRecoveryConfiguration();
  if (configuration.isLoading) return <PageSkeleton />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (!configuration.data) return <PageSkeleton />;
  const error = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Schedule a DR exercise" description="Rehearse a published plan under the tenant's configured environment policy." parentLabel="DR exercises" parentPath={MODULE_PATHS.exercises} /><MutationError error={error} /><ExerciseForm initial={defaultExerciseValues(configuration.data.document.exercises)} submitting={mutation.isPending} serverError={error} submitLabel="Schedule exercise" idempotencyKey={key} productionEnabled={configuration.data.document.exercises.production_enabled} onCancel={() => navigate(MODULE_PATHS.exercises)} onSubmit={(payload) => mutation.mutate(payload)} /></PageShell>;
};
