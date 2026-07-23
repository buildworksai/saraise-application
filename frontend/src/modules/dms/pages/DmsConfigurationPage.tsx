import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, History, RotateCcw, Save, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { useAuthStore } from '@/stores/auth-store';
import {
  type DmsConfigurationExportDocument,
  type DmsConfigurationValues,
  type DmsEnvironment,
  type DocumentOrdering,
} from '../contracts';
import { ApiProblem, MutationProblem, PageHeader, PageSkeleton, formatDate } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';

type NumericKey = {
  [Key in keyof DmsConfigurationValues]: DmsConfigurationValues[Key] extends number ? Key : never
}[keyof DmsConfigurationValues];

const numberFields = [
  ['max_folder_depth', 'Maximum folder depth', 'Deepest folder nesting accepted for this tenant.'],
  ['max_document_tags', 'Maximum tags per document', 'Prevents unbounded tag payloads.'],
  ['max_tag_length', 'Maximum tag length', 'Maximum characters accepted in one tag.'],
  ['max_metadata_bytes', 'Maximum metadata bytes', 'Serialized document metadata size limit.'],
  ['max_share_lifetime_days', 'Maximum share lifetime (days)', 'Upper bound for public share expiry.'],
  ['max_share_access_count', 'Maximum share downloads', 'Upper bound for limited public shares.'],
  ['principal_search_min_limit', 'Principal search minimum results', 'Smallest directory result page.'],
  ['principal_search_max_limit', 'Principal search maximum results', 'Largest directory result page.'],
  ['principal_search_default_limit', 'Principal search default results', 'Default directory result page.'],
  ['principal_query_min_length', 'Principal query minimum length', 'Characters required before directory search.'],
  ['principal_query_max_length', 'Principal query maximum length', 'Largest directory search query.'],
  ['max_name_length', 'Maximum name length', 'Folder and document name limit.'],
  ['max_metadata_key_length', 'Maximum metadata key length', 'Maximum searchable metadata property length.'],
  ['download_verification_chunk_size', 'Download verification chunk bytes', 'Streaming checksum verification chunk.'],
  ['max_document_search_length', 'Maximum document search length', 'Maximum full-text query length.'],
  ['share_token_entropy_bytes', 'Share token entropy bytes', 'Security entropy for newly issued bearer tokens.'],
  ['share_token_prefix_length', 'Share token display prefix', 'Non-secret prefix characters retained for identification.'],
  ['incoming_share_token_max_length', 'Incoming token maximum length', 'Rejects oversized public share tokens.'],
  ['metadata_namespace_max_length', 'Metadata namespace length', 'Extension namespace maximum length.'],
  ['max_upload_bytes', 'Maximum upload bytes', 'Per-document upload size ceiling.'],
  ['storage_stream_chunk_size', 'Storage stream chunk bytes', 'Storage transfer chunk size.'],
  ['content_inspection_window_bytes', 'Inspection window bytes', 'Leading content bytes inspected before storage.'],
  ['storage_key_max_length', 'Storage key maximum length', 'Maximum internal object key length.'],
  ['max_control_character_ratio_percent', 'Control character ratio (%)', 'Maximum text control-character ratio.'],
  ['min_control_characters', 'Minimum control characters', 'Minimum count used by the text-content heuristic.'],
  ['storage_backend_name_max_length', 'Backend name maximum length', 'Maximum configured storage adapter name.'],
  ['outbox_freshness_seconds', 'Outbox freshness seconds', 'Readiness threshold for unpublished events.'],
  ['collection_search_max_length', 'Collection query maximum length', 'Maximum folder/document collection query.'],
  ['tag_filter_max_tags', 'Maximum tag filters', 'Maximum tags accepted in one collection filter.'],
  ['tag_filter_max_length', 'Tag filter maximum length', 'Maximum characters in one tag filter.'],
  ['version_change_note_max_length', 'Version note maximum length', 'Maximum immutable version change-note length.'],
  ['api_read_quota', 'Monthly API read quota', 'Tenant read request allocation.'],
  ['api_write_quota', 'Monthly API write quota', 'Tenant mutation request allocation.'],
  ['storage_quota_bytes', 'Storage quota bytes', 'Total tenant document storage allocation.'],
  ['folder_page_size', 'Folder page size', 'Default folder collection page.'],
  ['document_page_size', 'Document page size', 'Default document collection page.'],
  ['max_page_size', 'Maximum page size', 'Hard tenant page-size ceiling.'],
  ['default_share_expiry_hours', 'Default share expiry hours', 'Initial share expiry shown to operators.'],
  ['default_share_access_count', 'Default share download count', 'Initial limited-share download count.'],
  ['text_preview_max_characters', 'Text preview characters', 'Maximum text rendered by the browser preview.'],
  ['upload_timeout_ms', 'Upload timeout (ms)', 'Explicit timeout for the governed upload transport.'],
  ['upload_max_retries', 'Upload retry count', 'Bounded retries using the same idempotency key.'],
  ['circuit_breaker_failure_threshold', 'Circuit failure threshold', 'Failures that open the upload circuit.'],
  ['circuit_breaker_reset_ms', 'Circuit reset window (ms)', 'Time before a guarded upload retry is allowed.'],
] as const satisfies readonly (readonly [NumericKey, string, string])[];

