import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, History, RotateCcw, Save, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { ErrorState } from '@/components/ui/ErrorState';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { useAuthStore } from '@/stores/auth-store';
import {
  REGIONAL_QUERY_KEYS,
  type RegionalConfigurationDocument,
  type RegionalConfigurationEnvironment,
  type RegionalConfigurationExport,
} from '../contracts';
import { regionalService } from '../services/regional-service';
import { useRegionalDocumentTitle } from '../use-regional-document-title';

const ENVIRONMENTS: RegionalConfigurationEnvironment[] = ['development', 'self-hosted', 'saas'];
const CONFIG_KEYS = ['country_code', 'jurisdiction_type', 'compliance_tags'] as const;
const JURISDICTION_TYPES = ['country', 'state', 'province', 'economic_zone'] as const;
const SEARCH_FIELDS = ['name', 'description'] as const;
const FILTER_FIELDS = ['is_active', 'name'] as const;
const ROLLOUT_ROLES = ['tenant_admin', 'tenant_user'] as const;
const ORDER_FIELDS = [
  'name', '-name', 'created_at', '-created_at', 'updated_at', '-updated_at',
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isConfigurationDocument(value: unknown): value is RegionalConfigurationDocument {
  if (!isRecord(value)) return false;
  const { resource, workflow, api, health, rollout } = value;
  if (
    !isRecord(resource) ||
    !isRecord(workflow) ||
    !isRecord(api) ||
    !isRecord(health) ||
    !isRecord(rollout)
  ) return false;
  return (
    typeof resource.name_min_length === 'number' &&
    typeof resource.name_max_length === 'number' &&
    typeof resource.name_default === 'string' &&
    typeof resource.description_default === 'string' &&
    typeof resource.description_max_length === 'number' &&
    typeof resource.default_active === 'boolean' &&
    isRecord(resource.default_config) &&
    Array.isArray(resource.allowed_config_keys) &&
    Array.isArray(resource.allowed_jurisdiction_types) &&
    typeof resource.max_compliance_tags === 'number' &&
    typeof resource.max_config_bytes === 'number' &&
    Array.isArray(resource.search_fields) &&
    typeof workflow.activation_state === 'boolean' &&
    typeof workflow.deactivation_state === 'boolean' &&
    typeof workflow.require_delete_confirmation === 'boolean' &&
    typeof api.default_page_size === 'number' &&
    typeof api.max_page_size === 'number' &&
    Array.isArray(api.allowed_filters) &&
    Array.isArray(api.allowed_ordering) &&
    typeof health.cache_probe_ttl_seconds === 'number' &&
    typeof rollout.enabled === 'boolean' &&
    Array.isArray(rollout.roles) &&
    Array.isArray(rollout.cohorts)
  );
}

function parseCsv(value: string): string[] {
  return [...new Set(value.split(',').map((entry) => entry.trim()).filter(Boolean))];
}

function validateDocument(document: RegionalConfigurationDocument): string[] {
  const errors: string[] = [];
  const { resource, api, health, rollout } = document;
  if (resource.name_min_length < 1 || resource.name_min_length > 64) {
    errors.push('Minimum name length must be between 1 and 64.');
  }
  if (
    resource.name_max_length < resource.name_min_length ||
    resource.name_max_length > 512
  ) {
    errors.push('Maximum name length must be at least the minimum and no greater than 512.');
  }
  if (
    resource.name_default.trim().length < resource.name_min_length ||
    resource.name_default.trim().length > resource.name_max_length
  ) {
    errors.push('The default name must satisfy the configured name limits.');
  }
  if (resource.description_max_length < 0 || resource.description_max_length > 10_000) {
    errors.push('Description limit must be between 0 and 10,000.');
  }
  if (resource.description_default.length > resource.description_max_length) {
    errors.push('The default description exceeds its configured limit.');
  }
  if (resource.max_compliance_tags < 0 || resource.max_compliance_tags > 100) {
    errors.push('Compliance tag limit must be between 0 and 100.');
  }
  if (resource.max_config_bytes < 128 || resource.max_config_bytes > 65_536) {
    errors.push('Configuration size must be between 128 and 65,536 bytes.');
  }
  if (resource.allowed_config_keys.some((value) => !CONFIG_KEYS.includes(value as typeof CONFIG_KEYS[number]))) {
    errors.push('Resource configuration contains a key outside the platform allow-list.');
  }
  if (
    Object.keys(resource.default_config).some(
      (value) => !resource.allowed_config_keys.includes(value),
    )
  ) {
    errors.push('Default resource configuration uses a disabled key.');
  }
  if (
    resource.default_config.country_code !== undefined &&
    !/^[A-Za-z]{2}$/.test(resource.default_config.country_code)
  ) {
    errors.push('Default country code must contain exactly two letters.');
  }
  if (
    resource.default_config.jurisdiction_type !== undefined &&
    !resource.allowed_jurisdiction_types.includes(
      resource.default_config.jurisdiction_type,
    )
  ) {
    errors.push('Default jurisdiction type must be enabled.');
  }
  if (resource.allowed_jurisdiction_types.some((value) => !JURISDICTION_TYPES.includes(value as typeof JURISDICTION_TYPES[number]))) {
    errors.push('Jurisdiction types contain a value outside the platform allow-list.');
  }
  if (resource.search_fields.some((value) => !SEARCH_FIELDS.includes(value))) {
    errors.push('Search fields contain a value outside the platform allow-list.');
  }
  if (api.default_page_size < 1 || api.default_page_size > api.max_page_size) {
    errors.push('Default page size must be positive and no greater than the maximum.');
  }
  if (api.max_page_size < 1 || api.max_page_size > 500) {
    errors.push('Maximum page size must be between 1 and 500.');
  }
  if (api.allowed_filters.some((value) => !FILTER_FIELDS.includes(value))) {
    errors.push('Filters contain a value outside the platform allow-list.');
  }
  if (api.allowed_ordering.some((value) => !ORDER_FIELDS.includes(value))) {
    errors.push('Ordering contains a value outside the platform allow-list.');
  }
  if (health.cache_probe_ttl_seconds < 1 || health.cache_probe_ttl_seconds > 300) {
    errors.push('Cache probe TTL must be between 1 and 300 seconds.');
  }
  if (rollout.enabled && (rollout.roles.length === 0 || rollout.cohorts.length === 0)) {
    errors.push('Enabled rollout requires at least one role and one cohort.');
  }
  if (rollout.roles.some((value) => !ROLLOUT_ROLES.includes(value as typeof ROLLOUT_ROLES[number]))) {
    errors.push('Rollout roles contain a value outside the platform role allow-list.');
  }
  return errors;
}

type MultiChoiceProps = {
  label: string;
  guidance: string;
  options: readonly string[];
  selected: readonly string[];
  onChange: (values: string[]) => void;
};

function MultiChoice({ label, guidance, options, selected, onChange }: MultiChoiceProps) {
  return (
    <fieldset className="rounded-md border border-border p-3">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      <p className="mb-2 text-xs text-muted-foreground">{guidance}</p>
      <div className="flex flex-wrap gap-3">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selected, option]
                    : selected.filter((value) => value !== option),
                )
              }
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export const RegionalConfigurationPage = () => {
  useRegionalDocumentTitle('Regional configuration');
  const user = useAuthStore((state) => state.user);
  const canManage = user?.tenant_role === 'tenant_admin';
  const queryClient = useQueryClient();
  const importRef = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] =
    useState<RegionalConfigurationEnvironment>('development');
  const [draft, setDraft] = useState<RegionalConfigurationDocument | null>(null);
  const [documentText, setDocumentText] = useState('');
  const [localError, setLocalError] = useState('');
  const [rollbackVersion, setRollbackVersion] = useState<number | null>(null);
  const current = useQuery({
    queryKey: REGIONAL_QUERY_KEYS.configuration(environment),
    queryFn: () => regionalService.getConfiguration(environment),
    enabled: canManage,
  });
  const history = useQuery({
    queryKey: REGIONAL_QUERY_KEYS.configurationHistory(environment),
    queryFn: () => regionalService.listConfigurationHistory(environment),
    enabled: canManage,
  });

  useEffect(() => {
    if (!current.data) return;
    setDraft(current.data.document);
    setDocumentText(JSON.stringify(current.data.document, null, 2));
  }, [current.data]);

  const validationErrors = useMemo(
    () => draft ? validateDocument(draft) : ['Configuration is unavailable.'],
    [draft],
  );
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['regional', 'configuration'] });
  };
  const save = useMutation({
    mutationFn: () => {
      if (!draft || validationErrors.length) throw new Error('Configuration is invalid.');
      return regionalService.updateConfiguration({ environment, document: draft });
    },
    onSuccess: invalidate,
  });
  const preview = useMutation({
    mutationFn: () => {
      if (!draft || validationErrors.length) throw new Error('Configuration is invalid.');
      return regionalService.previewConfiguration(environment, draft);
    },
  });
  const rollback = useMutation({
    mutationFn: (version: number) =>
      regionalService.rollbackConfiguration(environment, version),
    onSuccess: async () => {
      setRollbackVersion(null);
      await invalidate();
    },
  });
  const imported = useMutation({
    mutationFn: (document: RegionalConfigurationDocument) =>
      regionalService.importConfiguration(environment, document),
    onSuccess: invalidate,
  });

  if (!canManage) {
    return (
      <ErrorState
        title="Access denied"
        message="Regional configuration requires the tenant administrator role."
      />
    );
  }
  if (current.isLoading) {
    return <p role="status" className="p-8 text-muted-foreground">Loading configuration…</p>;
  }
  if (current.isError || !draft) {
    return (
      <ErrorState
        title="Configuration unavailable"
        message={current.error instanceof Error ? current.error.message : 'The configuration request failed.'}
        onRetry={() => void current.refetch()}
      />
    );
  }

  const updateResource = <K extends keyof RegionalConfigurationDocument['resource']>(
    key: K,
    value: RegionalConfigurationDocument['resource'][K],
  ) => setDraft({ ...draft, resource: { ...draft.resource, [key]: value } });
  const updateApi = <K extends keyof RegionalConfigurationDocument['api']>(
    key: K,
    value: RegionalConfigurationDocument['api'][K],
  ) => setDraft({ ...draft, api: { ...draft.api, [key]: value } });
  const updateWorkflow = <K extends keyof RegionalConfigurationDocument['workflow']>(
    key: K,
    value: RegionalConfigurationDocument['workflow'][K],
  ) => setDraft({ ...draft, workflow: { ...draft.workflow, [key]: value } });
  const updateDefaultConfig = (
    values: RegionalConfigurationDocument['resource']['default_config'],
  ) => updateResource('default_config', values);

  const applyDocumentText = () => {
    setLocalError('');
    try {
      const parsed: unknown = JSON.parse(documentText);
      if (!isConfigurationDocument(parsed)) {
        throw new Error('The document is missing one or more required configuration fields.');
      }
      const errors = validateDocument(parsed);
      if (errors.length) throw new Error(errors.join(' '));
      setDraft(parsed);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Configuration JSON is invalid.');
    }
  };
  const importDocument = async (file: File) => {
    setLocalError('');
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const candidate = isRecord(parsed) && isConfigurationDocument(parsed.document)
        ? parsed.document
        : parsed;
      if (!isConfigurationDocument(candidate)) {
        throw new Error('The selected file is not a complete Regional configuration document.');
      }
      const errors = validateDocument(candidate);
      if (errors.length) throw new Error(errors.join(' '));
      setDraft(candidate);
      setDocumentText(JSON.stringify(candidate, null, 2));
      await imported.mutateAsync(candidate);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Configuration import failed.');
    }
  };
  const exportDocument = async () => {
    const exported: RegionalConfigurationExport =
      await regionalService.exportConfiguration(environment);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `regional-${environment}-v${exported.version}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main id="main-content" className="space-y-6 p-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div>
          <h1 className="text-3xl font-bold">Regional configuration</h1>
          <p className="mt-2 text-muted-foreground">
            Versioned tenant policy with dry-run, immutable audit, rollback, and portability.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={preview.isPending || validationErrors.length > 0} onClick={() => preview.mutate()}>
            <Eye className="mr-2 h-4 w-4" />Preview
          </Button>
          <Button disabled={save.isPending || validationErrors.length > 0} onClick={() => save.mutate()}>
            <Save className="mr-2 h-4 w-4" />Apply version
          </Button>
        </div>
      </div>
      <Card>
        <CardHeader><CardTitle>Environment and rollout</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <label className="text-sm font-medium">
            Environment
            <select
              className="mt-1 block h-10 w-full rounded-md border border-input bg-background px-3"
              value={environment}
              onChange={(event) => setEnvironment(event.target.value as RegionalConfigurationEnvironment)}
            >
              {ENVIRONMENTS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-3 rounded-md border border-border p-3 text-sm">
            <input
              type="checkbox"
              checked={draft.rollout.enabled}
              onChange={(event) => setDraft({
                ...draft,
                rollout: { ...draft.rollout, enabled: event.target.checked },
              })}
            />
            Capability enabled for this environment
          </label>
          <MultiChoice
            label="Allowed roles"
            guidance="Select the tenant roles included in this phased rollout."
            options={ROLLOUT_ROLES}
            selected={draft.rollout.roles}
            onChange={(roles) => setDraft({
              ...draft,
              rollout: { ...draft.rollout, roles },
            })}
          />
          <Input
            label="Cohorts"
            title="Comma-separated rollout cohorts. Use all for the tenant default."
            value={draft.rollout.cohorts.join(', ')}
            onChange={(event) => setDraft({
              ...draft,
              rollout: { ...draft.rollout, cohorts: parseCsv(event.target.value) },
            })}
          />
        </CardContent>
      </Card>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Resource defaults and safe limits</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Input label="Minimum name length" type="number" min="1" max={draft.resource.name_max_length} value={draft.resource.name_min_length} onChange={(event) => updateResource('name_min_length', Number(event.target.value))} />
            <Input label="Maximum name length" type="number" min={draft.resource.name_min_length} max="512" value={draft.resource.name_max_length} onChange={(event) => updateResource('name_max_length', Number(event.target.value))} />
            <Input label="Default name" value={draft.resource.name_default} minLength={draft.resource.name_min_length} maxLength={draft.resource.name_max_length} onChange={(event) => updateResource('name_default', event.target.value)} />
            <Input label="Description limit" type="number" min="0" max="10000" value={draft.resource.description_max_length} onChange={(event) => updateResource('description_max_length', Number(event.target.value))} />
            <Input label="Compliance tag limit" type="number" min="0" max="100" value={draft.resource.max_compliance_tags} onChange={(event) => updateResource('max_compliance_tags', Number(event.target.value))} />
            <Input label="Configuration byte limit" type="number" min="128" max="65536" value={draft.resource.max_config_bytes} onChange={(event) => updateResource('max_config_bytes', Number(event.target.value))} />
            <label className="flex items-center gap-3 rounded-md border border-border p-3 text-sm">
              <input type="checkbox" checked={draft.resource.default_active} onChange={(event) => updateResource('default_active', event.target.checked)} />
              New resources active by default
            </label>
            <div className="sm:col-span-2">
              <label htmlFor="description-default" className="mb-1 block text-sm font-medium">Default description</label>
              <Textarea id="description-default" maxLength={draft.resource.description_max_length} value={draft.resource.description_default} onChange={(event) => updateResource('description_default', event.target.value)} />
            </div>
            <Input
              label="Default country code"
              maxLength={2}
              disabled={!draft.resource.allowed_config_keys.includes('country_code')}
              value={draft.resource.default_config.country_code ?? ''}
              onChange={(event) => {
                const countryCode = event.target.value.toUpperCase();
                const { country_code: omitted, ...rest } = draft.resource.default_config;
                void omitted;
                updateDefaultConfig(
                  countryCode ? { ...rest, country_code: countryCode } : rest,
                );
              }}
            />
            <label className="text-sm font-medium">
              Default jurisdiction type
              <select
                className="mt-1 block h-10 w-full rounded-md border border-input bg-background px-3 disabled:opacity-50"
                disabled={!draft.resource.allowed_config_keys.includes('jurisdiction_type')}
                value={draft.resource.default_config.jurisdiction_type ?? ''}
                onChange={(event) => {
                  const { jurisdiction_type: omitted, ...rest } =
                    draft.resource.default_config;
                  void omitted;
                  updateDefaultConfig(
                    event.target.value
                      ? { ...rest, jurisdiction_type: event.target.value }
                      : rest,
                  );
                }}
              >
                <option value="">No default</option>
                {draft.resource.allowed_jurisdiction_types.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </label>
            <Input
              label="Default compliance tags"
              title="Comma-separated defaults applied to new resources."
              disabled={!draft.resource.allowed_config_keys.includes('compliance_tags')}
              value={draft.resource.default_config.compliance_tags?.join(', ') ?? ''}
              onChange={(event) => {
                const tags = parseCsv(event.target.value);
                const { compliance_tags: omitted, ...rest } =
                  draft.resource.default_config;
                void omitted;
                updateDefaultConfig(tags.length ? { ...rest, compliance_tags: tags } : rest);
              }}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Workflow and API policy</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-3 rounded-md border border-border p-3 text-sm"><input type="checkbox" checked={draft.workflow.activation_state} onChange={(event) => updateWorkflow('activation_state', event.target.checked)} />Activation target state</label>
            <label className="flex items-center gap-3 rounded-md border border-border p-3 text-sm"><input type="checkbox" checked={draft.workflow.deactivation_state} onChange={(event) => updateWorkflow('deactivation_state', event.target.checked)} />Deactivation target state</label>
            <label className="flex items-center gap-3 rounded-md border border-border p-3 text-sm sm:col-span-2"><input type="checkbox" checked={draft.workflow.require_delete_confirmation} onChange={(event) => updateWorkflow('require_delete_confirmation', event.target.checked)} />Require accessible archive confirmation</label>
            <Input label="Default page size" type="number" min="1" max={draft.api.max_page_size} value={draft.api.default_page_size} onChange={(event) => updateApi('default_page_size', Number(event.target.value))} />
            <Input label="Maximum page size" type="number" min={draft.api.default_page_size} max="500" value={draft.api.max_page_size} onChange={(event) => updateApi('max_page_size', Number(event.target.value))} />
            <Input label="Cache probe TTL (seconds)" type="number" min="1" max="300" value={draft.health.cache_probe_ttl_seconds} onChange={(event) => setDraft({ ...draft, health: { cache_probe_ttl_seconds: Number(event.target.value) } })} />
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <MultiChoice label="Resource configuration keys" guidance="Only selected typed keys can be persisted." options={CONFIG_KEYS} selected={draft.resource.allowed_config_keys} onChange={(values) => {
          const defaultConfig = Object.fromEntries(
            Object.entries(draft.resource.default_config).filter(([key]) =>
              values.includes(key),
            ),
          );
          setDraft({
            ...draft,
            resource: {
              ...draft.resource,
              allowed_config_keys: values,
              default_config: defaultConfig,
            },
          });
        }} />
        <MultiChoice label="Jurisdiction types" guidance="Tenant subset of the platform jurisdiction allow-list." options={JURISDICTION_TYPES} selected={draft.resource.allowed_jurisdiction_types} onChange={(values) => {
          const selectedDefault = draft.resource.default_config.jurisdiction_type;
          let defaultConfig = draft.resource.default_config;
          if (selectedDefault && !values.includes(selectedDefault)) {
            const { jurisdiction_type: omitted, ...rest } = defaultConfig;
            void omitted;
            defaultConfig = rest;
          }
          setDraft({
            ...draft,
            resource: {
              ...draft.resource,
              allowed_jurisdiction_types: values,
              default_config: defaultConfig,
            },
          });
        }} />
        <MultiChoice label="Search fields" guidance="Server-side fields included in resource search." options={SEARCH_FIELDS} selected={draft.resource.search_fields} onChange={(values) => updateResource('search_fields', values as RegionalConfigurationDocument['resource']['search_fields'])} />
        <MultiChoice label="Filter fields" guidance="Server-side query filter allow-list." options={FILTER_FIELDS} selected={draft.api.allowed_filters} onChange={(values) => updateApi('allowed_filters', values as RegionalConfigurationDocument['api']['allowed_filters'])} />
        <div className="lg:col-span-2"><MultiChoice label="Ordering fields" guidance="Deterministic server-side ordering allow-list." options={ORDER_FIELDS} selected={draft.api.allowed_ordering} onChange={(values) => updateApi('allowed_ordering', values as RegionalConfigurationDocument['api']['allowed_ordering'])} /></div>
      </div>
      {validationErrors.length ? (
        <div role="alert" className="rounded-md border border-destructive/40 p-4 text-sm text-destructive">
          {validationErrors.map((error) => <p key={error}>{error}</p>)}
        </div>
      ) : null}
      {(save.error || preview.error || rollback.error || imported.error || localError) ? (
        <p role="alert" className="rounded-md border border-destructive/40 p-4 text-sm text-destructive">
          {localError || (save.error ?? preview.error ?? rollback.error ?? imported.error)?.message}
        </p>
      ) : null}
      {preview.data ? (
        <Card>
          <CardHeader><CardTitle>Dry-run diff</CardTitle></CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">
              {JSON.stringify(preview.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader><CardTitle>Complete configuration document</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Advanced JSON editor for review and configuration-as-code workflows. All fields remain server validated.
          </p>
          <Textarea aria-label="Complete configuration document" rows={20} value={documentText} onChange={(event) => setDocumentText(event.target.value)} />
          <Button variant="outline" onClick={applyDocumentText}>Validate and stage JSON</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><History className="h-5 w-5" />Version history and immutable audit</CardTitle></CardHeader>
        <CardContent>
          {history.isError ? (
            <ErrorState message="Configuration history could not be loaded." onRetry={() => void history.refetch()} />
          ) : history.data?.length ? (
            <ol className="divide-y divide-border">
              {history.data.map((version) => (
                <li key={version.id} className="flex flex-col justify-between gap-3 py-3 md:flex-row md:items-center">
                  <div>
                    <p className="font-medium">Version {version.version} · {version.operation}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(version.created_at).toLocaleString()} · actor {version.actor_id} · correlation {version.correlation_id}
                    </p>
                  </div>
                  <Button variant="outline" size="sm" disabled={version.version === current.data?.version || rollback.isPending} onClick={() => setRollbackVersion(version.version)}>
                    <RotateCcw className="mr-2 h-4 w-4" />Rollback
                  </Button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">No prior versions exist for this environment.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Import and export</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => void exportDocument()}><Download className="mr-2 h-4 w-4" />Export JSON</Button>
          <input ref={importRef} className="hidden" type="file" accept="application/json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importDocument(file); }} />
          <Button variant="outline" disabled={imported.isPending} onClick={() => importRef.current?.click()}><Upload className="mr-2 h-4 w-4" />Import and apply</Button>
        </CardContent>
      </Card>
      <ConfirmDialog
        open={rollbackVersion !== null}
        onOpenChange={(open) => { if (!open) setRollbackVersion(null); }}
        title={`Rollback to version ${rollbackVersion ?? ''}?`}
        description="Rollback creates a new immutable version containing the selected prior document."
        confirmLabel="Create rollback version"
        onConfirm={() => { if (rollbackVersion !== null) rollback.mutate(rollbackVersion); }}
      />
    </main>
  );
};
