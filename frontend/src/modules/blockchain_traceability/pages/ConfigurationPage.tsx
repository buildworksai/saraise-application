import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, HeartPulse, RotateCcw, Save, Upload } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { TraceabilityConfigurationDocument, TraceabilityConfigurationExport } from '../contracts';
import { ApiProblem, ConfiguredStatusPill, EmptyPanel, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { traceabilityCapabilitiesKey, traceabilityConfigurationKey, useTraceabilityCapabilities, useTraceabilityConfiguration } from '../hooks/use-traceability-configuration';
import { blockchainTraceabilityService } from '../services/blockchain_traceability-service';

const configurationHistoryKey = ['blockchain-traceability', 'configuration', 'history'] as const;

function splitStrings(value: string): readonly string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function splitNumbers(value: string): readonly number[] {
  return splitStrings(value).map(Number).filter(Number.isFinite);
}

function downloadConfiguration(configuration: TraceabilityConfigurationExport): void {
  const blob = new Blob([JSON.stringify(configuration, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `blockchain-traceability-${configuration.environment}-v${configuration.version}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function parseImportedDocument(source: string): TraceabilityConfigurationDocument {
  const parsed: unknown = JSON.parse(source);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Import must be a JSON object.');
  if ('document' in parsed) return (parsed as TraceabilityConfigurationExport).document;
  return parsed as TraceabilityConfigurationDocument;
}

function NumberSetting({ id, label, help, value, onChange, disabled = false }: { id: string; label: string; help: string; value: number; onChange: (value: number) => void; disabled?: boolean }) {
  return <Input id={id} label={label} title={help} type="number" required disabled={disabled} value={value} onChange={(event) => onChange(Number(event.target.value))} />;
}

// This console intentionally coordinates every governed configuration operation in one reviewable workflow.
// eslint-disable-next-line complexity, max-lines-per-function
export function ConfigurationPage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const environment = params.get('environment') ?? 'default';
  const configuration = useTraceabilityConfiguration(environment);
  const capabilities = useTraceabilityCapabilities(environment);
  const history = useQuery({ queryKey: [...configurationHistoryKey, environment], queryFn: () => blockchainTraceabilityService.listConfigurationHistory(environment) });
  const healthEnabled = capabilities.data?.document.features.enabled === true && capabilities.data.document.features.enable_health;
  const health = useQuery({ queryKey: ['blockchain-traceability', 'health'], queryFn: blockchainTraceabilityService.getHealth, enabled: healthEnabled });
  const [draft, setDraft] = useState<TraceabilityConfigurationDocument | null>(null);
  const [source, setSource] = useState('');
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [importSource, setImportSource] = useState('');
  const [previewedSource, setPreviewedSource] = useState<string | null>(null);

  useEffect(() => {
    if (!configuration.data) return;
    setDraft(configuration.data.document);
    setSource(JSON.stringify(configuration.data.document, null, 2));
  }, [configuration.data]);
  useEffect(() => {
    if (draft && !sourceError) setSource(JSON.stringify(draft, null, 2));
  }, [draft, sourceError]);

  const fingerprint = useMemo(() => draft ? JSON.stringify(draft) : '', [draft]);
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: traceabilityConfigurationKey }),
      client.invalidateQueries({ queryKey: traceabilityCapabilitiesKey }),
      client.invalidateQueries({ queryKey: configurationHistoryKey }),
    ]);
  };
  const preview = useMutation({
    mutationFn: () => blockchainTraceabilityService.previewConfiguration({ document: draft!, environment }),
    onSuccess: (result) => {
      setDraft(result.document);
      setSource(JSON.stringify(result.document, null, 2));
      setPreviewedSource(JSON.stringify(result.document));
    },
  });
  const save = useMutation({ mutationFn: () => blockchainTraceabilityService.updateConfiguration({ document: draft!, environment }), onSuccess: refresh });
  const rollback = useMutation({ mutationFn: (version: number) => blockchainTraceabilityService.rollbackConfiguration({ version, environment }), onSuccess: refresh });
  const importMutation = useMutation({ mutationFn: () => blockchainTraceabilityService.importConfiguration({ document: parseImportedDocument(importSource), environment }), onSuccess: async () => { setImportSource(''); await refresh(); } });
  const exportMutation = useMutation({ mutationFn: () => blockchainTraceabilityService.exportConfiguration(environment), onSuccess: downloadConfiguration });

  if (configuration.isLoading || capabilities.isLoading) return <PageSkeleton label="Loading traceability configuration" />;
  if (configuration.error || capabilities.error || !configuration.data || !capabilities.data || !draft) return <main className="p-4 sm:p-8"><ApiProblem error={configuration.error ?? capabilities.error} onRetry={() => { void configuration.refetch(); void capabilities.refetch(); }} /></main>;

  const limitsInvalid = draft.validation.max_json_bytes < 1 || draft.validation.max_json_depth < 1 || draft.validation.max_json_keys < 1 || draft.list_policy.default_page_size < 1 || draft.list_policy.default_page_size > draft.list_policy.max_page_size || draft.resilience.base_backoff_seconds > draft.resilience.max_backoff_seconds || draft.network_policy.default_confirmation_depth > draft.network_policy.max_confirmation_depth || draft.schema_policy.allowed_versions.length === 0 || draft.validation.gtin_lengths.length === 0;
  const previewCurrent = previewedSource === fingerprint;
  const canSave = capabilities.data.can_update && previewCurrent && !limitsInvalid && !sourceError && !save.isPending;
  const operationError = preview.error ?? save.error ?? rollback.error ?? importMutation.error ?? exportMutation.error;
  const setDocument = (next: TraceabilityConfigurationDocument) => { setDraft(next); setPreviewedSource(null); };
  const setFeature = <K extends keyof TraceabilityConfigurationDocument['features']>(key: K, value: TraceabilityConfigurationDocument['features'][K]) => setDocument({ ...draft, features: { ...draft.features, [key]: value } });

  return <main className="space-y-8 p-4 sm:p-8">
    <PageHeader title="Blockchain traceability configuration" description="Tenant-scoped, environment-specific behavior. Changes are server-validated, previewed, versioned, audited, portable, and reversible." actions={<><Button variant="outline" disabled={!capabilities.data.can_export || exportMutation.isPending} onClick={() => exportMutation.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button><Button variant="outline" disabled={!capabilities.data.can_preview || preview.isPending || limitsInvalid || Boolean(sourceError)} onClick={() => preview.mutate()}><Save className="mr-2 h-4 w-4" />Preview</Button><Button disabled={!canSave} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4" />Save version</Button></>} />
    {operationError && <ApiProblem error={operationError} mutation onRetry={() => { preview.reset(); save.reset(); rollback.reset(); importMutation.reset(); exportMutation.reset(); }} />}
    <Card className="p-5"><div className="flex flex-wrap items-center gap-3"><ConfiguredStatusPill status={draft.features.enabled ? 'active' : 'disabled'} /><span className="text-sm">Version {configuration.data.version} · {configuration.data.environment}</span><span className="font-mono text-xs text-muted-foreground">Tenant {configuration.data.tenant_id}</span></div></Card>
    <Card className="p-5"><Input id="configuration-environment" label="Environment" title="Select a tenant environment without introducing divergent code paths." pattern="[a-z0-9-]+" value={environment} onChange={(event) => { const next = new URLSearchParams(params); next.set('environment', event.target.value); setParams(next); setDraft(null); setPreviewedSource(null); }} /><p className="mt-2 text-xs text-muted-foreground">Every environment uses the identical service path; only the governed value differs.</p></Card>

    <section className="space-y-4" aria-labelledby="limits-heading"><div><h2 id="limits-heading" className="text-xl font-semibold">Safe limits and validation allow-lists</h2><p className="text-sm text-muted-foreground">Dependent and invalid combinations disable preview and save. The API independently enforces platform ceilings.</p></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <NumberSetting id="max-json-bytes" label="Maximum JSON bytes" help="Largest JSON evidence document accepted for this tenant." value={draft.validation.max_json_bytes} onChange={(value) => setDocument({ ...draft, validation: { ...draft.validation, max_json_bytes: value } })} />
      <NumberSetting id="max-json-depth" label="Maximum JSON depth" help="Maximum nesting depth for evidence JSON." value={draft.validation.max_json_depth} onChange={(value) => setDocument({ ...draft, validation: { ...draft.validation, max_json_depth: value } })} />
      <NumberSetting id="max-json-keys" label="Maximum JSON keys" help="Maximum aggregate object keys in an evidence document." value={draft.validation.max_json_keys} onChange={(value) => setDocument({ ...draft, validation: { ...draft.validation, max_json_keys: value } })} />
      <Input id="gtin-lengths" label="Allowed GTIN lengths" title="Comma-separated exact GTIN lengths accepted by asset validation." value={draft.validation.gtin_lengths.join(', ')} onChange={(event) => setDocument({ ...draft, validation: { ...draft.validation, gtin_lengths: splitNumbers(event.target.value) } })} />
      <NumberSetting id="page-size" label="Default list page size" help="Number of records requested by list pages." value={draft.list_policy.default_page_size} onChange={(value) => setDocument({ ...draft, list_policy: { ...draft.list_policy, default_page_size: value } })} />
      <NumberSetting id="max-page-size" label="Maximum list page size" help="Tenant limit bounded by the platform ceiling." value={draft.list_policy.max_page_size} onChange={(value) => setDocument({ ...draft, list_policy: { ...draft.list_policy, max_page_size: value } })} />
      <NumberSetting id="confirmation-default" label="Default confirmations" help="Default finality depth for newly configured networks." value={draft.network_policy.default_confirmation_depth} onChange={(value) => setDocument({ ...draft, network_policy: { ...draft.network_policy, default_confirmation_depth: value } })} />
      <NumberSetting id="confirmation-max" label="Maximum confirmations" help="Highest finality depth that operators may save." value={draft.network_policy.max_confirmation_depth} onChange={(value) => setDocument({ ...draft, network_policy: { ...draft.network_policy, max_confirmation_depth: value } })} />
      <Input id="schema-versions" label="Allowed event schema versions" title="Comma-separated allow-list; an empty list is invalid." value={draft.schema_policy.allowed_versions.join(', ')} onChange={(event) => setDocument({ ...draft, schema_policy: { ...draft.schema_policy, allowed_versions: splitNumbers(event.target.value) } })} />
    </div></section>

    <section className="grid gap-4 lg:grid-cols-2"><Card className="space-y-4 p-5"><h2 className="font-semibold">Feature flags and phased rollout</h2><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.features.enabled} disabled={!capabilities.data.can_update} onChange={(event) => setFeature('enabled', event.target.checked)} />Enable traceability capability</label><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.features.enable_supersede} disabled={!draft.features.enabled || !capabilities.data.can_update} onChange={(event) => setFeature('enable_supersede', event.target.checked)} />Enable compliance supersession workflow</label><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.features.enable_health} disabled={!draft.features.enabled || !capabilities.data.can_update} onChange={(event) => setFeature('enable_health', event.target.checked)} />Enable dependency health console</label><Input id="rollout-roles" label="Allowed roles" title="Comma-separated role allow-list for progressive activation." disabled={!draft.features.enabled} value={draft.features.roles.join(', ')} onChange={(event) => setFeature('roles', splitStrings(event.target.value))} /><Input id="rollout-cohorts" label="Allowed cohorts" title="Comma-separated cohort allow-list for phased rollout." disabled={!draft.features.enabled} value={draft.features.cohorts.join(', ')} onChange={(event) => setFeature('cohorts', splitStrings(event.target.value))} /></Card>
      <Card className="space-y-4 p-5"><h2 className="font-semibold">Resilient provider execution</h2><NumberSetting id="provider-timeout" label="Provider timeout (seconds)" help="Explicit deadline for every external provider operation." value={draft.resilience.timeout_seconds} onChange={(value) => setDocument({ ...draft, resilience: { ...draft.resilience, timeout_seconds: value } })} /><NumberSetting id="provider-attempts" label="Maximum attempts" help="Bounded attempts including the initial provider call." value={draft.resilience.max_attempts} onChange={(value) => setDocument({ ...draft, resilience: { ...draft.resilience, max_attempts: value } })} /><NumberSetting id="backoff-base" label="Base backoff (seconds)" help="Initial exponential backoff before jitter." value={draft.resilience.base_backoff_seconds} onChange={(value) => setDocument({ ...draft, resilience: { ...draft.resilience, base_backoff_seconds: value } })} /><NumberSetting id="backoff-max" label="Maximum backoff (seconds)" help="Upper bound for exponential backoff." value={draft.resilience.max_backoff_seconds} onChange={(value) => setDocument({ ...draft, resilience: { ...draft.resilience, max_backoff_seconds: value } })} /></Card></section>

    {limitsInvalid && <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive" role="alert">Configuration contains an unsafe bound or empty allow-list. Preview and save are disabled.</p>}
    <Card className="grid gap-4 p-5 md:grid-cols-2"><div className="md:col-span-2"><h2 className="font-semibold">Operator experience</h2><p className="text-xs text-muted-foreground">Navigation, workflow defaults, and status semantics are runtime configuration—not source literals.</p></div><NumberSetting id="sidebar-order" label="Sidebar order" help="Positions this module among tenant navigation branches." value={draft.ui.sidebar_order} onChange={(value) => setDocument({ ...draft, ui: { ...draft.ui, sidebar_order: value } })} /><Input id="recall-reason" label="Default recall reason" title="Operator-editable default sent with recall transitions." value={draft.ui.default_recall_reason} onChange={(event) => setDocument({ ...draft, ui: { ...draft.ui, default_recall_reason: event.target.value } })} /><Input id="revocation-reason" label="Default revocation reason" title="Operator-editable default sent with credential revocation." value={draft.ui.default_revocation_reason} onChange={(event) => setDocument({ ...draft, ui: { ...draft.ui, default_revocation_reason: event.target.value } })} /><Input id="positive-statuses" label="Positive status tokens" title="Comma-separated statuses rendered with the semantic success treatment." value={draft.ui.positive_statuses.join(', ')} onChange={(event) => setDocument({ ...draft, ui: { ...draft.ui, positive_statuses: splitStrings(event.target.value) } })} /><Input id="warning-statuses" label="Warning status tokens" title="Comma-separated statuses rendered with the semantic warning treatment." value={draft.ui.warning_statuses.join(', ')} onChange={(event) => setDocument({ ...draft, ui: { ...draft.ui, warning_statuses: splitStrings(event.target.value) } })} /></Card>
    <Card className="p-5"><h2 className="font-semibold">Complete portable document</h2><p className="mt-1 text-xs text-muted-foreground">Advanced workflow machines, retention rules, health thresholds, navigation order, status presentation, and operational policies remain editable through this typed API document.</p><Textarea id="configuration-document" label="Configuration JSON" className="mt-4 min-h-96 font-mono text-xs" value={source} error={sourceError ?? undefined} onChange={(event) => { const value = event.target.value; setSource(value); setPreviewedSource(null); try { setDraft(parseImportedDocument(value)); setSourceError(null); } catch (error) { setSourceError(error instanceof Error ? error.message : 'Configuration JSON is invalid.'); } }} /></Card>

    {preview.data && <Card className="p-5" aria-live="polite"><h2 className="font-semibold">Server preview</h2><p className="mt-2 text-sm text-muted-foreground">{preview.data.changes.length} validated change(s). Save is enabled only while this exact normalized document remains unchanged.</p>{preview.data.changes.length === 0 ? <p className="mt-3 text-sm">No changes from the active version.</p> : <ul className="mt-3 space-y-2 text-sm">{preview.data.changes.map((change) => <li key={change.path} className="rounded-md bg-muted p-2"><code>{change.path}</code>: {JSON.stringify(change.before)} → {JSON.stringify(change.after)}</li>)}</ul>}</Card>}

    <section className="grid gap-4 lg:grid-cols-2"><Card className="p-5"><h2 className="font-semibold">Import</h2><p className="mt-1 text-xs text-muted-foreground">Paste an exported configuration or a bare configuration document. The service validates it before creating a version.</p><Textarea id="configuration-import" label="Import JSON" className="mt-4 min-h-48 font-mono text-xs" value={importSource} onChange={(event) => setImportSource(event.target.value)} /><Button className="mt-4" variant="outline" disabled={!capabilities.data.can_import || !importSource.trim() || importMutation.isPending} onClick={() => importMutation.mutate()}><Upload className="mr-2 h-4 w-4" />Import document</Button></Card>
      <Card className="p-5"><h2 className="font-semibold">Immutable version history and rollback</h2>{history.isLoading ? <p className="mt-4 text-sm" role="status">Loading history…</p> : history.error ? <div className="mt-4"><ApiProblem error={history.error} mutation onRetry={() => { void history.refetch(); }} /></div> : history.data?.length ? <div className="mt-4 max-h-80 space-y-3 overflow-auto">{history.data.map((version) => <div key={version.version} className="flex items-start justify-between gap-4 rounded-md border p-3"><div><strong>Version {version.version}</strong><p className="text-xs text-muted-foreground">{version.change_type} · {new Date(version.created_at).toLocaleString()}</p><p className="font-mono text-xs text-muted-foreground">{version.created_by} · {version.correlation_id}</p></div><Button size="sm" variant="outline" disabled={!capabilities.data.can_rollback || version.version === configuration.data.version || rollback.isPending} onClick={() => rollback.mutate(version.version)}><RotateCcw className="mr-1 h-4 w-4" />Rollback</Button></div>)}</div> : <div className="mt-4"><EmptyPanel title="No configuration history" description="The active configuration has no prior version available for rollback." /></div>}</Card></section>

    <Card className="p-5"><h2 className="flex items-center gap-2 font-semibold"><HeartPulse className="h-5 w-5" />Dependency health</h2>{!healthEnabled ? <p className="mt-3 text-sm text-muted-foreground">Health visibility is disabled by the active tenant feature policy.</p> : health.isLoading ? <p className="mt-3 text-sm" role="status">Checking dependencies…</p> : health.error ? <div className="mt-4"><ApiProblem error={health.error} mutation onRetry={() => { void health.refetch(); }} /></div> : health.data ? <div className="mt-4 space-y-3" aria-live="polite"><ConfiguredStatusPill status={health.data.status} />{health.data.dependencies.length === 0 ? <EmptyPanel title="No health dependencies reported" description="The service returned an empty dependency inventory; no healthy state has been assumed." /> : <ul className="grid gap-2 md:grid-cols-2">{health.data.dependencies.map((dependency) => <li key={dependency.name} className="flex items-center justify-between rounded-md border p-3"><div><strong className="text-sm">{dependency.name}</strong><p className="text-xs text-muted-foreground">{dependency.code} · {new Date(dependency.checked_at).toLocaleString()}</p></div><ConfiguredStatusPill status={dependency.status} /></li>)}</ul>}</div> : null}</Card>
  </main>;
}
