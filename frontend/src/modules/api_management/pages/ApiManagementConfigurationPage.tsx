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
  type ApiManagementNavigationConfiguration,
  type ApiManagementConfigurationSchema,
  type ApiManagementValidationLimits,
  type ConfigurationDependency,
  type ConfigurationFieldSchema,
  type ConfigurationVersion,
  type JsonObject,
  type JsonValue,
  type PortableApiManagementConfiguration,
  type ResourceFilterField,
  type ResourceOrderingField,
  type ResourceSearchField,
  type ResourceWritableField,
} from '../contracts';
import { api_managementService } from '../services/api_management-service';

const optionFields = ['writable_fields', 'filter_fields', 'search_fields', 'ordering_fields', 'default_ordering', 'rollout_strategy'] as const;
const boundedFields = ['resource_name_min_length', 'resource_name_max_length', 'page_size', 'max_page_size', 'health_cache_ttl_seconds', 'table_skeleton_rows', 'form_description_rows', 'rollout_percentage', 'rollout_bucket_count', 'quota_cost'] as const;
const validationLimitFields = ['list_max_items', 'list_item_max_length', 'resource_name_minimum_floor', 'resource_name_minimum_ceiling', 'resource_name_maximum_floor', 'resource_name_maximum_ceiling', 'resource_description_max_length', 'page_size_minimum', 'page_size_maximum', 'deletion_confirmation_max_length', 'health_cache_ttl_minimum', 'health_cache_ttl_maximum', 'table_skeleton_rows_minimum', 'table_skeleton_rows_maximum', 'form_description_rows_minimum', 'form_description_rows_maximum', 'rollout_percentage_minimum', 'rollout_percentage_maximum', 'configuration_history_page_size', 'configuration_history_max_page_size', 'configuration_history_max_page', 'configuration_version_reason_max_length', 'resource_version_reason_max_length', 'audit_target_type_max_length', 'audit_action_max_length'] as const satisfies readonly (keyof ApiManagementValidationLimits)[];
const navigationFields = ['resources_list', 'resources_create', 'resources_detail', 'configuration'] as const satisfies readonly (keyof ApiManagementNavigationConfiguration)[];
const stringListFields = ['environment_registry', 'rollout_roles', 'rollout_cohorts', 'allowed_resource_config_keys', 'configuration_version_reasons', 'resource_version_reasons', 'audit_target_types', 'audit_actions'] as const satisfies readonly (keyof ApiManagementConfigurationDocument)[];
const displayedDocumentFields = [
  'environment',
  'environment_registry',
  'resource_name_min_length',
  'resource_name_max_length',
  'resource_description_default',
  'resource_config_default',
  'resource_initially_active',
  'writable_fields',
  'filter_fields',
  'search_fields',
  'ordering_fields',
  'default_ordering',
  'page_size',
  'max_page_size',
  'deletion_confirmation_message',
  'activation_enabled',
  'deactivation_enabled',
  'health_cache_ttl_seconds',
  'table_skeleton_rows',
  'form_description_rows',
  'feature_enabled',
  'rollout_percentage',
  'rollout_roles',
  'rollout_cohorts',
  'rollout_strategy',
  'rollout_bucket_count',
  'quota_cost',
  'configuration_version_reasons',
  'resource_version_reasons',
  'audit_target_types',
  'audit_actions',
  'allowed_resource_config_keys',
] as const;

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

function isStringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && (value as unknown[]).every((entry) => typeof entry === 'string');
}

function promoteImportedEnvironment(candidate: unknown, environment: string): unknown {
  if (candidate === null || typeof candidate !== 'object' || Array.isArray(candidate)) return candidate;
  const imported = candidate as Readonly<Record<string, unknown>>;
  const registryValue = imported.environment_registry;
  const registry = isStringArray(registryValue) ? registryValue : [];
  const promotedRegistry = registry.includes(environment) ? registry : [...registry, environment];
  return { ...imported, environment, environment_registry: promotedRegistry };
}

function isPortableConfiguration(value: unknown): value is PortableApiManagementConfiguration {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Readonly<Record<string, unknown>>;
  return candidate.module === 'api_management' &&
    candidate.schema_version === 2 &&
    typeof candidate.version === 'number' &&
    candidate.document !== null &&
    typeof candidate.document === 'object' &&
    !Array.isArray(candidate.document);
}