const arrayFields = [
  ['forbidden_name_characters', 'Forbidden name characters', 'Comma-separated characters rejected in names.'],
  ['blocked_file_signatures', 'Blocked file signatures', 'Comma-separated hexadecimal leading-byte signatures.'],
  ['permitted_mime_types', 'Permitted MIME types', 'Fail-closed allow-list; an empty list cannot be saved.'],
  ['executable_extensions', 'Blocked executable extensions', 'Comma-separated lowercase extensions including leading dots.'],
  ['governance_required_operations', 'Governed operations', 'Operations that require a configured governance evaluator.'],
] as const satisfies readonly (readonly [keyof DmsConfigurationValues, string, string])[];

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function csv(value: readonly string[]): string {
  return value.join(', ');
}

function csvValues(value: string): readonly string[] {
  return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))];
}

function draftProblem(values: DmsConfigurationValues | null): string | null {
  if (!values) return 'Configuration has not loaded.';
  if (numberFields.some(([key]) => !Number.isFinite(values[key]) || values[key] < 0)) return 'Numeric values must be finite and non-negative.';
  if (!(values.principal_search_min_limit <= values.principal_search_default_limit && values.principal_search_default_limit <= values.principal_search_max_limit)) return 'Principal search default must be between its minimum and maximum.';
  if (values.folder_page_size > values.max_page_size || values.document_page_size > values.max_page_size) return 'Folder and document page sizes cannot exceed the maximum page size.';
  if (values.default_share_access_count > values.max_share_access_count) return 'Default share downloads cannot exceed the maximum.';
  if (values.default_share_expiry_hours > values.max_share_lifetime_days * 24) return 'Default share expiry cannot exceed the configured lifetime.';
  if (!values.document_ordering_fields.includes(values.default_document_ordering)) return 'Default ordering must be included in the ordering allow-list.';
  if (values.permitted_mime_types.length === 0) return 'The MIME-type allow-list is fail-closed and cannot be empty.';
  return null;
}

