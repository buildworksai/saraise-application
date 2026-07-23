/* eslint-disable max-lines-per-function */
import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, History, RotateCcw, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { useAuthStore } from '@/stores/auth-store';
import type { AssetConfigurationDocument, AssetConfigurationExport } from '../contracts';
import { PageHeader, PageSkeleton, ProblemState } from '../components/AssetManagementUI';
import { assetQueryKeys, assetService } from '../services/asset-service';

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseDocument(value: string): AssetConfigurationDocument {
  return JSON.parse(value) as AssetConfigurationDocument;
}

export const AssetConfigurationPage = () => {
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState('');
  const [importDraft, setImportDraft] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);

  const configurationQuery = useQuery({
    queryKey: assetQueryKeys.configuration(tenantId),
    queryFn: () => assetService.getConfiguration(),
  });
  const historyQuery = useQuery({
    queryKey: assetQueryKeys.configurationHistory(tenantId),
    queryFn: () => assetService.listConfigurationHistory(),
  });

  useEffect(() => {
    if (configurationQuery.data) setDraft(pretty(configurationQuery.data.document));
  }, [configurationQuery.data]);

  const parsedDraft = useMemo((): { document: AssetConfigurationDocument | null; error: string | null } => {
    try {
      return { document: draft ? parseDocument(draft) : null, error: null };
    } catch (error) {
      return { document: null, error: error instanceof Error ? error.message : 'Invalid JSON document.' };
    }
  }, [draft]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: assetQueryKeys.root(tenantId) });
  };

  const previewMutation = useMutation({
    mutationFn: (document: AssetConfigurationDocument) => assetService.previewConfiguration(document),
  });
  const updateMutation = useMutation({
    mutationFn: (document: AssetConfigurationDocument) => assetService.updateConfiguration(document),
    onSuccess: (configuration) => {
      setDraft(pretty(configuration.document));
      refresh();
      toast.success('Asset configuration saved');
    },
  });
  const rollbackMutation = useMutation({
    mutationFn: (version: number) => assetService.rollbackConfiguration(version),
    onSuccess: (configuration) => {
      setDraft(pretty(configuration.document));
      refresh();
      toast.success('Asset configuration rolled back');
    },
  });
  const importMutation = useMutation({
    mutationFn: (configuration: AssetConfigurationExport) => assetService.importConfiguration(configuration),
    onSuccess: (configuration) => {
      setDraft(pretty(configuration.document));
      setImportDraft('');
      refresh();
      toast.success('Asset configuration imported');
    },
  });
  const exportMutation = useMutation({
    mutationFn: () => assetService.exportConfiguration(),
    onSuccess: (document) => setImportDraft(pretty(document)),
  });

  const submitPreview = (event: FormEvent) => {
    event.preventDefault();
    if (parsedDraft.document) previewMutation.mutate(parsedDraft.document);
  };
  const submitSave = () => {
    if (parsedDraft.document) updateMutation.mutate(parsedDraft.document);
  };
  const submitImport = () => {
    try {
      importMutation.mutate(JSON.parse(importDraft) as AssetConfigurationExport);
    } catch (error) {
      setParseError(error instanceof Error ? error.message : 'Invalid import document.');
    }
  };
  const importFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    void file.text().then(setImportDraft);
  };

  if (configurationQuery.isLoading) return <PageSkeleton />;
  if (configurationQuery.error || !configurationQuery.data) {
    return <main className="p-4 sm:p-8"><ProblemState error={configurationQuery.error ?? new Error('Configuration unavailable')} onRetry={() => void configurationQuery.refetch()} /></main>;
  }

  const previewChanges = previewMutation.data?.changes ?? {};

  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Asset configuration"
        description={`Version ${configurationQuery.data.version}. Changes are validated by the server, versioned, audited, and reversible.`}
      />

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="space-y-4 p-5">
          <form className="space-y-4" onSubmit={submitPreview}>
            <label className="block text-sm font-medium" htmlFor="asset-configuration-document">
              Configuration document
            </label>
            <textarea
              id="asset-configuration-document"
              className="min-h-[34rem] w-full rounded-md border border-input bg-background p-3 font-mono text-sm"
              value={draft}
              spellCheck={false}
              onChange={(event) => setDraft(event.target.value)}
            />
            {(parseError ?? parsedDraft.error) && <p role="alert" className="text-sm text-destructive">{parseError ?? parsedDraft.error}</p>}
            {previewMutation.error && <ProblemState error={previewMutation.error} compact />}
            {updateMutation.error && <ProblemState error={updateMutation.error} compact />}
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="submit" variant="secondary" disabled={!parsedDraft.document || previewMutation.isPending}>
                Preview
              </Button>
              <Button type="button" disabled={!parsedDraft.document || updateMutation.isPending} onClick={submitSave}>
                Save version
              </Button>
            </div>
          </form>
        </Card>

        <div className="space-y-4">
          <Card className="space-y-3 p-5">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4" aria-hidden="true" />
              <h2 className="font-semibold">Preview</h2>
            </div>
            {Object.keys(previewChanges).length === 0 ? (
              <p className="text-sm text-muted-foreground">No pending differences.</p>
            ) : (
              <dl className="space-y-3 text-sm">
                {Object.entries(previewChanges).map(([field, change]) => (
                  <div key={field} className="rounded-md border p-3">
                    <dt className="font-medium">{field}</dt>
                    <dd className="mt-1 break-words text-muted-foreground">
                      {pretty(change.from)} -&gt; {pretty(change.to)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>

          <Card className="space-y-3 p-5">
            <div className="flex items-center gap-2">
              <Upload className="h-4 w-4" aria-hidden="true" />
              <h2 className="font-semibold">Import / export</h2>
            </div>
            <Input id="asset-configuration-import-file" type="file" accept="application/json" onChange={importFile} />
            <textarea
              aria-label="Configuration import document"
              className="min-h-40 w-full rounded-md border border-input bg-background p-3 font-mono text-xs"
              value={importDraft}
              onChange={(event) => setImportDraft(event.target.value)}
            />
            {importMutation.error && <ProblemState error={importMutation.error} compact />}
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
                <Download className="mr-2 h-4 w-4" aria-hidden="true" />
                Export
              </Button>
              <Button onClick={submitImport} disabled={!importDraft || importMutation.isPending}>
                <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
                Import
              </Button>
            </div>
          </Card>

          <Card className="space-y-3 p-5">
            <div className="flex items-center gap-2">
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              <h2 className="font-semibold">Version history</h2>
            </div>
            {historyQuery.error && <ProblemState error={historyQuery.error} onRetry={() => void historyQuery.refetch()} compact />}
            <div className="space-y-2">
              {historyQuery.data?.items.map((version) => (
                <div key={version.id} className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
                  <div>
                    <p className="font-medium">Version {version.version}</p>
                    <p className="text-muted-foreground">{version.source} · {new Date(version.created_at).toLocaleString()}</p>
                    <p className="font-mono text-xs text-muted-foreground">{version.correlation_id}</p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={rollbackMutation.isPending}
                    onClick={() => rollbackMutation.mutate(version.version)}
                  >
                    Roll back
                  </Button>
                </div>
              ))}
            </div>
            {rollbackMutation.error && <ProblemState error={rollbackMutation.error} compact />}
          </Card>
        </div>
      </section>
    </main>
  );
};