function toggle(values: readonly string[], value: string): readonly string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function numberValue(value: string): number {
  return value === '' ? Number.NaN : Number(value);
}

// eslint-disable-next-line complexity -- fail-closed schema validation reports the first precise contract defect.
function schemaProblem(schema: ApiManagementConfigurationSchema): string | null {
  if (!schema.environments.length) return 'The server configuration schema has no governed environments.';
  if (!schema.environment || !schema.environments.includes(schema.environment)) {
    return 'The server schema selected an environment outside its governed registry.';
  }
  for (const field of displayedDocumentFields) {
    if (!schema.fields[field]) return `The server schema omitted metadata for ${field}.`;
  }
  for (const field of optionFields) {
    if (!schema.fields[field]?.options?.length) return `The server schema omitted options for ${field}.`;
  }
  for (const field of boundedFields) {
    const metadata = schema.fields[field];
    if (metadata?.min_value === undefined || metadata.max_value === undefined) return `The server schema omitted safe limits for ${field}.`;
  }
  for (const field of stringListFields) {
    const metadata = schema.fields[field];
    if (metadata?.max_items === undefined || metadata.max_length === undefined) {
      return `The server schema omitted list limits for ${field}.`;
    }
  }
  for (const field of validationLimitFields) {
    const metadata = schema.fields[`validation_limits.${field}`];
    if (metadata?.min_value === undefined || metadata.max_value === undefined) return `The server schema omitted platform guard rails for validation_limits.${field}.`;
  }
  for (const field of navigationFields) {
    const metadata = schema.fields[`navigation.${field}.order`];
    if (metadata?.min_value === undefined || metadata.max_value === undefined) return `The server schema omitted navigation limits for navigation.${field}.order.`;
  }
  for (const [field, metadata] of Object.entries(schema.fields)) {
    if (!metadata.label.trim() || !metadata.help_text.trim()) return `The server schema omitted accessible guidance for ${field}.`;
  }
  return null;
}

// eslint-disable-next-line complexity -- each declarative operator is deliberately handled exhaustively.
function dependencyMatches(document: ApiManagementConfigurationDocument, dependency: ConfigurationDependency): boolean {
  const current = document[dependency.source_field];
  switch (dependency.operator) {
    case 'equals': return current === dependency.value;
    case 'not_equals': return current !== dependency.value;
    case 'less_than': return typeof current === 'number' && typeof dependency.value === 'number' && current < dependency.value;
    case 'less_than_or_equal': return typeof current === 'number' && typeof dependency.value === 'number' && current <= dependency.value;
    case 'greater_than': return typeof current === 'number' && typeof dependency.value === 'number' && current > dependency.value;
    case 'greater_than_or_equal': return typeof current === 'number' && typeof dependency.value === 'number' && current >= dependency.value;
    case 'in': return Array.isArray(dependency.value) && dependency.value.includes(current as JsonValue);
  }
}

function assignDocumentValue(document: ApiManagementConfigurationDocument, field: keyof ApiManagementConfigurationDocument, value: JsonValue): ApiManagementConfigurationDocument {
  return { ...document, [field]: value } as ApiManagementConfigurationDocument;
}

function clearDocumentValue(document: ApiManagementConfigurationDocument, field: keyof ApiManagementConfigurationDocument): ApiManagementConfigurationDocument {
  const current = document[field];
  if (Array.isArray(current)) return assignDocumentValue(document, field, []);
  if (typeof current === 'string') return assignDocumentValue(document, field, '');
  if (current !== null && typeof current === 'object') return assignDocumentValue(document, field, {});
  return document;
}

function applyDependencies(document: ApiManagementConfigurationDocument, schema: ApiManagementConfigurationSchema): ApiManagementConfigurationDocument {
  return schema.dependencies.reduce((current, dependency) => {
    if (!dependencyMatches(current, dependency) || dependency.effect.kind === 'disable') return current;
    if (dependency.effect.kind === 'clear') {
      return dependency.target_fields.reduce(clearDocumentValue, current);
    }
    if (dependency.effect.value === undefined) return current;
    return dependency.target_fields.reduce(
      (updated, target) => assignDocumentValue(updated, target, dependency.effect.value as JsonValue),
      current,
    );
  }, document);
}

