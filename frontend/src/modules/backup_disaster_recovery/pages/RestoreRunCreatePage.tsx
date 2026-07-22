import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { RestoreMode, RestoreTargetEnvironment } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { FormCard, FormField, MODULE_PATHS, MutationError, PageHeader, PageShell, createIdempotencyKey, fieldError, inputClass } from '../components/ModuleUi';

interface RestoreValidation { recoveryPoint?: string; targetRef?: string; components?: string; }

export const RestoreRunCreatePage = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [recoveryPoint, setRecoveryPoint] = useState(params.get('recovery_point') ?? '');
  const [environment, setEnvironment] = useState<RestoreTargetEnvironment>('isolated');
  const [targetRef, setTargetRef] = useState('');
  const [mode, setMode] = useState<RestoreMode>('full');
  const [components, setComponents] = useState('');
  const [validation, setValidation] = useState<RestoreValidation>({});
  const [idempotencyKey] = useState(() => createIdempotencyKey('restore'));
  const mutation = useMutation({ mutationFn: backupDisasterRecoveryService.createRestoreRun, onSuccess: (run) => navigate(`${MODULE_PATHS.restores}/${run.id}`) });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next: RestoreValidation = {};
    if (!recoveryPoint.trim()) next.recoveryPoint = 'Select or paste an available recovery point ID.';
    if (!targetRef.trim()) next.targetRef = 'Enter a registered target reference.';
    if (mode === 'selective' && !components.trim()) next.components = 'Enter at least one component for a selective restore.';
    setValidation(next);
    if (Object.values(next).some(Boolean) || mutation.isPending) return;
    mutation.mutate({ recovery_point_id: recoveryPoint.trim(), target_environment: environment, target_ref: targetRef.trim(), restore_mode: mode, selected_components: mode === 'selective' ? components.split(',').map((value) => value.trim()).filter(Boolean) : [], idempotency_key: idempotencyKey });
  };
  const mutationError = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Plan a restore" description="Validate integrity, compatibility, capacity, and target conflicts before restoration begins." parentLabel="Restore runs" parentPath={MODULE_PATHS.restores} /><MutationError error={mutationError} />
    <FormCard title="Restore plan" description="Production restore is unavailable until the step-up verification integration is operational." onSubmit={submit} footer={<><Button type="button" variant="outline" onClick={() => navigate(MODULE_PATHS.restores)}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? 'Creating validation job…' : 'Validate restore'}</Button></>}>
      <FormField id="recovery-point" label="Recovery point ID" error={validation.recoveryPoint ?? fieldError(mutationError, 'recovery_point_id')}><input id="recovery-point" className={inputClass} value={recoveryPoint} onChange={(event) => setRecoveryPoint(event.target.value)} /></FormField>
      <FormField id="target-environment" label="Target environment" hint="Production is disabled because step-up verification is not available."><select id="target-environment" className={inputClass} value={environment} onChange={(event) => setEnvironment(event.target.value as RestoreTargetEnvironment)}><option value="isolated">Isolated</option><option value="standby">Standby</option><option value="production" disabled>Production (unavailable)</option></select></FormField>
      <FormField id="target-ref" label="Registered target reference" error={validation.targetRef ?? fieldError(mutationError, 'target_ref')} hint="Logical target only; URLs and credentials are rejected."><input id="target-ref" className={inputClass} value={targetRef} onChange={(event) => setTargetRef(event.target.value)} /></FormField>
      <FormField id="restore-mode" label="Restore mode"><select id="restore-mode" className={inputClass} value={mode} onChange={(event) => setMode(event.target.value as RestoreMode)}><option value="full">Full</option><option value="selective">Selective</option></select></FormField>
      {mode === 'selective' ? <div className="md:col-span-2"><FormField id="components" label="Components" error={validation.components} hint="Comma-separated canonical component names."><input id="components" className={inputClass} value={components} onChange={(event) => setComponents(event.target.value)} /></FormField></div> : null}
    </FormCard><p className="sr-only" aria-live="polite">{mutation.isPending ? 'Restore validation submission in progress' : ''}</p>
  </PageShell>;
};
