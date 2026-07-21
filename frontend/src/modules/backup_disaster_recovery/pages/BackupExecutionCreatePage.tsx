import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import type { BackupType, ScopeType } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { FormCard, FormField, MODULE_PATHS, MutationError, PageHeader, PageShell, createIdempotencyKey, fieldError, inputClass } from '../components/ModuleUi';

export const BackupExecutionCreatePage = () => {
  const navigate = useNavigate();
  const [scopeType, setScopeType] = useState<ScopeType>('tenant');
  const [scopeRef, setScopeRef] = useState('tenant');
  const [backupType, setBackupType] = useState<BackupType>('full');
  const [validation, setValidation] = useState('');
  const [idempotencyKey] = useState(() => createIdempotencyKey('backup'));
  const mutation = useMutation({
    mutationFn: backupDisasterRecoveryService.requestBackup,
    onSuccess: (receipt) => navigate(`${MODULE_PATHS.recoveryPoints}?backup_job_id=${receipt.backup_job_id}`),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!scopeRef.trim()) { setValidation('Enter the canonical scope reference.'); return; }
    if (mutation.isPending) return;
    mutation.mutate({ backup_type: backupType, scope_type: scopeType, scope_ref: scopeRef.trim(), idempotency_key: idempotencyKey });
  };
  const mutationError = mutation.error instanceof Error ? mutation.error : null;
  return <PageShell><PageHeader title="Request a backup" description="Capture a protected artifact through the registered backup catalog. The request continues as a durable background job." parentLabel="Overview" parentPath={MODULE_PATHS.overview} />
    <MutationError error={mutationError} />
    <FormCard title="Backup scope" description="Choose the smallest canonical scope that meets your recovery objective." onSubmit={submit} footer={<><Button type="button" variant="outline" onClick={() => navigate(MODULE_PATHS.overview)}>Cancel</Button><Button type="submit" disabled={mutation.isPending} aria-disabled={mutation.isPending}>{mutation.isPending ? 'Queuing backup…' : 'Queue backup'}</Button></>}>
      <FormField id="scope-type" label="Scope type"><select id="scope-type" className={inputClass} value={scopeType} onChange={(event) => setScopeType(event.target.value as ScopeType)}><option value="tenant">Tenant</option><option value="module">Module</option><option value="database">Database</option><option value="files">Files</option></select></FormField>
      <FormField id="backup-type" label="Backup type"><select id="backup-type" className={inputClass} value={backupType} onChange={(event) => setBackupType(event.target.value as BackupType)}><option value="full">Full</option><option value="incremental">Incremental</option><option value="differential">Differential</option></select></FormField>
      <div className="md:col-span-2"><FormField id="scope-ref" label="Canonical scope reference" error={validation || fieldError(mutationError, 'scope_ref')} hint="Use a registered logical identifier—never a credential, file URL, or connection string."><input id="scope-ref" className={inputClass} value={scopeRef} aria-describedby="scope-ref-hint scope-ref-error" aria-invalid={Boolean(validation)} onChange={(event) => { setScopeRef(event.target.value); setValidation(''); }} /></FormField></div>
    </FormCard>
    <p aria-live="polite" className="sr-only">{mutation.isPending ? 'Backup submission in progress' : ''}</p>
  </PageShell>;
};