// The page deliberately presents every server-owned value; no hidden source-only policy remains.
// eslint-disable-next-line complexity, max-lines-per-function
export function DmsConfigurationPage() {
  const client = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const canManage = user?.is_superuser === true || user?.is_staff === true || user?.tenant_role === 'tenant_admin';
  const fileInput = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] = useState<DmsEnvironment>('default');
  const current = useQuery({ queryKey: DMS_QUERY_KEYS.configuration(environment), queryFn: () => dmsService.getConfiguration(environment) });
  const history = useQuery({ queryKey: DMS_QUERY_KEYS.configurationHistory(environment), queryFn: () => dmsService.configurationHistory(environment) });
  const audit = useQuery({ queryKey: DMS_QUERY_KEYS.configurationAudit(environment), queryFn: () => dmsService.configurationAudit(environment) });
  const [draft, setDraft] = useState<DmsConfigurationValues | null>(null);
  const [previewFingerprint, setPreviewFingerprint] = useState<string | null>(null);
  useEffect(() => {
    if (!current.data) return;
    setEnvironment(current.data.environment);
    setDraft(current.data.values);
  }, [current.data]);
  const fingerprint = useMemo(() => draft ? JSON.stringify({ environment, values: draft }) : '', [draft, environment]);
  const invalid = draftProblem(draft);
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.configuration(environment) }),
      client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.configurationHistory(environment) }),
      client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.configurationAudit(environment) }),
    ]);
  };
  const preview = useMutation({
    mutationFn: () => dmsService.previewConfiguration({ environment, values: draft! }),
    onSuccess: (result) => {
      setDraft(result.normalized_values);
      setPreviewFingerprint(JSON.stringify({ environment, values: result.normalized_values }));
    },
  });
  const save = useMutation({
    mutationFn: () => dmsService.updateConfiguration({ environment, values: draft! }),
    onSuccess: async () => {
      toast.success('Configuration saved as an immutable version');
      setPreviewFingerprint(null);
      await refresh();
    },
  });
  const rollback = useMutation({
    mutationFn: (version: number) => dmsService.rollbackConfiguration(version, environment),
    onSuccess: async () => {
      toast.success('Rollback published as a new configuration version');
      setPreviewFingerprint(null);
      await refresh();
    },
  });
  const importConfiguration = useMutation({
    mutationFn: dmsService.importConfiguration,
    onSuccess: async () => {
      toast.success('Configuration imported as a new immutable version');
      setPreviewFingerprint(null);
      await refresh();
    },
  });
  const exportConfiguration = useMutation({
    mutationFn: () => dmsService.exportConfiguration(environment),
    onSuccess: (document) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' }));
      const link = globalThis.document.createElement('a');
      link.href = url;
      link.download = `dms-${document.environment}-v${document.version}.json`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
  const readImport = (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== 'string') return;
      try {
        const parsed: unknown = JSON.parse(reader.result);
        if (!isObject(parsed) || parsed.module !== 'dms' || !isObject(parsed.values) || typeof parsed.environment !== 'string' || typeof parsed.version !== 'number' || typeof parsed.schema_version !== 'number') {
          toast.error('The file is not a DMS configuration export document.');
          return;
        }
        importConfiguration.mutate(parsed as unknown as DmsConfigurationExportDocument);
      } catch {
        toast.error('The configuration file is not valid JSON.');
      }
    };
    reader.readAsText(file);
  };
  if (current.isLoading || history.isLoading || audit.isLoading) return <PageSkeleton/>;
  const queryError = current.error ?? history.error ?? audit.error;
  if (queryError) return <main className="p-4 sm:p-8"><ApiProblem error={queryError} onRetry={() => { void current.refetch(); void history.refetch(); void audit.refetch(); }}/></main>;
  if (!draft || !current.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('The governed DMS configuration response was empty.')}/></main>;
  const setNumber = (key: NumericKey, value: number) => { setDraft((existing) => existing ? { ...existing, [key]: value } : existing); setPreviewFingerprint(null); };
  const setArray = (key: typeof arrayFields[number][0], value: readonly string[]) => { setDraft((existing) => existing ? { ...existing, [key]: value } : existing); setPreviewFingerprint(null); };
  const mutationError = preview.error ?? save.error ?? rollback.error ?? importConfiguration.error ?? exportConfiguration.error;
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title="DMS configuration" description="Tenant-scoped, environment-specific policy. Every change is server-validated, previewed, versioned, audited with correlation evidence, portable, and reversible." actions={<><Button variant="outline" disabled={exportConfiguration.isPending} onClick={() => exportConfiguration.mutate()}><Download className="mr-2 h-4 w-4"/>Export</Button>{canManage ? <><Button variant="outline" onClick={() => fileInput.current?.click()} disabled={importConfiguration.isPending}><Upload className="mr-2 h-4 w-4"/>Import</Button><input ref={fileInput} className="sr-only" type="file" accept="application/json" onChange={(event) => readImport(event.target.files?.[0])}/><Button variant="outline" disabled={Boolean(invalid) || preview.isPending} onClick={() => preview.mutate()}><Eye className="mr-2 h-4 w-4"/>Preview</Button><Button disabled={Boolean(invalid) || previewFingerprint !== fingerprint || save.isPending} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4"/>Save version</Button></> : null}</>}/>
    {!canManage ? <div role="note" className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm text-warning-foreground">You have read-only configuration access. Tenant administrators can preview, import, save, and roll back versions.</div> : null}
    {mutationError ? <MutationProblem error={mutationError}/> : null}
    {invalid ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{invalid}</div> : null}
    <Card className="space-y-5 p-5">
      <div className="grid gap-4 md:grid-cols-3"><label className="text-sm font-medium">Environment<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={environment} disabled={!canManage} onChange={(event) => { setEnvironment(event.target.value as DmsEnvironment); setPreviewFingerprint(null); }}><option value="default">Default</option><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option></select></label><div><p className="text-sm font-medium">Active version</p><p className="mt-2 text-xl font-semibold">v{current.data.version}</p></div><div><p className="text-sm font-medium">Last updated</p><p className="mt-2 text-sm">{formatDate(current.data.updated_at)}</p></div></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{numberFields.map(([key, label, guidance]) => <Input key={key} label={label} title={guidance} type="number" min={0} value={draft[key]} disabled={!canManage} onChange={(event) => setNumber(key, Number(event.target.value))}/>)}</div>
    </Card>
    <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Workflows, integration, and allow-lists</h2><div className="grid gap-4 md:grid-cols-2"><Input label="Storage backend" title="Registered adapter name; credentials remain in the secret manager." maxLength={draft.storage_backend_name_max_length} value={draft.storage_backend} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, storage_backend: event.target.value }); setPreviewFingerprint(null); }}/><label className="text-sm font-medium">Folder deletion policy<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.folder_deletion_policy} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, folder_deletion_policy: event.target.value as DmsConfigurationValues['folder_deletion_policy'] }); setPreviewFingerprint(null); }}><option value="empty_only">Require an empty folder</option><option value="recursive_soft_delete">Recursively soft-delete contents</option></select></label><label className="text-sm font-medium">Default document ordering<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.default_document_ordering} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, default_document_ordering: event.target.value as DocumentOrdering }); setPreviewFingerprint(null); }}>{draft.document_ordering_fields.map((ordering) => <option key={ordering} value={ordering}>{ordering}</option>)}</select></label><Input label="Allowed document ordering fields" title="Comma-separated server ordering allow-list." value={csv(draft.document_ordering_fields)} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, document_ordering_fields: csvValues(event.target.value) as readonly DocumentOrdering[] }); setPreviewFingerprint(null); }}/>{arrayFields.map(([key, label, guidance]) => <Input key={key} label={label} title={guidance} value={csv(draft[key] as readonly string[])} disabled={!canManage} onChange={(event) => setArray(key, csvValues(event.target.value))}/>)}</div><Textarea label="Default restore note template" title="Audit note used when restoring an immutable document version." maxLength={draft.version_change_note_max_length} value={draft.restore_note_template} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, restore_note_template: event.target.value }); setPreviewFingerprint(null); }}/></Card>
    <Card className="space-y-4 p-5"><h2 className="text-lg font-semibold">Permission policy and phased rollout</h2><Textarea label="Permission implication policy (JSON)" title="Each permission maps to its implied capability levels; the server validates the safe allow-list." value={JSON.stringify(draft.permission_implications, null, 2)} disabled={!canManage} onChange={(event) => { try { const value: unknown = JSON.parse(event.target.value); if (isObject(value)) { setDraft({ ...draft, permission_implications: value as DmsConfigurationValues['permission_implications'] }); setPreviewFingerprint(null); } } catch { /* The prior valid value remains active and savable state cannot become invalid JSON. */ } }}/><Textarea label="Feature flags (JSON)" title="Tenant flags can be changed without deployment." value={JSON.stringify(draft.feature_flags, null, 2)} disabled={!canManage} onChange={(event) => { try { const value: unknown = JSON.parse(event.target.value); if (isObject(value)) { setDraft({ ...draft, feature_flags: value as Readonly<Record<string, boolean>> }); setPreviewFingerprint(null); } } catch { /* Preserve the last valid document. */ } }}/><div className="grid gap-4 md:grid-cols-3"><label className="text-sm font-medium">Rollout state<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={draft.rollout.enabled ? 'enabled' : 'disabled'} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, rollout: { ...draft.rollout, enabled: event.target.value === 'enabled' } }); setPreviewFingerprint(null); }}><option value="enabled">Enabled</option><option value="disabled">Disabled</option></select></label><Input label="Rollout roles" title="Comma-separated tenant roles included in the rollout." value={csv(draft.rollout.roles)} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, rollout: { ...draft.rollout, roles: csvValues(event.target.value) } }); setPreviewFingerprint(null); }}/><Input label="Rollout cohorts" title="Comma-separated tenant cohorts included in the rollout." value={csv(draft.rollout.cohorts)} disabled={!canManage} onChange={(event) => { setDraft({ ...draft, rollout: { ...draft.rollout, cohorts: csvValues(event.target.value) } }); setPreviewFingerprint(null); }}/></div></Card>
    {preview.data ? <Card className="p-5"><h2 className="font-semibold">Server preview</h2><p className="mt-1 text-sm text-muted-foreground">{preview.data.changes.length} field change{preview.data.changes.length === 1 ? '' : 's'} · {preview.data.restart_required ? 'A restart is required and will be coordinated.' : 'Applies without service restart.'}</p>{preview.data.changes.length ? <ul className="mt-4 divide-y">{preview.data.changes.map((change) => <li className="grid gap-2 py-3 text-sm md:grid-cols-[220px_1fr_1fr]" key={change.field}><strong>{change.field}</strong><code className="break-all text-muted-foreground">{JSON.stringify(change.before)}</code><code className="break-all text-primary">{JSON.stringify(change.after)}</code></li>)}</ul> : <p className="mt-4 text-sm">No changes from the active version.</p>}</Card> : null}
    <div className="grid gap-5 xl:grid-cols-2"><Card className="overflow-hidden"><div className="border-b p-4"><h2 className="flex items-center font-semibold"><History className="mr-2 h-4 w-4"/>Version history</h2></div>{history.data?.items.length ? <ol className="divide-y">{history.data.items.map((version) => <li className="flex items-center justify-between gap-4 p-4" key={version.id}><div><p className="font-medium">Version {version.version}</p><p className="text-xs text-muted-foreground">{version.environment} · {formatDate(version.created_at)} · actor {version.created_by}</p><p className="break-all font-mono text-xs text-muted-foreground">Correlation {version.correlation_id}</p></div>{canManage && version.version !== current.data.version ? <Button size="sm" variant="outline" disabled={rollback.isPending} onClick={() => { if (window.confirm(`Publish version ${version.version} as a new rollback version? Immutable history will be retained.`)) rollback.mutate(version.version); }}><RotateCcw className="mr-1 h-4 w-4"/>Rollback</Button> : null}</li>)}</ol> : <p className="p-5 text-sm text-muted-foreground">No prior configuration versions.</p>}</Card><Card className="overflow-hidden"><div className="border-b p-4"><h2 className="font-semibold">Immutable audit evidence</h2></div>{audit.data?.items.length ? <ol className="divide-y">{audit.data.items.map((record) => <li className="p-4" key={record.id}><p className="font-medium">{record.action} · version {record.to_version}</p><p className="mt-1 text-xs text-muted-foreground">{formatDate(record.created_at)} · actor {record.actor_id}</p><p className="mt-1 break-all font-mono text-xs text-muted-foreground">Correlation {record.correlation_id}</p></li>)}</ol> : <p className="p-5 text-sm text-muted-foreground">No audit records were returned.</p>}</Card></div>
  </main>;
}
