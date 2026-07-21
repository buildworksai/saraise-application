/* eslint-disable react-refresh/only-export-components -- blank values are part of this form contract. */
import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import type { DRRunbookCreateRequest, ScopeType } from '../contracts';
import { FormCard, FormField, fieldError, inputClass, textareaClass } from './ModuleUi';

export interface RunbookFormValues {
  name: string;
  slug: string;
  description: string;
  scopeType: ScopeType;
  scopeRef: string;
  backupScheduleId: string;
  rpoTargetSeconds: string;
  rtoTargetSeconds: string;
}

export const blankRunbookValues: RunbookFormValues = { name: '', slug: '', description: '', scopeType: 'tenant', scopeRef: 'tenant', backupScheduleId: '', rpoTargetSeconds: '3600', rtoTargetSeconds: '14400' };

export const RunbookForm = ({ initial, submitting, serverError, submitLabel, onCancel, onSubmit }: { initial: RunbookFormValues; submitting: boolean; serverError: Error | null; submitLabel: string; onCancel: () => void; onSubmit: (payload: DRRunbookCreateRequest) => void }) => {
  const [values, setValues] = useState(initial);
  const [validation, setValidation] = useState('');
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!values.name.trim() || !values.slug.trim() || !values.scopeRef.trim()) { setValidation('Name, slug, and scope reference are required.'); return; }
    const rpo = Number(values.rpoTargetSeconds);
    const rto = Number(values.rtoTargetSeconds);
    if (!Number.isInteger(rpo) || rpo <= 0 || !Number.isInteger(rto) || rto <= 0) { setValidation('RPO and RTO targets must be whole seconds greater than zero.'); return; }
    if (submitting) return;
    onSubmit({ name: values.name.trim(), slug: values.slug.trim().toLowerCase(), description: values.description.trim(), scope_type: values.scopeType, scope_ref: values.scopeRef.trim(), backup_schedule_id: values.backupScheduleId.trim() || undefined, rpo_target_seconds: rpo, rto_target_seconds: rto });
  };
  return <FormCard title="Runbook definition" description="Targets are frozen when published; clone a version before changing a published plan." onSubmit={submit} footer={<><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button><Button type="submit" disabled={submitting}>{submitting ? 'Saving runbook…' : submitLabel}</Button></>}>
    {validation ? <div role="alert" className="md:col-span-2 rounded-md bg-destructive/5 p-3 text-sm text-destructive">{validation}</div> : null}
    <FormField id="name" label="Name" error={fieldError(serverError, 'name')}><input id="name" className={inputClass} value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} /></FormField>
    <FormField id="slug" label="Slug" error={fieldError(serverError, 'slug')} hint="Lowercase tenant-local identifier."><input id="slug" className={inputClass} value={values.slug} pattern="[a-z0-9-]+" onChange={(event) => setValues({ ...values, slug: event.target.value })} /></FormField>
    <div className="md:col-span-2"><FormField id="description" label="Operator description"><textarea id="description" className={textareaClass} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} /></FormField></div>
    <FormField id="scope-type" label="Scope type"><select id="scope-type" className={inputClass} value={values.scopeType} onChange={(event) => setValues({ ...values, scopeType: event.target.value as ScopeType })}><option value="tenant">Tenant</option><option value="module">Module</option><option value="database">Database</option><option value="files">Files</option></select></FormField>
    <FormField id="scope-ref" label="Scope reference" error={fieldError(serverError, 'scope_ref')}><input id="scope-ref" className={inputClass} value={values.scopeRef} onChange={(event) => setValues({ ...values, scopeRef: event.target.value })} /></FormField>
    <FormField id="schedule" label="Backup schedule ID" hint="Optional schedule validated through the backup catalog."><input id="schedule" className={inputClass} value={values.backupScheduleId} onChange={(event) => setValues({ ...values, backupScheduleId: event.target.value })} /></FormField>
    <div />
    <FormField id="rpo" label="RPO target (seconds)" error={fieldError(serverError, 'rpo_target_seconds')}><input id="rpo" type="number" min="1" step="1" className={inputClass} value={values.rpoTargetSeconds} onChange={(event) => setValues({ ...values, rpoTargetSeconds: event.target.value })} /></FormField>
    <FormField id="rto" label="RTO target (seconds)" error={fieldError(serverError, 'rto_target_seconds')}><input id="rto" type="number" min="1" step="1" className={inputClass} value={values.rtoTargetSeconds} onChange={(event) => setValues({ ...values, rtoTargetSeconds: event.target.value })} /></FormField>
  </FormCard>;
};