function Help({ id, metadata }: { readonly id: string; readonly metadata: ConfigurationFieldSchema }) {
  return <p id={id} className="mt-1 text-xs text-muted-foreground">{metadata.help_text}{metadata.unit ? ` Unit: ${metadata.unit}.` : ''}</p>;
}

function numericProblem(metadata: ConfigurationFieldSchema, value: number, dynamicMinimum?: number, dynamicMaximum?: number): string | undefined {
  const minimum = dynamicMinimum ?? metadata.min_value;
  const maximum = dynamicMaximum ?? metadata.max_value;
  if (!Number.isFinite(value)) return `${metadata.label} must be a number.`;
  if (minimum !== undefined && value < minimum) return `${metadata.label} must be at least ${minimum}.`;
  if (maximum !== undefined && value > maximum) return `${metadata.label} must be at most ${maximum}.`;
  return undefined;
}

function stringListProblem(metadata: ConfigurationFieldSchema, values: readonly string[]): string | undefined {
  if (metadata.max_items !== undefined && values.length > metadata.max_items) {
    return `${metadata.label} accepts at most ${metadata.max_items} entries.`;
  }
  const maximumItemLength = metadata.item_max_length ?? metadata.max_length;
  if (maximumItemLength !== undefined && values.some((value) => value.length > maximumItemLength)) {
    return `${metadata.label} entries must be at most ${maximumItemLength} characters.`;
  }
  return undefined;
}

function NumericSetting({ field, metadata, value, disabled, dynamicMinimum, dynamicMaximum, onChange }: { readonly field: string; readonly metadata: ConfigurationFieldSchema; readonly value: number; readonly disabled?: boolean; readonly dynamicMinimum?: number; readonly dynamicMaximum?: number; readonly onChange: (value: number) => void }) {
  const helpId = `${field}-help`;
  const problem = numericProblem(metadata, value, dynamicMinimum, dynamicMaximum);
  return <div><Input id={field} label={metadata.label} type="number" min={dynamicMinimum ?? metadata.min_value} max={dynamicMaximum ?? metadata.max_value} value={value} disabled={disabled} error={problem} aria-invalid={Boolean(problem)} aria-describedby={helpId} onChange={(event) => onChange(numberValue(event.target.value))} /><Help id={helpId} metadata={metadata} /></div>;
}

function TextSetting({ field, metadata, value, disabled, onChange }: { readonly field: string; readonly metadata: ConfigurationFieldSchema; readonly value: string; readonly disabled?: boolean; readonly onChange: (value: string) => void }) {
  const helpId = `${field}-help`;
  return <div><Input id={field} label={metadata.label} value={value} maxLength={metadata.max_length} disabled={disabled} aria-describedby={helpId} onChange={(event) => onChange(event.target.value)} /><Help id={helpId} metadata={metadata} /></div>;
}

function CheckboxSetting({ field, metadata, checked, disabled, onChange }: { readonly field: string; readonly metadata: ConfigurationFieldSchema; readonly checked: boolean; readonly disabled?: boolean; readonly onChange: (value: boolean) => void }) {
  const helpId = `${field}-help`;
  return <div><label className="flex items-center gap-2 text-sm font-medium"><input id={field} type="checkbox" checked={checked} disabled={disabled} aria-describedby={helpId} onChange={(event) => onChange(event.target.checked)} />{metadata.label}</label><Help id={helpId} metadata={metadata} /></div>;
}

function StringListSetting({ field, metadata, values, disabled, onChange }: { readonly field: string; readonly metadata: ConfigurationFieldSchema; readonly values: readonly string[]; readonly disabled?: boolean; readonly onChange: (value: readonly string[]) => void }) {
  const helpId = `${field}-help`;
  const problem = stringListProblem(metadata, values);
  return <div><Input id={field} label={metadata.label} value={values.join(', ')} disabled={disabled} error={problem} aria-invalid={Boolean(problem)} aria-describedby={helpId} onChange={(event) => onChange(parseList(event.target.value))} /><Help id={helpId} metadata={metadata} /></div>;
}

function OptionSet({ field, metadata, selected, disabled, onToggle }: { readonly field: string; readonly metadata: ConfigurationFieldSchema; readonly selected: readonly string[]; readonly disabled?: boolean; readonly onToggle: (value: string) => void }) {
  const helpId = `${field}-help`;
  return <fieldset aria-describedby={helpId} disabled={disabled}><legend className="text-sm font-medium">{metadata.label}</legend><div className="mt-2 flex flex-wrap gap-4">{metadata.options?.map((value) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(value)} onChange={() => onToggle(value)} />{value}</label>)}</div><Help id={helpId} metadata={metadata} /></fieldset>;
}

