/* eslint-disable react-refresh/only-export-components -- the default factory belongs to this form contract. */
import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import type { BDRExerciseConfiguration, DRExerciseCreateRequest, ExerciseEnvironment, ExerciseType } from '../contracts';
import { FormCard, FormField, fieldError, inputClass } from './ModuleUi';

export interface ExerciseFormValues { name: string; runbookId: string; recoveryPointId: string; exerciseType: ExerciseType; environment: ExerciseEnvironment; scheduledFor: string; }

export const defaultExerciseValues = (configuration: BDRExerciseConfiguration): ExerciseFormValues => ({ name: '', runbookId: '', recoveryPointId: '', exerciseType: 'tabletop', environment: 'isolated', scheduledFor: new Date(Date.now() + configuration.default_schedule_offset_ms).toISOString().slice(0,16) });

export const ExerciseForm = ({ initial, submitting, serverError, submitLabel, idempotencyKey, productionEnabled, editMode = false, onCancel, onSubmit }: { initial: ExerciseFormValues; submitting: boolean; serverError: Error | null; submitLabel: string; idempotencyKey: string; productionEnabled: boolean; editMode?: boolean; onCancel: () => void; onSubmit: (payload: DRExerciseCreateRequest) => void }) => {
  const [values, setValues] = useState(initial);
  const [validation, setValidation] = useState('');
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!values.name.trim() || !values.runbookId.trim() || !values.scheduledFor) { setValidation('Name, published runbook, and schedule are required.'); return; }
    const scheduled = new Date(values.scheduledFor);
    if (Number.isNaN(scheduled.valueOf())) { setValidation('Enter a valid schedule date and time.'); return; }
    if (submitting) return;
    onSubmit({ name: values.name.trim(), runbook_id: values.runbookId.trim(), recovery_point_id: values.recoveryPointId.trim() || undefined, exercise_type: values.exerciseType, environment: values.environment, scheduled_for: scheduled.toISOString(), idempotency_key: idempotencyKey });
  };
  const environmentDescription = productionEnabled
    ? 'Exercises may use isolated, standby, or explicitly enabled production environments.'
    : 'Exercises run only in isolated or standby environments; production is disabled by tenant policy.';
  return <FormCard title="Exercise plan" description={environmentDescription} onSubmit={submit} footer={<><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button><Button type="submit" disabled={submitting}>{submitting ? 'Saving exercise…' : submitLabel}</Button></>}>
    {validation ? <p role="alert" className="md:col-span-2 rounded-md bg-destructive/5 p-3 text-sm text-destructive">{validation}</p> : null}
    <FormField id="exercise-name" label="Exercise name" error={fieldError(serverError, 'name')}><input id="exercise-name" className={inputClass} value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} /></FormField>
    <FormField id="scheduled-for" label="Scheduled for" error={fieldError(serverError, 'scheduled_for')}><input id="scheduled-for" type="datetime-local" className={inputClass} value={values.scheduledFor} onChange={(event) => setValues({ ...values, scheduledFor: event.target.value })} /></FormField>
    <FormField id="exercise-runbook" label="Published runbook ID" error={fieldError(serverError, 'runbook_id')}><input id="exercise-runbook" className={inputClass} disabled={editMode} value={values.runbookId} onChange={(event) => setValues({ ...values, runbookId: event.target.value })} /></FormField>
    <FormField id="recovery-point" label="Recovery point ID" hint="Optional. A verified matching point is selected when execution starts."><input id="recovery-point" className={inputClass} value={values.recoveryPointId} onChange={(event) => setValues({ ...values, recoveryPointId: event.target.value })} /></FormField>
    <FormField id="exercise-type" label="Exercise type"><select id="exercise-type" disabled={editMode} className={inputClass} value={values.exerciseType} onChange={(event) => setValues({ ...values, exerciseType: event.target.value as ExerciseType })}><option value="tabletop">Tabletop</option><option value="restore">Restore</option><option value="failover">Failover</option><option value="full">Full</option></select></FormField>
    <FormField id="environment" label="Safe environment"><select id="environment" disabled={editMode} className={inputClass} value={values.environment} onChange={(event) => setValues({ ...values, environment: event.target.value as ExerciseEnvironment })}><option value="isolated">Isolated</option><option value="standby">Standby</option>{productionEnabled || values.environment === 'production' ? <option value="production">Production</option> : null}</select></FormField>
  </FormCard>;
};
