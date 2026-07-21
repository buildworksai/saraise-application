import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ExerciseForm, defaultExerciseValues } from '../components/ExerciseForm';
import { MODULE_PATHS, MutationError, PageHeader, PageShell, createIdempotencyKey } from '../components/ModuleUi';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';

export const DRExerciseCreatePage = () => {
  const navigate = useNavigate();
  const [key] = useState(() => createIdempotencyKey('exercise'));
  const mutation = useMutation({ mutationFn: backupDisasterRecoveryService.createExercise, onSuccess: (exercise) => navigate(`${MODULE_PATHS.exercises}/${exercise.id}`) });
  const error = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Schedule a DR exercise" description="Rehearse a published plan without exposing production workloads." parentLabel="DR exercises" parentPath={MODULE_PATHS.exercises} /><MutationError error={error} /><ExerciseForm initial={defaultExerciseValues()} submitting={mutation.isPending} serverError={error} submitLabel="Schedule exercise" idempotencyKey={key} onCancel={() => navigate(MODULE_PATHS.exercises)} onSubmit={(payload) => mutation.mutate(payload)} /></PageShell>;
};
