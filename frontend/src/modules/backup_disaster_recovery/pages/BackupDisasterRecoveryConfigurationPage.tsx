import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, FileDiff, History, RotateCcw, Save, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import type {
  BDRConfigurationDocument,
  BDRConfigurationMutation,
  BDRConfigurationPreview,
  BDRConfigurationRollout,
} from '../contracts';
import { configurationQueryKey } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import {
  BackgroundProgress,
  FormField,
  ModuleErrorState,
  MutationError,
  PageHeader,
  PageShell,
  PageSkeleton,
  ResponsiveTable,
  formatDateTime,
  inputClass,
  textareaClass,
} from '../components/ModuleUi';

const isConfigurationDocument = (value: unknown): value is BDRConfigurationDocument => {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const record = value as Readonly<Record<string, unknown>>;
  return [
    'quota_costs', 'resilience', 'health', 'providers', 'runbooks', 'steps',
    'restores', 'exercises', 'reports', 'presentation', 'polling', 'workflows',
  ].every((key) => typeof record[key] === 'object' && record[key] !== null);
};

const splitList = (value: string): readonly string[] => value
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);

const downloadDocument = (filename: string, value: object): void => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

// The configuration transaction intentionally keeps parse, preview fingerprint,
// import staging, mutation state, and immutable history in one review surface.
// eslint-disable-next-line complexity, max-lines-per-function
export const BackupDisasterRecoveryConfigurationPage = () => {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const configuration = useQuery({ queryKey: configurationQueryKey, queryFn: backupDisasterRecoveryService.getConfiguration });
  const versions = useQuery({ queryKey: ['bdr', 'configuration', 'versions'], queryFn: backupDisasterRecoveryService.listConfigurationVersions });
  const [documentText, setDocumentText] = useState('');
  const [environment, setEnvironment] = useState('');
  const [rolloutEnabled, setRolloutEnabled] = useState(false);
  const [roles, setRoles] = useState('');
  const [cohorts, setCohorts] = useState('');
  const [parseError, setParseError] = useState('');
  const [preview, setPreview] = useState<BDRConfigurationPreview | null>(null);
  const [previewFingerprint, setPreviewFingerprint] = useState('');
  const [importMode, setImportMode] = useState(false);

  useEffect(() => {
    if (!configuration.data) return;
    setDocumentText(JSON.stringify(configuration.data.document, null, 2));
    setEnvironment(configuration.data.environment);
    setRolloutEnabled(configuration.data.rollout.enabled);
    setRoles(configuration.data.rollout.roles.join(', '));
    setCohorts(configuration.data.rollout.cohorts.join(', '));
  }, [configuration.data]);

  const rollout = useMemo<BDRConfigurationRollout>(() => ({
    enabled: rolloutEnabled,
    roles: splitList(roles),
    cohorts: splitList(cohorts),
  }), [cohorts, roles, rolloutEnabled]);

  const parsePayload = (): BDRConfigurationMutation | null => {
    try {
      const parsed: unknown = JSON.parse(documentText);
      if (!isConfigurationDocument(parsed)) {
        setParseError('The document must contain every required configuration section.');
        return null;
      }
      if (!environment.trim()) {
        setParseError('Environment is required.');
        return null;
      }
      setParseError('');
      return { document: parsed, environment: environment.trim(), rollout };
    } catch {
      setParseError('Configuration must be valid JSON.');
      return null;
    }
  };

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: configurationQueryKey });
    void queryClient.invalidateQueries({ queryKey: ['bdr', 'configuration', 'versions'] });
  };
  const previewMutation = useMutation({
    mutationFn: backupDisasterRecoveryService.previewConfiguration,
    onSuccess: (result, payload) => {
      setPreview(result);
      setPreviewFingerprint(JSON.stringify(payload));
    },
  });
  const saveMutation = useMutation({ mutationFn: backupDisasterRecoveryService.updateConfiguration, onSuccess: invalidate });
  const importMutation = useMutation({ mutationFn: backupDisasterRecoveryService.importConfiguration, onSuccess: () => { setImportMode(false); invalidate(); } });
  const rollbackMutation = useMutation({ mutationFn: backupDisasterRecoveryService.rollbackConfiguration, onSuccess: invalidate });
  const exportMutation = useMutation({
    mutationFn: backupDisasterRecoveryService.exportConfiguration,
    onSuccess: (result) => downloadDocument(`backup-disaster-recovery-config-v${result.version}.json`, result),
  });

  if (configuration.isLoading || versions.isLoading) return <PageSkeleton cards={2} />;
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (versions.error) return <ModuleErrorState error={versions.error} onRetry={() => { void versions.refetch(); }} />;
  if (!configuration.data) return <PageSkeleton cards={2} />;

  const payloadFingerprint = (() => {
    try {
      const parsed: unknown = JSON.parse(documentText);
      return JSON.stringify({ document: parsed, environment: environment.trim(), rollout });
    } catch {
      return '';
    }
  })();
  const canApply = preview?.valid === true && previewFingerprint === payloadFingerprint;
  const busy = previewMutation.isPending || saveMutation.isPending || importMutation.isPending || rollbackMutation.isPending || exportMutation.isPending;
  const operationError = [previewMutation.error, saveMutation.error, importMutation.error, rollbackMutation.error, exportMutation.error]
    .find((error) => error instanceof Error);

  const requestPreview = (): void => {
    const payload = parsePayload();
    if (payload) previewMutation.mutate(payload);
  };
  const apply = (): void => {
    const payload = parsePayload();
    if (!payload || JSON.stringify(payload) !== previewFingerprint || !preview?.valid) return;
    if (importMode) importMutation.mutate(payload);
    else saveMutation.mutate(payload);
  };
  const readImport = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== 'string') return;
      try {
        const parsed: unknown = JSON.parse(reader.result);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('Invalid document');
        const record = parsed as Readonly<Record<string, unknown>>;
        const importedDocument = record.document ?? parsed;
        if (!isConfigurationDocument(importedDocument)) throw new Error('Invalid document');
        setDocumentText(JSON.stringify(importedDocument, null, 2));
        if (typeof record.environment === 'string') setEnvironment(record.environment);
        if (typeof record.rollout === 'object' && record.rollout !== null && !Array.isArray(record.rollout)) {
          const importedRollout = record.rollout as Readonly<Record<string, unknown>>;
          setRolloutEnabled(importedRollout.enabled === true);
          if (Array.isArray(importedRollout.roles)) setRoles(importedRollout.roles.filter((item): item is string => typeof item === 'string').join(', '));
          if (Array.isArray(importedRollout.cohorts)) setCohorts(importedRollout.cohorts.filter((item): item is string => typeof item === 'string').join(', '));
        }
        setImportMode(true);
        setPreview(null);
        setParseError('');
      } catch {
        setParseError('The selected file is not a valid configuration export.');
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  };

  return <PageShell>
    <BackgroundProgress active={busy} label="Applying disaster recovery configuration" />
    <PageHeader title="Disaster recovery configuration" description="Tenant-scoped, versioned policy and operational controls. Preview every change before it is applied." actions={<>
      <input ref={fileInput} type="file" accept="application/json,.json" className="sr-only" onChange={readImport} />
      <Button variant="outline" onClick={() => fileInput.current?.click()}><Upload className="mr-2 h-4 w-4" />Import</Button>
      <Button variant="outline" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}><Download className="mr-2 h-4 w-4" />Export</Button>
    </>} />
    <MutationError error={operationError instanceof Error ? operationError : null} />
    {parseError ? <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{parseError}</p> : null}
    {importMode ? <p role="status" className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">Imported values are staged only. Preview the diff, then apply the import transaction.</p> : null}
    <Card><CardHeader><CardTitle>Configuration document · version {configuration.data.version}</CardTitle><p className="text-sm text-muted-foreground">All values are validated again by the server. Secrets and provider credentials are never accepted here.</p></CardHeader><CardContent className="space-y-5">
      <div className="grid gap-5 md:grid-cols-2">
        <FormField id="configuration-environment" label="Environment" hint="Selects tenant values without creating environment-specific code paths."><input id="configuration-environment" className={inputClass} value={environment} onChange={(event) => { setEnvironment(event.target.value); setPreview(null); }} /></FormField>
        <FormField id="configuration-rollout" label="Phased rollout"><label className="flex h-10 items-center gap-3 rounded-md border border-input px-3"><input id="configuration-rollout" type="checkbox" checked={rolloutEnabled} onChange={(event) => { setRolloutEnabled(event.target.checked); setPreview(null); }} />Enabled for selected roles or cohorts</label></FormField>
        <FormField id="configuration-roles" label="Rollout roles" hint="Comma-separated role allow-list."><input id="configuration-roles" disabled={!rolloutEnabled} className={inputClass} value={roles} onChange={(event) => { setRoles(event.target.value); setPreview(null); }} /></FormField>
        <FormField id="configuration-cohorts" label="Rollout cohorts" hint="Comma-separated cohort allow-list."><input id="configuration-cohorts" disabled={!rolloutEnabled} className={inputClass} value={cohorts} onChange={(event) => { setCohorts(event.target.value); setPreview(null); }} /></FormField>
      </div>
      <FormField id="configuration-document" label="Policy document" hint="Every setting exposed here has the same RBAC-gated API representation."><textarea id="configuration-document" spellCheck={false} className={`${textareaClass} min-h-[32rem] font-mono text-xs`} value={documentText} onChange={(event) => { setDocumentText(event.target.value); setPreview(null); }} /></FormField>
      <div className="flex flex-wrap justify-end gap-3"><Button variant="outline" disabled={previewMutation.isPending} onClick={requestPreview}><FileDiff className="mr-2 h-4 w-4" />{previewMutation.isPending ? 'Validating…' : 'Preview changes'}</Button><Button disabled={!canApply || busy} onClick={apply}><Save className="mr-2 h-4 w-4" />{importMode ? 'Apply import' : 'Apply configuration'}</Button></div>
    </CardContent></Card>
    {preview ? <Card><CardHeader><CardTitle>Validated change preview</CardTitle></CardHeader><CardContent>{preview.changes.length ? <ResponsiveTable label="Configuration changes" headers={['Path', 'Before', 'After']}>{preview.changes.map((change) => <tr key={change.path}><td className="px-4 py-3 font-mono text-xs">{change.path}</td><td className="max-w-sm break-words px-4 py-3 font-mono text-xs">{JSON.stringify(change.before)}</td><td className="max-w-sm break-words px-4 py-3 font-mono text-xs">{JSON.stringify(change.after)}</td></tr>)}</ResponsiveTable> : <p className="text-sm text-muted-foreground">No effective changes. Apply remains safe and idempotent.</p>}</CardContent></Card> : null}
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="h-5 w-5" />Immutable version history</CardTitle><p className="text-sm text-muted-foreground">Every entry records actor, correlation ID, prior value, new value, and rollback ancestry.</p></CardHeader><CardContent>{versions.data?.length ? <ResponsiveTable label="Configuration version history" headers={['Version', 'Changed', 'Actor', 'Correlation ID', 'Origin', 'Action']}>{versions.data.map((version) => <tr key={version.id}><td className="px-4 py-3 font-semibold">v{version.version}</td><td className="px-4 py-3">{formatDateTime(version.created_at)}</td><td className="px-4 py-3 font-mono text-xs">{version.actor_id}</td><td className="px-4 py-3 font-mono text-xs">{version.correlation_id}</td><td className="px-4 py-3">{version.rollback_of ? `Rollback of ${version.rollback_of}` : 'Direct change'}</td><td className="px-4 py-3"><Button variant="outline" size="sm" disabled={version.version === configuration.data.version || busy} onClick={() => rollbackMutation.mutate({ version: version.version })}><RotateCcw className="mr-2 h-4 w-4" />Rollback</Button></td></tr>)}</ResponsiveTable> : <p className="text-sm text-muted-foreground">The initial immutable version appears after the first saved change.</p>}</CardContent></Card>
  </PageShell>;
};
