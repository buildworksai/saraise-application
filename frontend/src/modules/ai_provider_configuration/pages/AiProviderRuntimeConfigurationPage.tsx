import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, RotateCcw, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiProblem, ConsoleHeader, ConsoleSkeleton, EmptyPanel } from '../components/ConsolePrimitives';
import type { RuntimeConfigurationDocument, RuntimeConfigurationValues } from '../contracts';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';
import { useAiProviderDocumentTitle } from '../use-ai-provider-document-title';

const QUERY_ROOT = ['ai-provider-configuration'] as const;

function parseJson(value: string): RuntimeConfigurationValues {
  const parsed = JSON.parse(value) as unknown;
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Configuration must be a JSON object.');
  }
  return parsed as RuntimeConfigurationValues;
}

export function AiProviderRuntimeConfigurationPage() {
  useAiProviderDocumentTitle('AI provider runtime configuration');
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState('');
  const [environment, setEnvironment] = useState('default');
  const [parseError, setParseError] = useState('');
  const configuration = useQuery({ queryKey: [...QUERY_ROOT, 'runtime-configuration'], queryFn: aiProviderConfigurationService.getRuntimeConfiguration });
  const versions = useQuery({ queryKey: [...QUERY_ROOT, 'runtime-configuration', 'versions'], queryFn: aiProviderConfigurationService.listRuntimeConfigurationVersions });
  const audit = useQuery({ queryKey: [...QUERY_ROOT, 'runtime-configuration', 'audit'], queryFn: aiProviderConfigurationService.listRuntimeConfigurationAudit });
  const valuesText = useMemo(() => JSON.stringify(configuration.data?.values ?? {}, null, 2), [configuration.data?.values]);

  useEffect(() => {
    if (!configuration.data) return;
    setDraft(valuesText);
    setEnvironment(configuration.data.environment);
  }, [configuration.data, valuesText]);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
  };

  const preview = useMutation({
    mutationFn: () => aiProviderConfigurationService.previewRuntimeConfiguration(environment, parseJson(draft)),
    onError: (error) => setParseError(error instanceof Error ? error.message : 'Configuration preview failed.'),
  });
  const update = useMutation({
    mutationFn: () => aiProviderConfigurationService.updateRuntimeConfiguration(environment, parseJson(draft)),
    onSuccess: async () => { setParseError(''); await refresh(); toast.success('Runtime configuration published'); },
    onError: (error) => setParseError(error instanceof Error ? error.message : 'Configuration update failed.'),
  });
  const rollback = useMutation({
    mutationFn: (version: number) => aiProviderConfigurationService.rollbackRuntimeConfiguration(version, environment),
    onSuccess: async () => { await refresh(); toast.success('Rollback published as a new version'); },
  });
  const exportDocument = useMutation({
    mutationFn: aiProviderConfigurationService.exportRuntimeConfiguration,
    onSuccess: (document) => {
      const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' });
      const link = globalThis.document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `ai-provider-runtime-${document.environment}-v${document.version}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    },
  });
  const importDocument = useMutation({
    mutationFn: (document: RuntimeConfigurationDocument) => aiProviderConfigurationService.importRuntimeConfiguration(document),
    onSuccess: async () => { await refresh(); toast.success('Runtime configuration imported'); },
  });

  const retry = () => {
    void Promise.all([configuration.refetch(), versions.refetch(), audit.refetch()]);
  };

  const readImport = (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const document = JSON.parse(String(reader.result)) as RuntimeConfigurationDocument;
        importDocument.mutate(document);
      } catch {
        setParseError('The selected import file is not valid JSON.');
      }
    };
    reader.readAsText(file);
  };

  const error = configuration.error ?? versions.error ?? audit.error;
  if (configuration.isLoading || versions.isLoading || audit.isLoading) return <div className="min-h-full bg-muted/20"><ConsoleHeader title="Runtime configuration" description="Validate, preview, publish, import, export, and roll back tenant AI provider policy." /><ConsoleSkeleton /></div>;
  if (error || !configuration.data) return <div className="min-h-full bg-muted/20"><ConsoleHeader title="Runtime configuration" description="Validate, preview, publish, import, export, and roll back tenant AI provider policy." /><main className="p-4 sm:p-6 lg:p-8"><ApiProblem error={error ?? new Error('Configuration unavailable')} onRetry={retry} /></main></div>;

  return (
    <div className="min-h-full bg-muted/20">
      <ConsoleHeader title="Runtime configuration" description="Tenant-scoped provider policy with server-side validation, immutable audit, version history, rollback, import, and export." />
      <main className="mx-auto grid max-w-7xl gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:p-8">
        <Card>
          <CardHeader className="gap-4 border-b lg:flex-row lg:items-center lg:justify-between">
            <div><CardTitle>Policy document</CardTitle><CardDescription>Current version {configuration.data.version}. Invalid combinations are rejected by the API before persistence.</CardDescription></div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => preview.mutate()}>Preview</Button>
              <Button onClick={() => update.mutate()} disabled={update.isPending}>Publish</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            <Input id="runtime-environment" label="Environment" value={environment} onChange={(event) => setEnvironment(event.target.value)} />
            <textarea aria-label="Runtime configuration JSON" value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-[36rem] w-full rounded-md border bg-background p-4 font-mono text-xs" spellCheck={false} />
            {parseError ? <p className="text-sm text-destructive" role="alert">{parseError}</p> : null}
            {preview.data ? <pre className="max-h-72 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(preview.data, null, 2)}</pre> : null}
          </CardContent>
        </Card>

        <aside className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-lg">Portable policy</CardTitle><CardDescription>Move reviewed configuration between environments without changing source.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <Button className="w-full" variant="outline" onClick={() => exportDocument.mutate()}><Download className="mr-2 h-4 w-4" />Export JSON</Button>
              <label className="flex h-10 cursor-pointer items-center justify-center rounded-md border text-sm font-medium hover:bg-muted">
                <Upload className="mr-2 h-4 w-4" />Import JSON
                <input className="sr-only" type="file" accept="application/json" onChange={(event) => readImport(event.target.files?.[0])} />
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-lg">Versions</CardTitle></CardHeader>
            <CardContent>{versions.data?.length ? <ul className="divide-y">{versions.data.map((item) => <li key={item.id} className="flex items-center justify-between py-3"><div><p className="font-medium">Version {item.version}</p><p className="font-mono text-xs text-muted-foreground">{item.correlation_id}</p></div><Button size="sm" variant="outline" disabled={item.version === configuration.data.version || rollback.isPending} onClick={() => rollback.mutate(item.version)}><RotateCcw className="mr-2 h-4 w-4" />Rollback</Button></li>)}</ul> : <EmptyPanel title="No versions" description="The first saved policy version will appear here." icon={<RotateCcw className="h-5 w-5" />} />}</CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-lg">Audit history</CardTitle></CardHeader>
            <CardContent>{audit.data?.length ? <ul className="divide-y">{audit.data.map((item) => <li key={item.id} className="py-3 text-sm"><p className="font-medium">{item.action} to version {item.to_version}</p><p className="font-mono text-xs text-muted-foreground">{item.correlation_id}</p></li>)}</ul> : <EmptyPanel title="No audit records" description="Every configuration change writes immutable audit evidence." icon={<RotateCcw className="h-5 w-5" />} />}</CardContent>
          </Card>
        </aside>
      </main>
    </div>
  );
}
