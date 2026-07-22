import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, History, RotateCcw, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ErrorState } from '@/components/ui';
import {
  QUERY_KEYS,
  type ApiManagementConfigurationDocument,
  type ConfigurationVersion,
  type DeploymentEnvironment,
  type JsonObject,
  type JsonValue,
  type ResourceFilterField,
  type ResourceOrderingField,
  type ResourceSearchField,
  type ResourceWritableField,
} from '../contracts';
import { api_managementService } from '../services/api_management-service';

const writableOptions: readonly ResourceWritableField[] = ['name', 'description', 'config'];
const filterOptions: readonly ResourceFilterField[] = ['is_active'];
const searchOptions: readonly ResourceSearchField[] = ['name', 'description'];
const orderingOptions: readonly ResourceOrderingField[] = ['name', 'created_at', 'updated_at'];
const environments: readonly DeploymentEnvironment[] = ['development', 'staging', 'production'];

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) return true;
  if (Array.isArray(value)) return value.every(isJsonValue);
  return typeof value === 'object' && Object.values(value).every(isJsonValue);
}

function isJsonObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && isJsonValue(value);
}

function parseList(value: string): readonly string[] {
  return Array.from(new Set(value.split(',').map((item) => item.trim()).filter(Boolean)));
}

function toggle<T extends string>(values: readonly T[], value: T): readonly T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function isEnvironment(value: string): value is DeploymentEnvironment {
  return environments.some((environment) => environment === value);
}

function numberValue(value: string): number {
  return value === '' ? Number.NaN : Number(value);
}

