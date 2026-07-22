import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, RotateCcw, Save, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import type { ConfigurationExport, ProcessMiningConfigurationDocument } from '../contracts';
import { ApiProblem, DataTable, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { processMiningService } from '../services/process_mining-service';

const INTEGER_FIELDS = [
  'max_batch_events', 'max_export_events', 'max_export_bytes', 'max_conformance_events', 'text_max_length',
  'attributes_max_bytes', 'source_module_max_length', 'max_event_age_days', 'future_clock_skew_seconds',
  'bulk_insert_batch_size', 'event_query_max_days', 'retention_days', 'retention_min_days',
  'export_projection_bytes_per_event', 'export_iterator_chunk_size', 'checksum_chunk_bytes', 'export_expiry_days',
  'discovery_min_events', 'discovery_min_cases', 'alpha_max_activities', 'bottleneck_reuse_minutes',
  'bottleneck_min_cases', 'outbox_freshness_seconds', 'default_time_window_days', 'list_page_size',
  'detail_page_size', 'polling_interval_ms', 'download_timeout_ms', 'download_retry_attempts',
  'download_retry_base_ms', 'download_circuit_failure_threshold', 'download_circuit_reset_ms',
  'visual_canvas_width', 'visual_canvas_height', 'visual_node_width', 'visual_node_height', 'visual_layout_columns',
  'visual_horizontal_gap', 'visual_vertical_gap', 'visual_layout_padding',
] as const satisfies readonly (keyof ProcessMiningConfigurationDocument)[];

const DECIMAL_FIELDS = [
  'heuristic_default_threshold', 'inductive_default_threshold', 'algorithm_threshold_min',
  'algorithm_threshold_step',
  'algorithm_threshold_max', 'low_fitness_threshold', 'bottleneck_critical_ratio', 'bottleneck_high_ratio',
  'bottleneck_medium_ratio', 'tail_duration_percentile', 'resource_concentration_threshold',
  'variant_grouping_percentage', 'visual_zoom_min', 'visual_zoom_max', 'visual_zoom_step',
  'visual_edge_width_min', 'visual_edge_width_max', 'visual_frequency_divisor', 'visual_duration_divisor',
] as const satisfies readonly (keyof ProcessMiningConfigurationDocument)[];

const label = (name: string) => name.replaceAll('_', ' ');

export function ConfigurationPage() {
  const client = useQueryClient();
  const configuration = useQuery({ queryKey: ['process-mining', 'configuration'], queryFn: processMiningService.getConfiguration });
  const history = useQuery({ queryKey: ['process-mining', 'configuration-history'], queryFn: () => processMiningService.configurationHistory() });
  const health = useQuery({ queryKey: ['process-mining', 'health'], queryFn: processMiningService.health });
  const [draft, setDraft] = useState<ProcessMiningConfigurationDocument | null>(null);
  const [importText, setImportText] = useState('');
  useEffect(() => { if (configuration.data) setDraft(structuredClone(configuration.data.document)); }, [configuration.data]);
  const dependencyError = useMemo(() => {
    if (!draft) return '';
    if (draft.retention_days < draft.retention_min_days) return 'Retention days must be at least the configured minimum.';
    if (draft.algorithm_threshold_min >= draft.algorithm_threshold_max) return 'Algorithm threshold maximum must exceed its minimum.';
    if (draft.visual_zoom_min >= draft.visual_zoom_max) return 'Visual zoom maximum must exceed its minimum.';
    if (!(draft.bottleneck_critical_ratio > draft.bottleneck_high_ratio && draft.bottleneck_high_ratio > draft.bottleneck_medium_ratio)) return 'Bottleneck severity ratios must descend from critical to medium.';
    return '';
  }, [draft]);
  const preview = useMutation({ mutationFn: (value: ProcessMiningConfigurationDocument) => processMiningService.previewConfiguration(value) });
  const save = useMutation({ mutationFn: (value: ProcessMiningConfigurationDocument) => processMiningService.updateConfiguration(value), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['process-mining', 'configuration'] }); await client.invalidateQueries({ queryKey: ['process-mining', 'configuration-history'] }); } });
  const rollback = useMutation({ mutationFn: (version: number) => processMiningService.rollbackConfiguration(version), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['process-mining', 'configuration'] }); await client.invalidateQueries({ queryKey: ['process-mining', 'configuration-history'] }); } });
  const importMutation = useMutation({ mutationFn: (value: ConfigurationExport) => processMiningService.importConfiguration(value), onSuccess: async () => { setImportText(''); await client.invalidateQueries({ queryKey: ['process-mining', 'configuration'] }); await client.invalidateQueries({ queryKey: ['process-mining', 'configuration-history'] }); } });
  const exportMutation = useMutation({ mutationFn: processMiningService.exportConfiguration, onSuccess: (value) => { const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `process-mining-configuration-v${value.version}.json`; anchor.click(); URL.revokeObjectURL(url); } });
  if (configuration.error) return <main className="p-4 sm:p-8"><ApiProblem error={configuration.error} onRetry={() => void configuration.refetch()}/></main>;
  if (configuration.isLoading || !configuration.data || !draft) return <PageSkeleton/>;
  const activeConfiguration = configuration.data;
  const setNumber = (field: keyof ProcessMiningConfigurationDocument, value: string) => setDraft((current) => current ? ({ ...current, [field]: Number(value) }) : current);
  const setList = (field: 'forbidden_attribute_keys' | 'rollout_roles' | 'rollout_cohorts' | 'analysis_terminal_states' | 'export_terminal_states', value: string) => setDraft((current) => current ? ({ ...current, [field]: value.split(',').map((item) => item.trim()).filter(Boolean) }) : current);
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title="Process mining configuration" description="Versioned tenant policy. Every change is server-validated, previewable, audited with correlation evidence, and reversible." actions={<><Button variant="outline" onClick={() => exportMutation.mutate()}><Download className="mr-2 h-4 w-4"/>Export</Button><Button disabled={Boolean(dependencyError) || save.isPending} onClick={() => save.mutate(draft)}><Save className="mr-2 h-4 w-4"/>Save version</Button></>}/>
    {(save.error || preview.error || importMutation.error || rollback.error) && <ApiProblem error={save.error ?? preview.error ?? importMutation.error ?? rollback.error} onRetry={() => { save.reset(); preview.reset(); importMutation.reset(); rollback.reset(); }}/>} 
    <Card className="p-6"><div className="grid gap-4 sm:grid-cols-3"><label className="text-sm font-medium" title="Separates environment values while preserving one code path.">Environment<select className="mt-1 block w-full rounded-md border bg-background p-2" value={draft.environment} onChange={(event) => setDraft({ ...draft, environment: event.target.value as ProcessMiningConfigurationDocument['environment'] })}><option value="default">Default</option><option value="development">Development</option><option value="self-hosted">Self-hosted</option><option value="saas">SaaS</option></select></label><label className="flex items-center gap-2 text-sm font-medium" title="Emergency feature flag for this tenant."><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}/>Capability enabled</label><p className="text-sm text-muted-foreground">Current version {activeConfiguration.version}<br/>Updated {new Date(activeConfiguration.updated_at).toLocaleString()}</p></div></Card>
    <Card className="p-6"><label className="text-sm font-medium" title="Default applied by discovery forms and validated by the server.">Default discovery algorithm<select className="ml-3 rounded-md border bg-background p-2" value={draft.default_discovery_algorithm} onChange={(event) => setDraft({ ...draft, default_discovery_algorithm: event.target.value as ProcessMiningConfigurationDocument['default_discovery_algorithm'] })}><option value="alpha_miner">Alpha miner</option><option value="heuristic_miner">Heuristic miner</option><option value="inductive_miner">Inductive miner</option></select></label></Card>
    <Card className="overflow-hidden"><div className="p-6"><h2 className="font-semibold">Dependency health</h2><p className="text-sm text-muted-foreground">Real readiness evidence; unavailable capabilities are never reported as successful.</p></div>{health.data ? <DataTable headers={['Dependency', 'Status', 'Code', 'Checked']} rows={health.data.dependencies.map((item) => [item.name, item.status, item.code, new Date(item.checked_at).toLocaleString()])}/> : <div className="p-6"><Button variant="outline" onClick={() => void health.refetch()}>Check health</Button></div>}</Card>
    <Card className="p-6"><h2 className="font-semibold">Limits, defaults, resilience, and visual controls</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[...INTEGER_FIELDS, ...DECIMAL_FIELDS].map((field) => <label key={field} className="text-sm font-medium capitalize" title={`Tenant setting: ${label(field)}. Server safe limits are authoritative.`}>{label(field)}<input className="mt-1 block w-full rounded-md border bg-background p-2" type="number" step={DECIMAL_FIELDS.includes(field as typeof DECIMAL_FIELDS[number]) ? 'any' : '1'} value={String(draft[field])} onChange={(event) => setNumber(field, event.target.value)} required/></label>)}</div>{dependencyError && <p role="alert" className="mt-4 text-sm text-destructive">{dependencyError}</p>}</Card>
    <Card className="p-6"><h2 className="font-semibold">Policy lists, rollout, and terminal states</h2><div className="mt-4 grid gap-4 lg:grid-cols-3">{(['forbidden_attribute_keys', 'rollout_roles', 'rollout_cohorts', 'analysis_terminal_states', 'export_terminal_states'] as const).map((field) => <label key={field} className="text-sm font-medium capitalize" title="Comma-separated policy values, audited as part of the versioned document.">{label(field)}<textarea className="mt-1 block min-h-24 w-full rounded-md border bg-background p-2" value={draft[field].join(', ')} onChange={(event) => setList(field, event.target.value)}/></label>)}</div></Card>
    <Card className="p-6"><h2 className="font-semibold">Workflow policy</h2><div className="mt-4 grid gap-4 lg:grid-cols-2">{(['analysis_transitions', 'export_transitions'] as const).map((field) => <label key={field} className="text-sm font-medium capitalize" title="Every supported state must be present; unsupported targets are rejected server-side.">{label(field)}<textarea className="mt-1 block min-h-64 w-full rounded-md border bg-background p-2 font-mono text-xs" value={JSON.stringify(draft[field], null, 2)} onChange={(event) => { try { const value: unknown = JSON.parse(event.target.value); if (typeof value === 'object' && value !== null) setDraft({ ...draft, [field]: value as Record<string, string[]> }); } catch { /* retain last valid workflow so invalid combinations are unsavable */ } }}/></label>)}</div></Card>
    <Card className="p-6"><div className="flex items-center justify-between"><div><h2 className="font-semibold">Dry-run preview</h2><p className="text-sm text-muted-foreground">Validate and inspect the exact diff before applying.</p></div><Button variant="outline" disabled={Boolean(dependencyError) || preview.isPending} onClick={() => preview.mutate(draft)}>Preview changes</Button></div>{preview.data && <pre className="mt-4 max-h-80 overflow-auto rounded bg-muted p-4 text-xs">{JSON.stringify(preview.data.changes, null, 2)}</pre>}</Card>
    <Card className="p-6"><h2 className="font-semibold">Import configuration document</h2><textarea className="mt-4 min-h-36 w-full rounded-md border bg-background p-3 font-mono text-xs" value={importText} onChange={(event) => setImportText(event.target.value)} placeholder="Paste an exported process_mining configuration document"/><Button className="mt-3" variant="outline" disabled={!importText.trim()} onClick={() => { try { importMutation.mutate(JSON.parse(importText) as ConfigurationExport); } catch { /* server mutation remains disabled until valid JSON */ } }}><Upload className="mr-2 h-4 w-4"/>Import as new version</Button></Card>
    <Card className="overflow-hidden"><div className="p-6"><h2 className="font-semibold">Immutable version history</h2><p className="text-sm text-muted-foreground">Rollback creates a new audited version; historical evidence is never modified.</p></div>{history.data && <DataTable headers={['Version', 'Source', 'Created', 'Correlation', 'Action']} rows={history.data.items.map((item) => [item.version, item.source, new Date(item.created_at).toLocaleString(), <span className="font-mono text-xs">{item.correlation_id}</span>, <Button size="sm" variant="outline" disabled={item.version === activeConfiguration.version || rollback.isPending} onClick={() => rollback.mutate(item.version)}><RotateCcw className="mr-1 h-3.5 w-3.5"/>Rollback</Button>])}/>}</Card>
  </main>;
}
