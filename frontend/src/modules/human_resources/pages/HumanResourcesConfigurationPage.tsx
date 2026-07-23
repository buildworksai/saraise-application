import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, History, RotateCcw, Save, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type {
  ConfigurationWrite, HumanResourcesConfigurationDocument, RuntimeEnvironment,
} from '../contracts';
import { hrKeys } from '../contracts';
import { GovernedError, PageShell, PageSkeleton, StatusChip } from '../components/hr-ui';
import { hrService, newIntentKey } from '../services/hr-service';

const control = 'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm';
const number = (value: string): number => Number(value);
const list = (value: string): string[] => value.split(',').map((item) => item.trim()).filter(Boolean);

function Field({ label, guidance, children }: { label: string; guidance: string; children: React.ReactNode }) {
  return <label className="block text-sm font-medium">{label}{children}<span className="mt-1 block text-xs font-normal text-muted-foreground">{guidance}</span></label>;
}

// eslint-disable-next-line max-lines-per-function, complexity -- this is the single governed configuration workspace.
export function HumanResourcesConfigurationPage() {
  const client = useQueryClient();
  const [environment, setEnvironment] = useState<RuntimeEnvironment>('default');
  const configuration = useQuery({ queryKey: [...hrKeys.configuration, environment], queryFn: () => hrService.getConfiguration(environment) });
  const history = useQuery({ queryKey: [...hrKeys.configurationHistory, environment], queryFn: () => hrService.getConfigurationHistory(environment) });
  const audit = useQuery({ queryKey: [...hrKeys.configurationAudit, environment], queryFn: () => hrService.getConfigurationAudit(environment) });
  const [document, setDocument] = useState<HumanResourcesConfigurationDocument | null>(null);
  const [reason, setReason] = useState('');
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState('');
  const [advancedText, setAdvancedText] = useState('');
  const [advancedError, setAdvancedError] = useState('');
  const [rolloutTarget, setRolloutTarget] = useState<'tenant' | 'role' | 'cohort'>('tenant');

  useEffect(() => {
    if (!configuration.data) return;
    setDocument(configuration.data.data.document);
    setEnvironment(configuration.data.data.environment);
    const rollout = configuration.data.data.document.feature_rollout;
    setRolloutTarget(rollout.roles.length ? 'role' : rollout.cohorts.length ? 'cohort' : 'tenant');
  }, [configuration.data]);
  useEffect(() => {
    if (document) setAdvancedText(JSON.stringify(document, null, 2));
  }, [document]);

  // eslint-disable-next-line complexity -- every dependent safe-limit rule must block saving locally.
  const safeError = useMemo(() => {
    if (!document) return 'Configuration has not loaded.';
    if (document.limits.list_page_size < 1 || document.limits.list_page_size > 100) return 'List page size must be between 1 and 100.';
    if (document.limits.lookup_page_size < 1 || document.limits.lookup_page_size > 100) return 'Lookup page size must be between 1 and 100.';
    if (document.limits.reporting_tree_default_depth < 1 || document.limits.reporting_tree_default_depth > document.limits.reporting_tree_max_depth) return 'Reporting-tree default depth must be within the configured maximum.';
    if (Number(document.limits.leave_input_minimum) < 0) return 'Leave input minimum cannot be negative.';
    if (Number(document.limits.leave_input_step) <= 0) return 'Leave input step must be positive.';
    if (document.feature_rollout.percentage < 0 || document.feature_rollout.percentage > 100) return 'Rollout percentage must be between 0 and 100.';
    if (document.feature_rollout.enabled && rolloutTarget === 'role' && !document.feature_rollout.roles.length) return 'Role rollout requires at least one role.';
    if (document.feature_rollout.enabled && rolloutTarget === 'cohort' && !document.feature_rollout.cohorts.length) return 'Cohort rollout requires at least one cohort.';
    return '';
  }, [document, rolloutTarget]);

  const payload = (): ConfigurationWrite => {
    if (!document) throw new Error('Configuration is unavailable.');
    return { environment, document, change_reason: reason.trim(), idempotency_key: newIntentKey() };
  };
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: hrKeys.configuration }),
      client.invalidateQueries({ queryKey: hrKeys.configurationHistory }),
      client.invalidateQueries({ queryKey: hrKeys.configurationAudit }),
    ]);
  };

  const preview = useMutation({
    mutationFn: () => {
      const request = payload();
      return hrService.previewConfiguration({ environment: request.environment, document: request.document, change_reason: request.change_reason });
    },
  });
  const save = useMutation({
    mutationFn: () => hrService.updateConfiguration(payload()),
    onSuccess: async () => { toast.success('Configuration version saved with audit evidence.'); setReason(''); await refresh(); },
  });
  const rollback = useMutation({
    mutationFn: (version: number) => hrService.rollbackConfiguration({ environment, version, change_reason: reason.trim(), idempotency_key: newIntentKey() }),
    onSuccess: async () => { toast.success('Rollback created a new configuration version.'); setReason(''); await refresh(); },
  });
  const importConfiguration = useMutation({
    mutationFn: (value: HumanResourcesConfigurationDocument) => hrService.importConfiguration({
      environment, document: value, change_reason: reason.trim(), idempotency_key: newIntentKey(),
    }),
    onSuccess: async () => { toast.success('Configuration imported and versioned.'); setImportText(''); setImportError(''); await refresh(); },
  });
  const exportConfiguration = useMutation({
    mutationFn: () => hrService.exportConfiguration(environment),
    onSuccess: (result) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' }));
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = `human-resources-${result.data.environment}-v${result.data.version}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
  });

  if (configuration.isLoading || history.isLoading || audit.isLoading) return <PageSkeleton cards={4} />;
  const queryError = configuration.error ?? history.error ?? audit.error;
  if (queryError || !configuration.data || !history.data || !audit.data || !document) {
    return <PageShell title="Human Resources configuration" description="Tenant-scoped runtime policy."><GovernedError error={queryError} retry={() => { void configuration.refetch(); void history.refetch(); void audit.refetch(); }} resource="Configuration" /></PageShell>;
  }

  const patchLimits = (value: Partial<HumanResourcesConfigurationDocument['limits']>) => setDocument((current) => current ? ({ ...current, limits: { ...current.limits, ...value } }) : current);
  const patchRollout = (value: Partial<HumanResourcesConfigurationDocument['feature_rollout']>) => setDocument((current) => current ? ({ ...current, feature_rollout: { ...current.feature_rollout, ...value } }) : current);
  const mutationError = preview.error ?? save.error ?? rollback.error ?? importConfiguration.error ?? exportConfiguration.error;
  const canMutate = !safeError && Boolean(reason.trim());

  return <PageShell title="Human Resources configuration" description="Versioned tenant policy. Preview every change before applying it; server validation remains authoritative." actions={<><Button variant="outline" disabled={preview.isPending || Boolean(safeError)} onClick={() => preview.mutate()}><Eye className="mr-2 h-4 w-4" />Preview</Button><Button variant="outline" disabled={exportConfiguration.isPending} onClick={() => exportConfiguration.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button><Button disabled={!canMutate || save.isPending} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4" />Save version</Button></>}>
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-6">
        <Card><CardHeader><CardTitle>Runtime limits and defaults</CardTitle></CardHeader><CardContent className="grid gap-5 md:grid-cols-2">
          <Field label="Environment" guidance="Environment changes values, never code paths."><select className={control} value={environment} onChange={(event) => setEnvironment(event.target.value as RuntimeEnvironment)}><option value="default">Default</option><option value="development">Development</option><option value="self-hosted">Self-hosted</option><option value="saas">SaaS</option></select></Field>
          <Field label="List page size" guidance="Bounds standard HR collection requests; server limit is 1–100."><Input type="number" min={1} max={100} value={document.limits.list_page_size} onChange={(event) => patchLimits({ list_page_size: number(event.target.value) })} /></Field>
          <Field label="Lookup page size" guidance="Bounds employee, department, and leave-allocation selectors."><Input type="number" min={1} max={100} value={document.limits.lookup_page_size} onChange={(event) => patchLimits({ lookup_page_size: number(event.target.value) })} /></Field>
          <Field label="Reporting depth" guidance={`Must not exceed the configured maximum of ${document.limits.reporting_tree_max_depth}.`}><Input type="number" min={1} max={document.limits.reporting_tree_max_depth} value={document.limits.reporting_tree_default_depth} onChange={(event) => patchLimits({ reporting_tree_default_depth: number(event.target.value) })} /></Field>
          <Field label="Minimum leave input" guidance={`The server also requires positive mutations of at least ${document.limits.leave_amount_minimum} days.`}><Input type="number" min={0} max={365} step={document.limits.leave_input_step} value={document.limits.leave_input_minimum} onChange={(event) => patchLimits({ leave_input_minimum: event.target.value })} /></Field>
          <Field label="Leave-day increment" guidance="Controls selectable allocation precision and must be positive."><Input type="number" min={0.01} max={365} step={0.01} value={document.limits.leave_input_step} onChange={(event) => patchLimits({ leave_input_step: event.target.value })} /></Field>
          <Field label="Default leave type" guidance="New allocations and requests start with this allowed value."><select className={control} value={document.defaults.leave_type} onChange={(event) => setDocument({ ...document, defaults: { ...document.defaults, leave_type: event.target.value as typeof document.defaults.leave_type } })}>{document.allowed_values.leave_types.map((value) => <option key={value}>{value}</option>)}</select></Field>
        </CardContent></Card>

        <Card><CardHeader><CardTitle>Feature rollout</CardTitle></CardHeader><CardContent className="grid gap-5 md:grid-cols-2">
          <Field label="Capability enabled" guidance="Disabling the flag stops rollout without a deployment."><select className={control} value={document.feature_rollout.enabled ? 'enabled' : 'disabled'} onChange={(event) => patchRollout({ enabled: event.target.value === 'enabled' })}><option value="enabled">Enabled</option><option value="disabled">Disabled</option></select></Field>
          <Field label="Rollout target" guidance="Dependent allow-lists are cleared when targeting changes."><select className={control} disabled={!document.feature_rollout.enabled} value={rolloutTarget} onChange={(event) => { const target = event.target.value as typeof rolloutTarget; setRolloutTarget(target); patchRollout({ roles: [], cohorts: [] }); }}><option value="tenant">Entire tenant</option><option value="role">Selected roles</option><option value="cohort">Selected cohorts</option></select></Field>
          <Field label="Rollout percentage" guidance="A bounded percentage supports phased activation."><Input type="number" min={0} max={100} disabled={!document.feature_rollout.enabled} value={document.feature_rollout.percentage} onChange={(event) => patchRollout({ percentage: number(event.target.value) })} /></Field>
          <Field label="Roles" guidance="Comma-separated allow-list; required only for role targeting."><Input disabled={!document.feature_rollout.enabled || rolloutTarget !== 'role'} value={document.feature_rollout.roles.join(', ')} onChange={(event) => patchRollout({ roles: list(event.target.value) })} /></Field>
          <Field label="Cohorts" guidance="Comma-separated allow-list; required only for cohort targeting."><Input disabled={!document.feature_rollout.enabled || rolloutTarget !== 'cohort'} value={document.feature_rollout.cohorts.join(', ')} onChange={(event) => patchRollout({ cohorts: list(event.target.value) })} /></Field>
        </CardContent></Card>

        <Card><CardHeader><CardTitle>Advanced governed document</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-muted-foreground">Edit every allowed value, default, policy, workflow, visual token, and operational control. Applying here changes the local draft only; preview and server validation are still required before save.</p><Textarea rows={24} className="font-mono text-xs" value={advancedText} onChange={(event) => { setAdvancedText(event.target.value); setAdvancedError(''); }} />{advancedError ? <p className="text-sm text-destructive" role="alert">{advancedError}</p> : null}<Button variant="outline" onClick={() => { try { const parsed: unknown = JSON.parse(advancedText); const expected = ['schema_version', 'allowed_values', 'limits', 'defaults', 'policies', 'workflows', 'feature_rollout', 'visual', 'operations']; if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('The governed document must be a JSON object.'); const fields = Object.keys(parsed).sort(); if (fields.join('|') !== [...expected].sort().join('|')) throw new Error('Top-level fields must exactly match the governed HR configuration contract.'); setDocument(parsed as HumanResourcesConfigurationDocument); setAdvancedError(''); } catch (error) { setAdvancedError(error instanceof Error ? error.message : 'The advanced document is invalid.'); } }}>Apply advanced draft</Button></CardContent></Card>

        <Card><CardHeader><CardTitle>Import configuration document</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-muted-foreground">Paste a previously exported document. Import uses the same server validation, versioning, RBAC, and immutable audit path as an ordinary update.</p><Textarea rows={10} value={importText} onChange={(event) => { setImportText(event.target.value); setImportError(''); }} placeholder='{"schema_version": 1, "...": "..."}' />{importError ? <p className="text-sm text-destructive" role="alert">{importError}</p> : null}<Button variant="outline" disabled={!canMutate || !importText.trim() || importConfiguration.isPending} onClick={() => { try { const parsed: unknown = JSON.parse(importText); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !('schema_version' in parsed)) throw new Error('The document does not match the HR configuration contract.'); importConfiguration.mutate(parsed as HumanResourcesConfigurationDocument); } catch (error) { setImportError(error instanceof Error ? error.message : 'The document is not valid JSON.'); } }}><Upload className="mr-2 h-4 w-4" />Import as new version</Button></CardContent></Card>
      </div>

      <aside className="space-y-6">
        <Card><CardHeader><CardTitle>Change control</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm">Current version <strong>{configuration.data.data.version}</strong></p><StatusChip status={safeError ? 'not_ready' : 'ready'} /><Field label="Change reason" guidance="Required for save, rollback, and import audit evidence."><Textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why this change is necessary" /></Field>{safeError ? <p className="text-sm text-destructive" role="alert">{safeError}</p> : null}</CardContent></Card>
        {preview.data ? <Card><CardHeader><CardTitle>Previewed diff</CardTitle></CardHeader><CardContent>{preview.data.data.changes.length ? <ul className="space-y-3">{preview.data.data.changes.map((change) => <li key={change.path} className="rounded border p-3 text-xs"><strong className="font-mono">{change.path}</strong><p className="mt-1 break-all text-muted-foreground">{JSON.stringify(change.before)} → {JSON.stringify(change.after)}</p></li>)}</ul> : <p className="text-sm text-muted-foreground">No changes from the active version.</p>}</CardContent></Card> : null}
        <Card><CardHeader><CardTitle><History className="mr-2 inline h-4 w-4" />Version history</CardTitle></CardHeader><CardContent>{history.data.items.length ? <ol className="space-y-3">{history.data.items.map((version) => <li key={version.id} className="rounded border p-3 text-sm"><div className="flex items-center justify-between"><strong>Version {version.version}</strong><Button size="sm" variant="outline" disabled={!reason.trim() || rollback.isPending || version.version === configuration.data.data.version} onClick={() => rollback.mutate(version.version)}><RotateCcw className="mr-1 h-3 w-3" />Rollback</Button></div><p className="mt-1 text-xs text-muted-foreground">{version.change_reason} · {new Date(version.created_at).toLocaleString()}</p><p className="mt-1 break-all font-mono text-xs">{version.correlation_id}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">No prior versions.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Immutable audit</CardTitle></CardHeader><CardContent>{audit.data.items.length ? <ol className="space-y-3">{audit.data.items.map((record) => <li key={record.id} className="border-b pb-3 text-xs last:border-0"><strong>v{record.version} · {record.actor_id}</strong><p>{record.change_reason}</p><p className="break-all font-mono text-muted-foreground">{record.correlation_id}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">No configuration changes recorded.</p>}</CardContent></Card>
      </aside>
    </div>
    {mutationError ? <GovernedError error={mutationError} resource="Configuration change" /> : null}
  </PageShell>;
}
