import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, History, RotateCcw, Save, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { IntegrationPlatformConfigurationDocument } from '../contracts';
import { GovernedError, PageHeader, PageSkeleton } from '../components/IntegrationPlatformUI';
import { integrationPlatformService as service } from '../services/integration-platform-service';

function numeric(value: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) throw new Error('Configuration values must be whole numbers.');
  return parsed;
}

export function ConfigurationPage() {
  const queryClient = useQueryClient();
  const importInput = useRef<HTMLInputElement>(null);
  const current = useQuery({ queryKey: ['integration-platform', 'configuration'], queryFn: () => service.getConfiguration() });
  const versions = useQuery({ queryKey: ['integration-platform', 'configuration', 'versions'], queryFn: () => service.listConfigurationVersions() });
  const audits = useQuery({ queryKey: ['integration-platform', 'configuration', 'audits'], queryFn: () => service.listConfigurationAudits() });
  const [draft, setDraft] = useState<IntegrationPlatformConfigurationDocument | null>(null);
  const [preview, setPreview] = useState<string[]>([]);
  useEffect(() => { if (current.data) setDraft(structuredClone(current.data.document)); }, [current.data]);
  const refresh = async () => { await queryClient.invalidateQueries({ queryKey: ['integration-platform', 'configuration'] }); };
  const save = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('Configuration is unavailable.');
      const result = await service.previewConfiguration({ environment: draft.environment, document: draft });
      setPreview(result.changed_sections);
      if (!window.confirm(`Apply version ${result.to_version}? Changed sections: ${result.changed_sections.join(', ') || 'none'}`)) throw new Error('Change cancelled.');
      return service.saveConfiguration({ environment: draft.environment, document: draft });
    },
    onSuccess: async (result) => { toast.success(`Configuration version ${result.version} applied.`); await refresh(); },
    onError: (error: Error) => { if (error.message !== 'Change cancelled.') toast.error(error.message); },
  });
  const rollback = useMutation({
    mutationFn: (version: number) => service.rollbackConfiguration(draft?.environment ?? 'default', version),
    onSuccess: async (result) => { toast.success(`Rolled back as new version ${result.version}.`); await refresh(); },
    onError: (error: Error) => toast.error(error.message),
  });
  const setNumber = (section: 'webhooks' | 'synchronization' | 'mapping' | 'security', key: string, value: string) => {
    if (!draft) return;
    const next = structuredClone(draft);
    const target = next[section] as unknown as Record<string, number>;
    target[key] = numeric(value);
    setDraft(next);
  };
  const importFile = async (file: File) => {
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== 'object' || !('document' in parsed)) throw new Error('Import must contain a configuration document.');
      const document = (parsed as { document: IntegrationPlatformConfigurationDocument }).document;
      const result = await service.previewConfiguration({ environment: document.environment, document });
      setPreview(result.changed_sections);
      if (window.confirm(`Import changes to: ${result.changed_sections.join(', ') || 'none'}?`)) {
        await service.importConfiguration({ environment: document.environment, document });
        await refresh();
      }
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Configuration import failed.'); }
  };
  const exportFile = async () => {
    const payload = await service.exportConfiguration();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `integration-platform-${payload.environment}-v${payload.version}.json`; link.click(); URL.revokeObjectURL(link.href);
  };
  if (current.isLoading || !draft) return <PageSkeleton label="Loading Integration Platform configuration" />;
  if (current.error) return <main className="p-4 sm:p-8"><GovernedError error={current.error} retry={() => { void current.refetch(); }} /></main>;
  return <main className="space-y-6 p-4 sm:p-8">
    <PageHeader title="Integration Platform configuration" description="Tenant-scoped runtime policy. Every save is validated server-side, versioned, audited, and reversible." actions={<><Button variant="secondary" onClick={() => { void exportFile(); }}><Download className="mr-2 h-4 w-4" />Export</Button><Button variant="secondary" onClick={() => importInput.current?.click()}><Upload className="mr-2 h-4 w-4" />Import</Button><Button disabled={save.isPending} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4" />Preview & apply</Button></>} />
    <input ref={importInput} className="hidden" type="file" accept="application/json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); }} />
    {preview.length > 0 && <Card className="p-4 text-sm" role="status">Previewed changes: {preview.join(', ')}</Card>}
    <Card className="grid gap-5 p-6 md:grid-cols-2">
      <Input label="Environment" value={draft.environment} onChange={(event) => setDraft({ ...draft, environment: event.target.value })} title="Portable environment label; code paths remain identical." />
      <Input label="Credential maximum characters" type="number" min={1} max={1048576} value={draft.validation.credential_max_length} onChange={(event) => setDraft({ ...draft, validation: { ...draft.validation, credential_max_length: numeric(event.target.value) } })} title="Server-enforced maximum for write-only credential input." />
      <Input label="Webhook timeout default (seconds)" type="number" min={draft.webhooks.timeout_seconds_min} max={draft.webhooks.timeout_seconds_max} value={draft.webhooks.timeout_seconds_default} onChange={(event) => setNumber('webhooks', 'timeout_seconds_default', event.target.value)} title="Default outbound deadline; bounded by the configured safe range." />
      <Input label="Webhook maximum attempts" type="number" min={draft.webhooks.max_attempts_min} max={draft.webhooks.max_attempts_max} value={draft.webhooks.max_attempts_default} onChange={(event) => setNumber('webhooks', 'max_attempts_default', event.target.value)} title="Maximum durable attempts before dead-letter evidence." />
      <Input label="Signature window (seconds)" type="number" min={30} max={900} value={draft.security.signature_window_seconds} onChange={(event) => setNumber('security', 'signature_window_seconds', event.target.value)} title="Allowed inbound timestamp skew; replay checks always remain enabled." />
      <Input label="Pull batch limit" type="number" min={1} max={10000} value={draft.synchronization.pull_batch_limit} onChange={(event) => setNumber('synchronization', 'pull_batch_limit', event.target.value)} title="Maximum records requested from an adapter per durable job." />
      <Input label="Mapping preview records" type="number" min={1} max={1000} value={draft.mapping.preview_record_limit} onChange={(event) => setNumber('mapping', 'preview_record_limit', event.target.value)} title="Maximum sample size accepted by preview." />
      <label className="text-sm font-medium">Synchronization directions<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" multiple value={draft.synchronization.directions} onChange={(event) => setDraft({ ...draft, synchronization: { ...draft.synchronization, directions: Array.from(event.target.selectedOptions, (option) => option.value as 'pull' | 'push') } })}><option value="pull">Pull</option><option value="push" disabled={!draft.feature_flags.push_synchronization?.enabled}>Push (requires governed source flag)</option></select><span className="mt-1 block text-xs text-muted-foreground">Push cannot be selected until its governed source feature is enabled.</span></label>
    </Card>
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="p-6"><h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><History className="h-4 w-4" />Versions</h2>{versions.data?.items.map((item) => <div className="flex items-center justify-between border-b py-3" key={item.id}><span>v{item.version} · {new Date(item.created_at).toLocaleString()}</span><Button size="sm" variant="secondary" disabled={rollback.isPending || item.version === current.data?.version} onClick={() => rollback.mutate(item.version)}><RotateCcw className="mr-1 h-3 w-3" />Rollback</Button></div>)}</Card>
      <Card className="p-6"><h2 className="mb-4 text-lg font-semibold">Immutable audit history</h2>{audits.data?.items.map((item) => <div className="border-b py-3 text-sm" key={item.id}><strong>{item.action}</strong> · v{item.from_version ?? 0} → v{item.to_version}<p className="font-mono text-xs text-muted-foreground">{item.correlation_id}</p></div>)}</Card>
    </div>
  </main>;
}
