import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, RotateCcw, Save, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type {
  MonitoringConfigurationDocument,
  MonitoringConfigurationEnvironment,
  MonitoringConfigurationExport,
  MonitoringConfigurationVersion,
} from '../contracts';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import { MonitoringPage, OperationalError, PageSkeleton, formatTime } from '../components/MonitoringPage';

const splitList = (value: string): readonly string[] => value.split(',').map((entry) => entry.trim()).filter(Boolean);
const fingerprint = (document: MonitoringConfigurationDocument): string => JSON.stringify(document);

function downloadConfiguration(value: MonitoringConfigurationExport): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `performance-monitoring-${value.environment}-v${value.exported_version}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function parseImport(value: string): MonitoringConfigurationExport {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !('document' in parsed) || !('environment' in parsed)) {
    throw new Error('Import must be an exported performance-monitoring configuration document.');
  }
  return parsed as MonitoringConfigurationExport;
}

// This page deliberately coordinates the complete governed configuration lifecycle.
// eslint-disable-next-line complexity
export function MonitoringConfigurationPage() {
  const queryClient = useQueryClient();
  const [environment, setEnvironment] = useState<MonitoringConfigurationEnvironment>('default');
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', environment], queryFn: () => performanceMonitoringService.getConfiguration(environment) });
  const history = useQuery({ queryKey: ['performance-monitoring', 'configuration', environment, 'history'], queryFn: () => performanceMonitoringService.listConfigurationHistory(environment) });
  const audit = useQuery({ queryKey: ['performance-monitoring', 'configuration', environment, 'audit'], queryFn: () => performanceMonitoringService.listConfigurationAudit(environment) });
  const [draft, setDraft] = useState<MonitoringConfigurationDocument | null>(null);
  const [rawDocument, setRawDocument] = useState('');
  const [rawError, setRawError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [importSource, setImportSource] = useState('');
  const [previewedFingerprint, setPreviewedFingerprint] = useState<string | null>(null);
  useEffect(() => {
    if (!configuration.data) return;
    setDraft(configuration.data.document);
    setRawDocument(JSON.stringify(configuration.data.document, null, 2));
    setRawError(null);
    setPreviewedFingerprint(null);
  }, [configuration.data]);
  const currentFingerprint = useMemo(() => draft ? fingerprint(draft) : '', [draft]);
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['performance-monitoring', 'configuration', environment] }),
      queryClient.invalidateQueries({ queryKey: ['performance-monitoring', 'configuration', environment, 'history'] }),
      queryClient.invalidateQueries({ queryKey: ['performance-monitoring', 'configuration', environment, 'audit'] }),
    ]);
  };
  const request = () => ({ document: draft!, environment, expected_version: configuration.data!.version, change_reason: reason.trim() });
  const preview = useMutation({ mutationFn: () => performanceMonitoringService.previewConfiguration(request()), onSuccess: (result) => { setDraft(result.proposed_document); setRawDocument(JSON.stringify(result.proposed_document, null, 2)); setPreviewedFingerprint(fingerprint(result.proposed_document)); } });
  const save = useMutation({ mutationFn: () => performanceMonitoringService.updateConfiguration(request()), onSuccess: async () => { toast.success('Configuration version saved'); setReason(''); setPreviewedFingerprint(null); await refresh(); } });
  const rollback = useMutation({ mutationFn: (version: MonitoringConfigurationVersion) => performanceMonitoringService.rollbackConfiguration({ version: version.version, environment, expected_version: configuration.data!.version, change_reason: reason.trim() }), onSuccess: async () => { toast.success('Configuration rolled back as a new version'); setReason(''); await refresh(); } });
  const importMutation = useMutation({ mutationFn: () => { const portable = parseImport(importSource); return performanceMonitoringService.importConfiguration({ document: portable.document, environment, expected_version: configuration.data!.version, change_reason: reason.trim() }); }, onSuccess: async () => { toast.success('Configuration imported'); setImportSource(''); setReason(''); await refresh(); } });
  const exportMutation = useMutation({ mutationFn: () => performanceMonitoringService.exportConfiguration(environment), onSuccess: downloadConfiguration });
  const updateDraft = (next: MonitoringConfigurationDocument) => { setDraft(next); setRawDocument(JSON.stringify(next, null, 2)); setRawError(null); setPreviewedFingerprint(null); };

  if (configuration.isPending) return <MonitoringPage title="Performance monitoring configuration" description="Tenant-owned monitoring behavior, safe limits and rollout controls."><PageSkeleton /></MonitoringPage>;
  if (configuration.isError || !configuration.data || !draft) return <MonitoringPage title="Performance monitoring configuration" description="Tenant-owned monitoring behavior, safe limits and rollout controls."><OperationalError error={configuration.error} onRetry={() => { void configuration.refetch(); }} /></MonitoringPage>;
  const operationError = preview.error ?? save.error ?? rollback.error ?? importMutation.error ?? exportMutation.error ?? history.error ?? audit.error;
  const canSave = Boolean(reason.trim()) && !rawError && previewedFingerprint === currentFingerprint && !save.isPending;
  const source = draft.defaults.telemetry_source;
  const limits = draft.limits;

  return <MonitoringPage title="Performance monitoring configuration" description="Preview, version, audit, roll back and port every tenant monitoring setting without a deployment." actions={<><select aria-label="Configuration environment" className="h-10 rounded-md border bg-background px-3 text-sm" value={environment} onChange={(event) => setEnvironment(event.target.value)}>{['default', 'development', 'self-hosted', 'saas'].map((value) => <option key={value}>{value}</option>)}</select><Button variant="outline" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button><Button variant="outline" disabled={preview.isPending || Boolean(rawError)} onClick={() => preview.mutate()}>{preview.isPending ? 'Validating…' : 'Preview'}</Button><Button disabled={!canSave} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4" />Save version</Button></>}>
    {operationError ? <OperationalError error={operationError} onRetry={() => { preview.reset(); save.reset(); rollback.reset(); importMutation.reset(); void history.refetch(); void audit.refetch(); }} /> : null}
    <Card><CardContent className="flex flex-wrap gap-x-6 gap-y-2 p-4 text-sm"><strong>Version {configuration.data.version}</strong><span>Environment {configuration.data.environment}</span><span className="font-mono text-xs text-muted-foreground">Correlation {configuration.data.correlation_id}</span></CardContent></Card>

    <section className="space-y-4" aria-labelledby="defaults-title"><div><h2 id="defaults-title" className="text-xl font-semibold">Defaults and safe limits</h2><p className="text-sm text-muted-foreground">Inputs expose the authoritative server bounds; preview performs the same validation before save is enabled.</p></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <ConfigNumber label="Sampling rate" title="Fraction of telemetry events retained at ingestion." min={limits.sampling_rate_min} max={limits.sampling_rate_max} step={0.0001} value={source.sampling_rate} onChange={(value) => updateDraft({ ...draft, defaults: { ...draft.defaults, telemetry_source: { ...source, sampling_rate: value } } })} />
      <ConfigNumber label="Retention days" title="Tenant retention for new telemetry sources." min={limits.retention_days_min} max={limits.retention_days_max} value={source.retention_days} onChange={(value) => updateDraft({ ...draft, defaults: { ...draft.defaults, telemetry_source: { ...source, retention_days: value } } })} />
      <ConfigNumber label="Daily event quota" title="Maximum accepted telemetry events per source per day." min={limits.daily_event_quota_min} max={limits.daily_event_quota_max} value={source.daily_event_quota} onChange={(value) => updateDraft({ ...draft, defaults: { ...draft.defaults, telemetry_source: { ...source, daily_event_quota: value } } })} />
      <ConfigNumber label="Dashboard service rows" title="Maximum service rows shown on the overview." min={1} max={draft.pagination.max_page_size} value={draft.defaults.dashboard.service_list_limit} onChange={(value) => updateDraft({ ...draft, defaults: { ...draft.defaults, dashboard: { ...draft.defaults.dashboard, service_list_limit: value } } })} />
      <ConfigNumber label="Dashboard alert rows" title="Maximum incident rows shown on the overview." min={1} max={draft.pagination.max_page_size} value={draft.defaults.dashboard.alert_list_limit} onChange={(value) => updateDraft({ ...draft, defaults: { ...draft.defaults, dashboard: { ...draft.defaults.dashboard, alert_list_limit: value } } })} />
      <ConfigNumber label="Global stale threshold (minutes)" title="Age after which a source is reported stale in the overview." min={1} max={limits.retention_days_max * 1440} value={draft.query.global_stale_threshold_minutes} onChange={(value) => updateDraft({ ...draft, query: { ...draft.query, global_stale_threshold_minutes: value } })} />
      <ConfigNumber label="Metric stale cadence multiplier" title="Expected-cadence multiplier used to flag a metric series stale." min={1} max={100} step={0.1} value={draft.query.metric_stale_interval_multiplier} onChange={(value) => updateDraft({ ...draft, query: { ...draft.query, metric_stale_interval_multiplier: value } })} />
      <label className="text-sm font-medium" title="Attributes removed from newly registered telemetry sources.">Default redaction fields<Input className="mt-1" value={source.redaction_fields.join(', ')} onChange={(event) => updateDraft({ ...draft, defaults: { ...draft.defaults, telemetry_source: { ...source, redaction_fields: splitList(event.target.value) } } })} /></label>
    </div></section>

    <section className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle>Feature rollout</CardTitle></CardHeader><CardContent className="space-y-4"><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.rollout.enabled} onChange={(event) => updateDraft({ ...draft, rollout: event.target.checked ? { ...draft.rollout, enabled: true } : { ...draft.rollout, enabled: false, percentage: 0, roles: [], cohorts: [] } })} />Enable monitoring capability</label><ConfigNumber label="Rollout percentage" title="Percentage of eligible tenant users receiving this capability." min={0} max={100} disabled={!draft.rollout.enabled} value={draft.rollout.percentage} onChange={(value) => updateDraft({ ...draft, rollout: value === 100 ? { ...draft.rollout, percentage: value, roles: [], cohorts: [] } : { ...draft.rollout, percentage: value } })} /><label className="text-sm font-medium">Roles<Input className="mt-1" disabled={!draft.rollout.enabled || draft.rollout.percentage === 100} value={draft.rollout.roles.join(', ')} onChange={(event) => updateDraft({ ...draft, rollout: { ...draft.rollout, roles: splitList(event.target.value) } })} /></label><label className="text-sm font-medium">Cohorts<Input className="mt-1" disabled={!draft.rollout.enabled || draft.rollout.percentage === 100} value={draft.rollout.cohorts.join(', ')} onChange={(event) => updateDraft({ ...draft, rollout: { ...draft.rollout, cohorts: splitList(event.target.value) } })} /></label><p className="text-xs text-muted-foreground">Role and cohort targeting applies only to partial rollouts. Disabling the feature clears targeting so contradictory states are unreachable.</p></CardContent></Card>
      <Card><CardHeader><CardTitle>Change control</CardTitle></CardHeader><CardContent><label className="text-sm font-medium">Change reason<textarea required className="mt-1 min-h-28 w-full rounded-md border bg-background p-3 text-sm" value={reason} onChange={(event) => setReason(event.target.value)} /></label><p className="mt-2 text-xs text-muted-foreground">Required for save, rollback and import. The server records the authenticated actor and request correlation ID.</p></CardContent></Card></section>

    {preview.data ? <Card aria-live="polite"><CardHeader><CardTitle>Validated preview</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">{preview.data.diff.length} change(s) · current version {preview.data.current_version} · applies without service restart</p><ul className="mt-3 max-h-64 space-y-2 overflow-auto text-sm">{preview.data.diff.map((change) => <li key={change.path} className="rounded-md bg-muted p-2"><code>{change.path}</code>: {JSON.stringify(change.before)} → {JSON.stringify(change.after)}</li>)}</ul></CardContent></Card> : null}

    <Card><CardHeader><CardTitle>Complete configuration document</CardTitle></CardHeader><CardContent><p className="mb-3 text-sm text-muted-foreground">Advanced operators can edit every allow-list, policy, resilience, health, evidence, pagination, visual-token and query setting. Unknown or missing keys fail server validation.</p><textarea aria-label="Complete configuration JSON" className="min-h-[28rem] w-full rounded-md border bg-background p-4 font-mono text-xs" value={rawDocument} onChange={(event) => { const value = event.target.value; setRawDocument(value); setPreviewedFingerprint(null); try { const parsed: unknown = JSON.parse(value); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Configuration must be a JSON object.'); setDraft(parsed as MonitoringConfigurationDocument); setRawError(null); } catch (error) { setRawError(error instanceof Error ? error.message : 'Invalid JSON'); } }} />{rawError ? <p className="mt-2 text-sm text-destructive" role="alert">{rawError}</p> : null}</CardContent></Card>

    <section className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle>Import configuration</CardTitle></CardHeader><CardContent><textarea aria-label="Imported configuration JSON" className="min-h-48 w-full rounded-md border bg-background p-3 font-mono text-xs" value={importSource} onChange={(event) => setImportSource(event.target.value)} /><Button className="mt-3" variant="outline" disabled={!reason.trim() || !importSource.trim() || importMutation.isPending} onClick={() => importMutation.mutate()}><Upload className="mr-2 h-4 w-4" />Validate and import</Button></CardContent></Card><Card><CardHeader><CardTitle>Version history and rollback</CardTitle></CardHeader><CardContent className="max-h-72 space-y-3 overflow-auto">{history.isPending ? <p role="status" className="text-sm text-muted-foreground">Loading version history…</p> : history.data?.length ? history.data.map((version) => <div key={version.id} className="flex items-center justify-between gap-4 rounded-md border p-3"><div><strong>Version {version.version}</strong><p className="text-xs text-muted-foreground">{version.change_reason} · {formatTime(version.created_at)}</p><p className="font-mono text-xs text-muted-foreground">{version.correlation_id}</p></div><Button size="sm" variant="outline" disabled={!reason.trim() || version.version === configuration.data.version || rollback.isPending} onClick={() => rollback.mutate(version)}><RotateCcw className="mr-1 h-4 w-4" />Rollback</Button></div>) : <p className="text-sm text-muted-foreground">No historical versions exist.</p>}</CardContent></Card></section>

    <Card><CardHeader><CardTitle>Immutable audit history</CardTitle></CardHeader><CardContent className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b"><th className="p-2">Action</th><th className="p-2">Version</th><th className="p-2">Actor</th><th className="p-2">Changed</th><th className="p-2">Correlation ID</th></tr></thead><tbody>{audit.isPending ? <tr><td colSpan={5} className="p-3 text-muted-foreground">Loading audit evidence…</td></tr> : audit.data?.map((record) => <tr key={record.id} className="border-b"><td className="p-2 capitalize">{record.action}</td><td className="p-2">{record.from_version ?? 'none'} → {record.to_version}</td><td className="p-2 font-mono text-xs">{record.actor_id}</td><td className="p-2">{formatTime(record.created_at)}</td><td className="p-2 font-mono text-xs">{record.correlation_id}</td></tr>)}</tbody></table></CardContent></Card>
  </MonitoringPage>;
}

function ConfigNumber({ label, title, value, min, max, step = 1, disabled = false, onChange }: { label: string; title: string; value: number; min: number; max: number; step?: number; disabled?: boolean; onChange: (value: number) => void }) {
  return <label className="text-sm font-medium" title={title}>{label}<Input className="mt-1" type="number" value={value} min={min} max={max} step={step} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} /><span className="mt-1 block text-xs font-normal text-muted-foreground">Allowed: {min}–{max}</span></label>;
}