// eslint-disable-next-line complexity, max-lines-per-function -- one governed surface coordinates preview, versioning, rollback, import, and export.
export function ApiManagementConfigurationPage() {
  const queryClient = useQueryClient();
  const [environment, setEnvironment] = useState<string | null>(null);
  const schema = useQuery({
    queryKey: QUERY_KEYS.CONFIGURATION_SCHEMA(environment ?? undefined),
    queryFn: () => api_managementService.getConfigurationSchema(environment ?? undefined),
  });
  const [historyPage, setHistoryPage] = useState(1);
  const [draft, setDraft] = useState<ApiManagementConfigurationDocument | null>(null);
  const [validated, setValidated] = useState<ApiManagementConfigurationDocument | null>(null);
  const [validatedSource, setValidatedSource] = useState('');
  const [importMode, setImportMode] = useState(false);
  const [importEnvelope, setImportEnvelope] = useState<PortableApiManagementConfiguration | null>(null);
  const [jsonDefault, setJsonDefault] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [rollbackVersion, setRollbackVersion] = useState<ConfigurationVersion | null>(null);

  useEffect(() => { document.title = 'API Management configuration · SARAISE'; }, []);
  useEffect(() => {
    if (!environment && schema.data?.environment) setEnvironment(schema.data.environment);
  }, [environment, schema.data]);

  const current = useQuery({
    queryKey: QUERY_KEYS.CONFIGURATION(environment ?? ''),
    queryFn: () => {
      if (!environment) throw new Error('A governed environment is required.');
      return api_managementService.getConfiguration(environment);
    },
    enabled: Boolean(environment && schema.data?.environments.length),
  });
  const history = useQuery({
    queryKey: QUERY_KEYS.CONFIGURATION_HISTORY(environment ?? '', { page: historyPage }),
    queryFn: () => {
      if (!environment) throw new Error('A governed environment is required.');
      return api_managementService.listConfigurationHistory(environment, { page: historyPage });
    },
    enabled: Boolean(environment),
  });

  useEffect(() => {
    if (!current.data || draft) return;
    setDraft(current.data.document);
    setJsonDefault(JSON.stringify(current.data.document.resource_config_default, null, 2));
  }, [current.data, draft]);

  const update = <K extends keyof ApiManagementConfigurationDocument>(key: K, value: ApiManagementConfigurationDocument[K]) => {
    setDraft((before) => before && schema.data ? applyDependencies({ ...before, [key]: value }, schema.data) : before);
    setValidated(null); setValidatedSource('');
  };
  const updateValidationLimit = (key: keyof ApiManagementValidationLimits, value: number) => {
    setDraft((before) => before ? { ...before, validation_limits: { ...before.validation_limits, [key]: value } } : before);
    setValidated(null); setValidatedSource('');
  };
  const updateNavigationOrder = (key: keyof ApiManagementNavigationConfiguration, value: number) => {
    setDraft((before) => before ? { ...before, navigation: { ...before.navigation, [key]: { order: value } } } : before);
    setValidated(null); setValidatedSource('');
  };
  const disabled = (field: keyof ApiManagementConfigurationDocument): boolean => Boolean(
    draft && schema.data?.dependencies.some(
      (dependency) => dependency.target_fields.includes(field) && dependencyMatches(draft, dependency),
    ),
  );

  const preview = useMutation({ mutationFn: (document: unknown) => {
    if (!environment) throw new Error('A governed environment is required.');
    return api_managementService.previewConfiguration(environment, { document });
  }, onSuccess: (result) => {
    if (!result.valid) { setValidated(null); toast.error('Configuration validation failed'); return; }
    setValidated(result.normalized_document); setValidatedSource(JSON.stringify(result.normalized_document)); toast.success('Server validation passed');
  } });
  const save = useMutation({ mutationFn: (document: ApiManagementConfigurationDocument) => {
    if (!environment) throw new Error('A governed environment is required.');
    if (importMode) {
      if (!importEnvelope) throw new Error('The portable import envelope is unavailable.');
      return api_managementService.importConfiguration(environment, {
        document: { ...importEnvelope, environment, document },
        idempotency_key: crypto.randomUUID(),
      });
    }
    return api_managementService.updateConfiguration(environment, { document, idempotency_key: crypto.randomUUID() });
  }, onSuccess: async (result) => {
    setDraft(result.document); setValidated(null); setValidatedSource(''); setImportMode(false); setImportEnvelope(null);
    await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CONFIGURATION(result.environment) });
    await queryClient.invalidateQueries({ queryKey: ['api-management', 'configuration', result.environment, 'history'] });
    toast.success(`Configuration version ${result.version} applied`);
  } });
  const rollback = useMutation({ mutationFn: (version: number) => {
    if (!environment) throw new Error('A governed environment is required.');
    return api_managementService.rollbackConfiguration(environment, { version, idempotency_key: crypto.randomUUID() });
  }, onSuccess: async () => {
    setRollbackVersion(null); setDraft(null);
    if (environment) await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CONFIGURATION(environment) });
    toast.success('Rollback created a new configuration version');
  } });
  const exportDocument = useMutation({ mutationFn: () => {
    if (!environment) throw new Error('A governed environment is required.');
    return api_managementService.exportConfiguration(environment);
  }, onSuccess: (result) => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
    link.download = `api-management-${result.environment}-configuration-v${result.version}.json`;
    link.click(); URL.revokeObjectURL(link.href);
  } });

  const importFile = async (file: File) => {
    try {
      if (!environment) throw new Error('Select an environment before importing.');
      const parsed: unknown = JSON.parse(await file.text());
      if (!isPortableConfiguration(parsed)) throw new Error('Import must be a SARAISE API-management schema version 2 export.');
      const promotedCandidate = promoteImportedEnvironment(parsed.document, environment);
      const result = await api_managementService.previewConfiguration(environment, { document: promotedCandidate });
      if (!result.valid) { toast.error('Imported document was rejected by server validation'); return; }
      setDraft(result.normalized_document); setValidated(result.normalized_document); setValidatedSource(JSON.stringify(result.normalized_document)); setJsonDefault(JSON.stringify(result.normalized_document.resource_config_default, null, 2)); setImportMode(true); setImportEnvelope({ ...parsed, environment, document: result.normalized_document });
      toast.success('Import preview is valid; review it before applying');
    } catch (error) { toast.error(error instanceof Error ? error.message : 'The selected file is not valid JSON.'); }
  };

  if (schema.isLoading || !environment || current.isLoading) return <div className="p-8" role="status">Loading governed configuration schema…</div>;
  const metadataProblem = schema.data ? schemaProblem(schema.data) : null;
  const schemaEnvironmentMismatch = schema.data && schema.data.environment !== environment;
  const environmentMismatch = current.data && environment && (
    current.data.environment !== environment ||
    current.data.document.environment !== environment
  );
  if (schema.error || !schema.data || metadataProblem || schemaEnvironmentMismatch || current.error || !current.data || !draft || environmentMismatch) return <div className="p-8"><ErrorState title="Configuration unavailable" message={metadataProblem ?? (schemaEnvironmentMismatch ? 'The server returned schema metadata for a different environment.' : environmentMismatch ? 'The server returned configuration for a different environment.' : schema.error instanceof Error ? schema.error.message : current.error instanceof Error ? current.error.message : 'No tenant configuration was returned.')} onRetry={() => { void schema.refetch(); void current.refetch(); }} /></div>;

  const metadata = (field: string): ConfigurationFieldSchema => schema.data.fields[field]!;
  const meta = (field: keyof ApiManagementConfigurationDocument): ConfigurationFieldSchema => metadata(field);
  const previewCurrent = validated !== null && validatedSource === JSON.stringify(draft);
  const error = preview.error ?? save.error ?? rollback.error ?? exportDocument.error;

  return <main className="space-y-6 p-8">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-3xl font-bold text-foreground">API Management configuration</h1><p className="text-sm text-muted-foreground">{environment} · version {current.data.version} · updated {new Date(current.data.updated_at).toLocaleString()}. Changes are server-validated, versioned, and audited.</p></div><div className="flex gap-2"><Button variant="outline" disabled={exportDocument.isPending} onClick={() => exportDocument.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button><label className="inline-flex cursor-pointer items-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-muted"><Upload className="mr-2 h-4 w-4" />Import preview<input className="sr-only" type="file" accept="application/json,.json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); event.target.value = ''; }} /></label></div></header>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Environment and rollout</h2><div className="grid gap-5 md:grid-cols-2">
      <div><label className="text-sm font-medium" htmlFor="environment">{meta('environment').label}</label><select id="environment" className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={environment ?? ''} aria-describedby="environment-help" onChange={(event) => { setEnvironment(event.target.value); setDraft(null); setValidated(null); setImportMode(false); setImportEnvelope(null); setHistoryPage(1); }}>{schema.data.environments.map((value) => <option key={value}>{value}</option>)}</select><Help id="environment-help" metadata={meta('environment')} /></div>
      <CheckboxSetting field="feature_enabled" metadata={meta('feature_enabled')} checked={draft.feature_enabled} onChange={(value) => update('feature_enabled', value)} />
      <NumericSetting field="rollout_percentage" metadata={meta('rollout_percentage')} value={draft.rollout_percentage} disabled={disabled('rollout_percentage')} onChange={(value) => update('rollout_percentage', value)} />
      <StringListSetting field="rollout_roles" metadata={meta('rollout_roles')} values={draft.rollout_roles} disabled={disabled('rollout_roles')} onChange={(value) => update('rollout_roles', value)} />
      <StringListSetting field="rollout_cohorts" metadata={meta('rollout_cohorts')} values={draft.rollout_cohorts} disabled={disabled('rollout_cohorts')} onChange={(value) => update('rollout_cohorts', value)} />
    </div></Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Resource defaults and safe limits</h2><div className="grid gap-5 md:grid-cols-2">
      <NumericSetting field="resource_name_min_length" metadata={meta('resource_name_min_length')} value={draft.resource_name_min_length} dynamicMaximum={draft.resource_name_max_length} onChange={(value) => update('resource_name_min_length', value)} />
      <NumericSetting field="resource_name_max_length" metadata={meta('resource_name_max_length')} value={draft.resource_name_max_length} dynamicMinimum={draft.resource_name_min_length} onChange={(value) => update('resource_name_max_length', value)} />
      <TextSetting field="resource_description_default" metadata={meta('resource_description_default')} value={draft.resource_description_default} onChange={(value) => update('resource_description_default', value)} />
      <CheckboxSetting field="resource_initially_active" metadata={meta('resource_initially_active')} checked={draft.resource_initially_active} onChange={(value) => update('resource_initially_active', value)} />
      <StringListSetting field="allowed_resource_config_keys" metadata={meta('allowed_resource_config_keys')} values={draft.allowed_resource_config_keys ?? []} onChange={(value) => update('allowed_resource_config_keys', value)} />
    </div><div><Textarea id="resource_config_default" label={meta('resource_config_default').label} rows={draft.form_description_rows} value={jsonDefault} error={jsonError} aria-describedby="resource_config_default-help" onChange={(event) => { const text = event.target.value; setJsonDefault(text); try { const value: unknown = JSON.parse(text); if (!isJsonObject(value)) { setJsonError('Value must be a JSON object.'); return; } const denied = Object.keys(value).filter((key) => !(draft.allowed_resource_config_keys ?? []).includes(key)); if (denied.length) { setJsonError(`Keys not in the allow-list: ${denied.join(', ')}`); return; } setJsonError(''); update('resource_config_default', value); } catch { setJsonError('Enter a valid JSON object.'); } }} /><Help id="resource_config_default-help" metadata={meta('resource_config_default')} /></div></Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Allow-listed operations</h2>
      <OptionSet field="writable_fields" metadata={meta('writable_fields')} selected={draft.writable_fields} onToggle={(value) => update('writable_fields', toggle(draft.writable_fields, value) as readonly ResourceWritableField[])} />
      <OptionSet field="filter_fields" metadata={meta('filter_fields')} selected={draft.filter_fields} onToggle={(value) => update('filter_fields', toggle(draft.filter_fields, value) as readonly ResourceFilterField[])} />
      <OptionSet field="search_fields" metadata={meta('search_fields')} selected={draft.search_fields} onToggle={(value) => update('search_fields', toggle(draft.search_fields, value) as readonly ResourceSearchField[])} />
      <OptionSet field="ordering_fields" metadata={meta('ordering_fields')} selected={draft.ordering_fields} onToggle={(value) => update('ordering_fields', toggle(draft.ordering_fields, value) as readonly ResourceOrderingField[])} />
      <label className="text-sm font-medium">{meta('default_ordering').label}<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.default_ordering} aria-describedby="default_ordering-help" onChange={(event) => update('default_ordering', event.target.value)}>{meta('default_ordering').options?.map((value) => <option key={value}>{value}</option>)}</select><Help id="default_ordering-help" metadata={meta('default_ordering')} /></label>
    </Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Workflow and presentation</h2><div className="grid gap-5 md:grid-cols-2">
      <TextSetting field="deletion_confirmation_message" metadata={meta('deletion_confirmation_message')} value={draft.deletion_confirmation_message} onChange={(value) => update('deletion_confirmation_message', value)} />
      <NumericSetting field="page_size" metadata={meta('page_size')} value={draft.page_size} dynamicMaximum={draft.max_page_size} onChange={(value) => update('page_size', value)} />
      <NumericSetting field="max_page_size" metadata={meta('max_page_size')} value={draft.max_page_size} dynamicMinimum={draft.page_size} onChange={(value) => update('max_page_size', value)} />
      <NumericSetting field="table_skeleton_rows" metadata={meta('table_skeleton_rows')} value={draft.table_skeleton_rows} onChange={(value) => update('table_skeleton_rows', value)} />
      <NumericSetting field="form_description_rows" metadata={meta('form_description_rows')} value={draft.form_description_rows} onChange={(value) => update('form_description_rows', value)} />
      <NumericSetting field="health_cache_ttl_seconds" metadata={meta('health_cache_ttl_seconds')} value={draft.health_cache_ttl_seconds} onChange={(value) => update('health_cache_ttl_seconds', value)} />
      <CheckboxSetting field="activation_enabled" metadata={meta('activation_enabled')} checked={draft.activation_enabled} disabled={disabled('activation_enabled')} onChange={(value) => update('activation_enabled', value)} />
      <CheckboxSetting field="deactivation_enabled" metadata={meta('deactivation_enabled')} checked={draft.deactivation_enabled} disabled={disabled('deactivation_enabled')} onChange={(value) => update('deactivation_enabled', value)} />
    </div></Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Runtime governance and navigation</h2><div className="grid gap-5 md:grid-cols-2">
      <StringListSetting field="environment_registry" metadata={meta('environment_registry')} values={draft.environment_registry} onChange={(value) => update('environment_registry', value.includes(environment) ? value : [...value, environment])} />
      <label className="text-sm font-medium">{meta('rollout_strategy').label}<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.rollout_strategy} aria-describedby="rollout_strategy-help" onChange={(event) => update('rollout_strategy', event.target.value)}>{meta('rollout_strategy').options?.map((value) => <option key={value}>{value}</option>)}</select><Help id="rollout_strategy-help" metadata={meta('rollout_strategy')} /></label>
      <NumericSetting field="rollout_bucket_count" metadata={meta('rollout_bucket_count')} value={draft.rollout_bucket_count} onChange={(value) => update('rollout_bucket_count', value)} />
      <NumericSetting field="quota_cost" metadata={meta('quota_cost')} value={draft.quota_cost} onChange={(value) => update('quota_cost', value)} />
      {navigationFields.map((field) => <NumericSetting key={field} field={`navigation.${field}.order`} metadata={metadata(`navigation.${field}.order`)} value={draft.navigation[field].order} onChange={(value) => updateNavigationOrder(field, value)} />)}
    </div></Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Version and audit evidence</h2>
      <StringListSetting field="configuration_version_reasons" metadata={meta('configuration_version_reasons')} values={draft.configuration_version_reasons} onChange={(value) => update('configuration_version_reasons', value)} />
      <StringListSetting field="resource_version_reasons" metadata={meta('resource_version_reasons')} values={draft.resource_version_reasons} onChange={(value) => update('resource_version_reasons', value)} />
      <StringListSetting field="audit_target_types" metadata={meta('audit_target_types')} values={draft.audit_target_types} onChange={(value) => update('audit_target_types', value)} />
      <StringListSetting field="audit_actions" metadata={meta('audit_actions')} values={draft.audit_actions} onChange={(value) => update('audit_actions', value)} />
    </Card>

    <Card className="space-y-5 p-6"><h2 className="text-lg font-semibold">Advanced tenant safety limits</h2><p className="text-sm text-muted-foreground">These tenant limits remain bounded by immutable platform hard ceilings supplied in the server schema. Lowering a limit can reject future writes that were previously accepted.</p><div className="grid gap-5 md:grid-cols-2">
      {validationLimitFields.map((field) => <NumericSetting key={field} field={`validation_limits.${field}`} metadata={metadata(`validation_limits.${field}`)} value={draft.validation_limits[field]} onChange={(value) => updateValidationLimit(field, value)} />)}
    </div></Card>

    <Card className="space-y-4 p-6"><h2 className="text-lg font-semibold">Validation preview</h2><p className="text-sm text-muted-foreground">Preview calls the governed API. Apply remains disabled until the exact current draft passes server validation.</p><div className="flex gap-3"><Button variant="outline" disabled={preview.isPending || Boolean(jsonError)} onClick={() => preview.mutate(draft)}>{preview.isPending ? 'Validating…' : 'Preview changes'}</Button><Button disabled={!previewCurrent || save.isPending} onClick={() => { if (validated) save.mutate(validated); }}>{save.isPending ? 'Applying…' : importMode ? 'Apply imported configuration' : 'Apply new version'}</Button></div>{preview.data?.changes.length ? <ul className="divide-y rounded border">{preview.data.changes.map((change) => <li key={change.field} className="grid gap-2 p-3 text-sm md:grid-cols-3"><strong>{change.field}</strong><code className="break-all text-muted-foreground">{JSON.stringify(change.before)}</code><code className="break-all text-foreground">{JSON.stringify(change.after)}</code></li>)}</ul> : previewCurrent ? <p className="text-sm text-muted-foreground">The server found no changes.</p> : null}{preview.data?.errors ? <pre role="alert" className="overflow-auto rounded bg-destructive/10 p-3 text-sm text-destructive">{JSON.stringify(preview.data.errors, null, 2)}</pre> : null}{error ? <p role="alert" className="text-sm text-destructive">{error instanceof Error ? error.message : 'The configuration operation failed.'}</p> : null}</Card>

    <Card className="space-y-4 p-6"><h2 className="flex items-center gap-2 text-lg font-semibold"><History className="h-5 w-5" />Immutable {environment} version history</h2>{history.isLoading ? <p role="status">Loading history…</p> : history.error ? <ErrorState message={history.error instanceof Error ? history.error.message : 'History could not be loaded.'} onRetry={() => { void history.refetch(); }} /> : history.data?.results.length ? <><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left"><th className="p-2">Version</th><th className="p-2">Changed</th><th className="p-2">Actor</th><th className="p-2">Correlation</th><th className="p-2 text-right">Action</th></tr></thead><tbody>{history.data.results.map((version) => <tr key={`${version.environment}-${version.version}`} className="border-b"><td className="p-2">{version.version}</td><td className="p-2">{new Date(version.created_at).toLocaleString()}</td><td className="p-2 font-mono text-xs">{version.actor_id}</td><td className="p-2 font-mono text-xs">{version.correlation_id}</td><td className="p-2 text-right"><Button size="sm" variant="outline" disabled={version.version === current.data.version} onClick={() => setRollbackVersion(version)}><RotateCcw className="mr-2 h-3 w-3" />Rollback</Button></td></tr>)}</tbody></table></div><div className="flex items-center justify-between"><Button variant="outline" disabled={!history.data.previous} onClick={() => setHistoryPage((page) => Math.max(1, page - 1))}>Previous versions</Button><span className="text-sm text-muted-foreground">Page {historyPage} · {history.data.count} versions</span><Button variant="outline" disabled={!history.data.next} onClick={() => setHistoryPage((page) => page + 1)}>Next versions</Button></div></> : <p className="text-sm text-muted-foreground">No configuration history is available.</p>}</Card>

    <Dialog open={rollbackVersion !== null} onOpenChange={(open) => { if (!open && !rollback.isPending) setRollbackVersion(null); }} title={`Rollback ${environment} to version ${rollbackVersion?.version ?? ''}?`} description="Rollback preserves history by creating a new current version from the selected immutable snapshot." size="sm"><div className="flex justify-end gap-2"><Button variant="outline" disabled={rollback.isPending} onClick={() => setRollbackVersion(null)}>Cancel</Button><Button disabled={!rollbackVersion || rollback.isPending} onClick={() => { if (rollbackVersion) rollback.mutate(rollbackVersion.version); }}>{rollback.isPending ? 'Rolling back…' : 'Create rollback version'}</Button></div></Dialog>
  </main>;
}
