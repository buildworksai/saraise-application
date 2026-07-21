import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import type { RunbookActionType, RunbookStepCreateRequest, RunbookStepParameters } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { RunbookForm, type RunbookFormValues } from '../components/RunbookForm';
import { BackgroundProgress, FormField, MODULE_PATHS, ModuleErrorState, MutationError, PageHeader, PageShell, PageSkeleton, StatusPill, inputClass, textareaClass } from '../components/ModuleUi';

const buildParameters = (action: RunbookActionType, target: string, detail: string): RunbookStepParameters => {
  switch (action) {
    case 'validate_recovery_point': return { action_type: action, require_checksum: true, require_encryption: true };
    case 'restore': return { action_type: action, restore_mode: detail.trim() ? 'selective' : 'full', selected_components: detail.split(',').map((value) => value.trim()).filter(Boolean) };
    case 'verify': return { action_type: action, checks: ['connectivity', 'integrity', 'application', 'security'] };
    case 'failover': return { action_type: action, target_ref: target.trim() };
    case 'failback': return { action_type: action, target_ref: target.trim() };
    case 'manual_approval': return { action_type: action, instructions: detail.trim() };
    case 'notify': return { action_type: action, channel_ref: target.trim(), message_template: detail.trim() };
    case 'extension': return { action_type: action, configuration_ref: detail.trim() };
  }
};