// eslint-disable-next-line complexity -- this page coordinates the complete governed configuration lifecycle in one transaction-oriented surface.
export function ApiManagementConfigurationPage() {
  const queryClient = useQueryClient();
  const current = useQuery({ queryKey: QUERY_KEYS.CONFIGURATION, queryFn: api_managementService.getConfiguration });
  const history = useQuery({ queryKey: QUERY_KEYS.CONFIGURATION_HISTORY, queryFn: api_managementService.listConfigurationHistory });
  const [draft, setDraft] = useState<ApiManagementConfigurationDocument | null>(null);
  const [validated, setValidated] = useState<ApiManagementConfigurationDocument | null>(null);
  const [validatedSource, setValidatedSource] = useState('');
  const [importMode, setImportMode] = useState(false);
  const [jsonDefault, setJsonDefault] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [rollbackVersion, setRollbackVersion] = useState<ConfigurationVersion | null>(null);

  useEffect(() => { document.title = 'API Management configuration · SARAISE'; }, []);
  useEffect(() => {
    if (!current.data || draft) return;
    setDraft(current.data.document);
    setJsonDefault(JSON.stringify(current.data.document.resource_config_default, null, 2));
  }, [current.data, draft]);

  const update = <K extends keyof ApiManagementConfigurationDocument>(key: K, value: ApiManagementConfigurationDocument[K]) => {
    setDraft((valueBefore) => valueBefore ? { ...valueBefore, [key]: value } : valueBefore);
    setValidated(null);
    setValidatedSource('');
    setImportMode(false);
  };
  const updateDocument = (change: (current: ApiManagementConfigurationDocument) => ApiManagementConfigurationDocument) => {
    setDraft((currentDraft) => currentDraft ? change(currentDraft) : currentDraft);
    setValidated(null); setValidatedSource(''); setImportMode(false);
  };

  const preview = useMutation({
    mutationFn: (document: unknown) => api_managementService.previewConfiguration({ document }),
    onSuccess: (result) => {
      if (!result.valid) { setValidated(null); toast.error('Configuration validation failed'); return; }
      setValidated(result.normalized_document);
      setValidatedSource(JSON.stringify(result.normalized_document));
      toast.success('Server validation passed');
    },
  });
  const save = useMutation({
    mutationFn: (document: ApiManagementConfigurationDocument) => {
      const request = { document, idempotency_key: crypto.randomUUID() };
      return importMode ? api_managementService.importConfiguration(request) : api_managementService.updateConfiguration(request);
    },
    onSuccess: async (result) => {
      setDraft(result.document); setValidated(null); setValidatedSource(''); setImportMode(false);
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CONFIGURATION });
      toast.success(`Configuration version ${result.version} applied`);
    },
  });
  const rollback = useMutation({
    mutationFn: (version: number) => api_managementService.rollbackConfiguration({ version, idempotency_key: crypto.randomUUID() }),
    onSuccess: async () => { setRollbackVersion(null); setDraft(null); await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CONFIGURATION }); toast.success('Rollback created a new configuration version'); },
  });
  const exportDocument = useMutation({
    mutationFn: api_managementService.exportConfiguration,
    onSuccess: (result) => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
      link.download = `api-management-configuration-v${result.version}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    },
  });

  const importFile = async (file: File) => {
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const candidate = typeof parsed === 'object' && parsed !== null && 'document' in parsed ? parsed.document : parsed;
      const result = await api_managementService.previewConfiguration({ document: candidate });
      if (!result.valid) { toast.error('Imported document was rejected by server validation'); return; }
      setDraft(result.normalized_document); setValidated(result.normalized_document); setValidatedSource(JSON.stringify(result.normalized_document)); setJsonDefault(JSON.stringify(result.normalized_document.resource_config_default, null, 2)); setImportMode(true);
      toast.success('Import preview is valid; review it before applying');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'The selected file is not valid JSON.');
    }
  };

  if (current.isLoading) return <div className="p-8" role="status">Loading tenant configuration…</div>;
  if (current.error || !current.data || !draft) return <div className="p-8"><ErrorState title="Configuration unavailable" message={current.error instanceof Error ? current.error.message : 'No tenant configuration was returned.'} onRetry={() => { void current.refetch(); }} /></div>;

  const previewCurrent = validated !== null && validatedSource === JSON.stringify(draft);
  const dependentDisabled = !draft.feature_enabled;
  const cohortTargetingDisabled = dependentDisabled || draft.rollout_percentage === 100;
  const error = preview.error ?? save.error ?? rollback.error ?? exportDocument.error;

  return (
    <main className="space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-3xl font-bold text-foreground">API Management configuration</h1><p className="text-sm text-muted-foreground">Version {current.data.version} · updated {new Date(current.data.updated_at).toLocaleString()}. All changes are server-validated, versioned, and audited.</p></div><div className="flex gap-2"><Button variant="outline" disabled={exportDocument.isPending} onClick={() => exportDocument.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button><label className="inline-flex cursor-pointer items-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-muted"><Upload className="mr-2 h-4 w-4" />Import preview<input className="sr-only" type="file" accept="application/json,.json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); event.target.value = ''; }} /></label></div></header>

      <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Environment and rollout</h2><div className="grid gap-5 md:grid-cols-2">
        <label className="text-sm font-medium">Environment<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.environment} onChange={(event) => { if (isEnvironment(event.target.value)) update('environment', event.target.value); }}>{environments.map((value) => <option key={value}>{value}</option>)}</select><span className="mt-1 block text-xs font-normal text-muted-foreground">The same runtime path is used in every environment.</span></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.feature_enabled} onChange={(event) => updateDocument((value) => event.target.checked ? { ...value, feature_enabled: true } : { ...value, feature_enabled: false, rollout_percentage: 0, rollout_roles: [], rollout_cohorts: [], activation_enabled: false, deactivation_enabled: false })} />Feature enabled for this tenant</label>
        <Input label="Rollout percentage" type="number" min={0} max={100} value={draft.rollout_percentage} disabled={dependentDisabled} onChange={(event) => { const percentage = numberValue(event.target.value); updateDocument((value) => percentage === 100 ? { ...value, rollout_percentage: percentage, rollout_roles: [], rollout_cohorts: [] } : { ...value, rollout_percentage: percentage }); }} />
        <Input label="Rollout roles (comma separated)" value={draft.rollout_roles.join(', ')} disabled={cohortTargetingDisabled} onChange={(event) => update('rollout_roles', parseList(event.target.value))} />
        <Input label="Rollout cohorts (comma separated)" value={draft.rollout_cohorts.join(', ')} disabled={cohortTargetingDisabled} onChange={(event) => update('rollout_cohorts', parseList(event.target.value))} />
      </div><p className="text-xs text-muted-foreground">Role and cohort targeting is available only for partial rollouts. At 100%, all eligible tenant users receive the feature.</p></Card>

      <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Resource defaults and safe limits</h2><div className="grid gap-5 md:grid-cols-2"><Input label="Minimum name length" type="number" min={1} max={draft.resource_name_max_length} value={draft.resource_name_min_length} onChange={(event) => update('resource_name_min_length', numberValue(event.target.value))} /><Input label="Maximum name length" type="number" min={draft.resource_name_min_length} max={255} value={draft.resource_name_max_length} onChange={(event) => update('resource_name_max_length', numberValue(event.target.value))} /><Input label="Default description" value={draft.resource_description_default} onChange={(event) => update('resource_description_default', event.target.value)} /><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.resource_initially_active} onChange={(event) => update('resource_initially_active', event.target.checked)} />New resources start active</label><Input label="Allowed resource configuration keys" value={(draft.allowed_resource_config_keys ?? []).join(', ')} onChange={(event) => update('allowed_resource_config_keys', parseList(event.target.value))} /></div>
        <Textarea label="Default resource configuration (JSON object)" rows={draft.form_description_rows} value={jsonDefault} error={jsonError} onChange={(event) => { const text = event.target.value; setJsonDefault(text); try { const value: unknown = JSON.parse(text); if (!isJsonObject(value)) { setJsonError('Value must be a JSON object.'); return; } const denied = Object.keys(value).filter((key) => !(draft.allowed_resource_config_keys ?? []).includes(key)); if (denied.length) { setJsonError(`Keys not in the allow-list: ${denied.join(', ')}`); return; } setJsonError(''); update('resource_config_default', value); } catch { setJsonError('Enter a valid JSON object.'); } }} />
      </Card>

      <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Allow-listed operations</h2><OptionSet label="Writable fields" options={writableOptions} selected={draft.writable_fields} onToggle={(value) => update('writable_fields', toggle(draft.writable_fields, value))} /><OptionSet label="Filter fields" options={filterOptions} selected={draft.filter_fields} onToggle={(value) => update('filter_fields', toggle(draft.filter_fields, value))} /><OptionSet label="Search fields" options={searchOptions} selected={draft.search_fields} onToggle={(value) => update('search_fields', toggle(draft.search_fields, value))} /><OptionSet label="Ordering fields" options={orderingOptions} selected={draft.ordering_fields} onToggle={(value) => update('ordering_fields', toggle(draft.ordering_fields, value))} /><label className="text-sm font-medium">Default ordering<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.default_ordering} onChange={(event) => update('default_ordering', event.target.value)}>{draft.ordering_fields.flatMap((value) => [<option key={value} value={value}>{value} ascending</option>, <option key={`-${value}`} value={`-${value}`}>{value} descending</option>])}</select></label></Card>

      <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Workflow and presentation</h2><div className="grid gap-5 md:grid-cols-2"><Input label="Archive confirmation message" value={draft.deletion_confirmation_message} onChange={(event) => update('deletion_confirmation_message', event.target.value)} /><Input label="Page size" type="number" min={1} max={draft.max_page_size} value={draft.page_size} onChange={(event) => update('page_size', numberValue(event.target.value))} /><Input label="Maximum page size" type="number" min={draft.page_size} max={100} value={draft.max_page_size} onChange={(event) => update('max_page_size', numberValue(event.target.value))} /><Input label="Loading table rows" type="number" min={1} max={20} value={draft.table_skeleton_rows} onChange={(event) => update('table_skeleton_rows', numberValue(event.target.value))} /><Input label="Description field rows" type="number" min={2} max={20} value={draft.form_description_rows} onChange={(event) => update('form_description_rows', numberValue(event.target.value))} /><Input label="Health cache TTL (seconds)" type="number" min={1} max={300} value={draft.health_cache_ttl_seconds} onChange={(event) => update('health_cache_ttl_seconds', numberValue(event.target.value))} /><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.activation_enabled} disabled={dependentDisabled} onChange={(event) => update('activation_enabled', event.target.checked)} />Activation transition enabled</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.deactivation_enabled} disabled={dependentDisabled} onChange={(event) => update('deactivation_enabled', event.target.checked)} />Deactivation transition enabled</label></div></Card>

      <Card className="space-y-4 p-6"><h2 className="text-lg font-semibold">Validation preview</h2><p className="text-sm text-muted-foreground">Preview calls the governed API. Apply remains disabled until the exact current draft passes server validation.</p><div className="flex gap-3"><Button variant="outline" disabled={preview.isPending || Boolean(jsonError)} onClick={() => preview.mutate(draft)}>{preview.isPending ? 'Validating…' : 'Preview changes'}</Button><Button disabled={!previewCurrent || save.isPending} onClick={() => { if (validated) save.mutate(validated); }}>{save.isPending ? 'Applying…' : importMode ? 'Apply imported configuration' : 'Apply new version'}</Button></div>{preview.data?.changes.length ? <ul className="divide-y rounded border">{preview.data.changes.map((change) => <li key={change.field} className="grid gap-2 p-3 text-sm md:grid-cols-3"><strong>{change.field}</strong><code className="break-all text-muted-foreground">{JSON.stringify(change.before)}</code><code className="break-all text-foreground">{JSON.stringify(change.after)}</code></li>)}</ul> : previewCurrent ? <p className="text-sm text-muted-foreground">The server found no changes.</p> : null}{preview.data?.errors ? <pre role="alert" className="overflow-auto rounded bg-destructive/10 p-3 text-sm text-destructive">{JSON.stringify(preview.data.errors, null, 2)}</pre> : null}{error ? <p role="alert" className="text-sm text-destructive">{error instanceof Error ? error.message : 'The configuration operation failed.'}</p> : null}</Card>

      <Card className="space-y-4 p-6"><h2 className="flex items-center gap-2 text-lg font-semibold"><History className="h-5 w-5" />Immutable version history</h2>{history.isLoading ? <p role="status">Loading history…</p> : history.error ? <ErrorState message={history.error instanceof Error ? history.error.message : 'History could not be loaded.'} onRetry={() => { void history.refetch(); }} /> : history.data?.length ? <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left"><th className="p-2">Version</th><th className="p-2">Changed</th><th className="p-2">Actor</th><th className="p-2">Correlation</th><th className="p-2 text-right">Action</th></tr></thead><tbody>{history.data.map((version) => <tr key={version.version} className="border-b"><td className="p-2">{version.version}</td><td className="p-2">{new Date(version.created_at).toLocaleString()}</td><td className="p-2 font-mono text-xs">{version.actor_id}</td><td className="p-2 font-mono text-xs">{version.correlation_id}</td><td className="p-2 text-right"><Button size="sm" variant="outline" disabled={version.version === current.data.version} onClick={() => setRollbackVersion(version)}><RotateCcw className="mr-2 h-3 w-3" />Rollback</Button></td></tr>)}</tbody></table></div> : <p className="text-sm text-muted-foreground">No configuration history is available.</p>}</Card>

      <Dialog open={rollbackVersion !== null} onOpenChange={(open) => { if (!open && !rollback.isPending) setRollbackVersion(null); }} title={`Rollback to version ${rollbackVersion?.version ?? ''}?`} description="Rollback preserves history by creating a new current version from the selected immutable snapshot." size="sm"><div className="flex justify-end gap-2"><Button variant="outline" disabled={rollback.isPending} onClick={() => setRollbackVersion(null)}>Cancel</Button><Button disabled={!rollbackVersion || rollback.isPending} onClick={() => { if (rollbackVersion) rollback.mutate(rollbackVersion.version); }}>{rollback.isPending ? 'Rolling back…' : 'Create rollback version'}</Button></div></Dialog>
    </main>
  );
}

function OptionSet<T extends string>({ label, options, selected, onToggle }: { readonly label: string; readonly options: readonly T[]; readonly selected: readonly T[]; readonly onToggle: (value: T) => void }) {
  return <fieldset><legend className="text-sm font-medium">{label}</legend><div className="mt-2 flex flex-wrap gap-4">{options.map((value) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(value)} onChange={() => onToggle(value)} />{value}</label>)}</div></fieldset>;
}