// The builder exposes each discriminated action schema and lifecycle state explicitly.
// eslint-disable-next-line complexity
export const DRRunbookEditPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stepName, setStepName] = useState('');
  const [stepKey, setStepKey] = useState('');
  const [description, setDescription] = useState('');
  const [action, setAction] = useState<RunbookActionType>('validate_recovery_point');
  const [target, setTarget] = useState('');
  const [detail, setDetail] = useState('');
  const [stepValidation, setStepValidation] = useState('');
  const [deleteStepId, setDeleteStepId] = useState<string | null>(null);
  const bookQuery = useQuery({ queryKey: ['bdr','runbook',id], queryFn: () => id ? backupDisasterRecoveryService.getRunbook(id) : Promise.reject(new Error('Runbook not found')), enabled: Boolean(id) });
  const stepsQuery = useQuery({ queryKey: ['bdr','runbook-steps',id], queryFn: () => id ? backupDisasterRecoveryService.listRunbookSteps(id) : Promise.reject(new Error('Runbook not found')), enabled: Boolean(id) });
  const update = useMutation({ mutationFn: (payload: Parameters<typeof backupDisasterRecoveryService.updateRunbook>[1]) => id ? backupDisasterRecoveryService.updateRunbook(id, payload) : Promise.reject(new Error('Runbook not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','runbook',id] }); } });
  const createStep = useMutation({ mutationFn: backupDisasterRecoveryService.createRunbookStep, onSuccess: () => { setStepName(''); setStepKey(''); setDescription(''); setTarget(''); setDetail(''); void queryClient.invalidateQueries({ queryKey: ['bdr','runbook-steps',id] }); } });
  const reorder = useMutation({ mutationFn: (stepIds: readonly string[]) => id ? backupDisasterRecoveryService.reorderRunbookSteps(id, { step_ids: stepIds }) : Promise.reject(new Error('Runbook not found')), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['bdr','runbook-steps',id] }); } });
  const remove = useMutation({ mutationFn: backupDisasterRecoveryService.deleteRunbookStep, onSuccess: () => { setDeleteStepId(null); void queryClient.invalidateQueries({ queryKey: ['bdr','runbook-steps',id] }); } });
  if (bookQuery.isLoading || stepsQuery.isLoading) return <PageSkeleton />;
  if (bookQuery.error) return <ModuleErrorState error={bookQuery.error} onRetry={() => { void bookQuery.refetch(); }} />;
  if (stepsQuery.error) return <ModuleErrorState error={stepsQuery.error} onRetry={() => { void stepsQuery.refetch(); }} />;
  const book = bookQuery.data;
  if (!book) return <PageSkeleton />;
  if (book.status !== 'draft') return <ModuleErrorState error={new Error('Published and retired runbooks are immutable. Clone this version to create an editable draft.')} onRetry={() => navigate(`${MODULE_PATHS.runbooks}/${book.id}`)} />;
  const steps = [...(stepsQuery.data?.items ?? [])].sort((left, right) => left.position - right.position);
  const initial: RunbookFormValues = { name: book.name, slug: book.slug, description: book.description, scopeType: book.scope_type, scopeRef: book.scope_ref, backupScheduleId: book.backup_schedule_id ?? '', rpoTargetSeconds: String(book.rpo_target_seconds), rtoTargetSeconds: String(book.rto_target_seconds) };
  const addStep = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!stepName.trim() || !stepKey.trim()) { setStepValidation('Step name and stable key are required.'); return; }
    if (['restore','failover','failback','manual_approval','notify','extension'].includes(action) && !target.trim()) { setStepValidation('This action requires its target, permission, recipient, or extension key.'); return; }
    const payload: RunbookStepCreateRequest = { runbook_id: book.id, step_key: stepKey.trim().toLowerCase(), position: steps.length + 1, name: stepName.trim(), description: description.trim(), action_type: action, extension_action_key: action === 'extension' ? target.trim() : undefined, approval_permission: action === 'manual_approval' ? target.trim() : undefined, parameters: buildParameters(action, target, detail), timeout_seconds: 3600, retry_limit: 1, on_failure: action === 'notify' ? 'continue_degraded' : 'stop' };
    setStepValidation('');
    if (!createStep.isPending) createStep.mutate(payload);
  };
  const move = (index: number, offset: -1 | 1) => {
    const destination = index + offset;
    if (destination < 0 || destination >= steps.length) return;
    const ids = steps.map((step) => step.id);
    const source = ids[index];
    const targetId = ids[destination];
    if (!source || !targetId) return;
    ids[index] = targetId;
    ids[destination] = source;
    reorder.mutate(ids);
  };
  const mutationError = [update.error, createStep.error, reorder.error, remove.error].find((error) => error instanceof Error);
  return <PageShell><BackgroundProgress active={bookQuery.isFetching || stepsQuery.isFetching || update.isPending || createStep.isPending || reorder.isPending || remove.isPending} label="Saving runbook changes" /><PageHeader title={`Edit ${book.name}`} description="Build a deterministic recovery sequence. Step order is committed atomically." parentLabel={`${book.name} · v${book.version}`} parentPath={`${MODULE_PATHS.runbooks}/${book.id}`} /><MutationError error={mutationError instanceof Error ? mutationError : null} />
    <RunbookForm initial={initial} submitting={update.isPending} serverError={update.error instanceof Error ? update.error : null} submitLabel="Save definition" onCancel={() => navigate(`${MODULE_PATHS.runbooks}/${book.id}`)} onSubmit={(payload) => update.mutate(payload)} />
    <Card><CardHeader><CardTitle>Runbook steps</CardTitle><p className="text-sm text-muted-foreground">Reorder with the labelled controls. Deleted steps are retained as soft-deleted audit records.</p></CardHeader><CardContent className="space-y-3">
      {steps.length ? <ol className="space-y-3">{steps.map((step,index) => <li key={step.id} className="grid gap-3 rounded-lg border p-4 sm:grid-cols-[2.5rem_1fr_auto] sm:items-center"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary font-bold text-primary-foreground">{step.position}</span><div><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{step.name}</p><StatusPill status={step.action_type} /></div><p className="text-sm text-muted-foreground">{step.description || step.step_key}</p></div><div className="flex gap-1"><Button type="button" variant="outline" aria-label={`Move ${step.name} up`} disabled={index === 0 || reorder.isPending} onClick={() => move(index,-1)}><ArrowUp className="h-4 w-4" /></Button><Button type="button" variant="outline" aria-label={`Move ${step.name} down`} disabled={index === steps.length - 1 || reorder.isPending} onClick={() => move(index,1)}><ArrowDown className="h-4 w-4" /></Button><Button type="button" variant="outline" aria-label={`Delete ${step.name}`} onClick={() => setDeleteStepId(step.id)}><Trash2 className="h-4 w-4" /></Button></div>{deleteStepId === step.id ? <div role="alert" className="rounded-md bg-destructive/5 p-3 text-sm sm:col-span-3"><p>Remove <strong>{step.name}</strong> from this draft?</p><div className="mt-2 flex gap-2"><Button size="sm" variant="outline" onClick={() => setDeleteStepId(null)}>Keep</Button><Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(step.id)}>Remove step</Button></div></div> : null}</li>)}</ol> : <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">No steps yet. Add the first recovery action below.</p>}
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Add a step</CardTitle></CardHeader><CardContent><form onSubmit={addStep} className="grid gap-5 md:grid-cols-2">
      {stepValidation ? <p role="alert" className="md:col-span-2 text-sm text-destructive">{stepValidation}</p> : null}
      <FormField id="step-name" label="Step name"><input id="step-name" className={inputClass} value={stepName} onChange={(event) => setStepName(event.target.value)} /></FormField><FormField id="step-key" label="Stable step key"><input id="step-key" className={inputClass} value={stepKey} onChange={(event) => setStepKey(event.target.value)} /></FormField>
      <div className="md:col-span-2"><FormField id="step-description" label="Operator instructions"><textarea id="step-description" className={textareaClass} value={description} onChange={(event) => setDescription(event.target.value)} /></FormField></div>
      <FormField id="action-type" label="Action type"><select id="action-type" className={inputClass} value={action} onChange={(event) => { setAction(event.target.value as RunbookActionType); setTarget(''); setDetail(''); }}>{['validate_recovery_point','restore','verify','failover','failback','manual_approval','notify','extension'].map((value) => <option key={value}>{value}</option>)}</select></FormField>
      {action === 'validate_recovery_point' ? <p className="self-end rounded-md bg-muted p-3 text-sm">Checksum and encryption metadata validation are required.</p> : null}
      {action === 'restore' ? <><FormField id="action-target" label="Registered restore target"><input id="action-target" className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)} /></FormField><FormField id="action-detail" label="Selective components" hint="Leave blank for full restore."><input id="action-detail" className={inputClass} value={detail} onChange={(event) => setDetail(event.target.value)} /></FormField></> : null}
      {action === 'verify' ? <p className="self-end rounded-md bg-muted p-3 text-sm">Integrity, availability, and application health checks are required.</p> : null}
      {action === 'failover' || action === 'failback' ? <FormField id="action-target" label="Registered target"><input id="action-target" className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)} /></FormField> : null}
      {action === 'manual_approval' ? <><FormField id="action-target" label="Approval permission"><input id="action-target" className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)} /></FormField><FormField id="action-detail" label="Approval instructions"><input id="action-detail" className={inputClass} value={detail} onChange={(event) => setDetail(event.target.value)} /></FormField></> : null}
      {action === 'notify' ? <><FormField id="action-target" label="Recipient group"><input id="action-target" className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)} /></FormField><FormField id="action-detail" label="Message template"><input id="action-detail" className={inputClass} value={detail} onChange={(event) => setDetail(event.target.value)} /></FormField></> : null}
      {action === 'extension' ? <><FormField id="action-target" label="Registered extension action"><input id="action-target" className={inputClass} value={target} onChange={(event) => setTarget(event.target.value)} /></FormField><FormField id="action-detail" label="Configuration reference"><input id="action-detail" className={inputClass} value={detail} onChange={(event) => setDetail(event.target.value)} /></FormField></> : null}
      <div className="flex justify-end md:col-span-2"><Button type="submit" disabled={createStep.isPending}><Plus className="mr-2 h-4 w-4" />{createStep.isPending ? 'Adding step…' : 'Add step'}</Button></div>
    </form></CardContent></Card>
    <p aria-live="polite" className="sr-only">{reorder.isPending ? 'Saving new step order' : createStep.isPending ? 'Creating step' : ''}</p>
  </PageShell>;
};
