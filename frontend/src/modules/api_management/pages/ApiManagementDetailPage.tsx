import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Power, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState } from '@/components/ui';
import { ApiError } from '@/services/api-client';
import { QUERY_KEYS, ROUTES } from '../contracts';
import { api_managementService } from '../services/api_management-service';

// eslint-disable-next-line complexity -- distinct loading, authorization, not-found, configuration, and lifecycle states must remain explicit.
export function ApiManagementDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [rollbackVersion, setRollbackVersion] = useState<number | null>(null);
  const resource = useQuery({ queryKey: QUERY_KEYS.RESOURCE(id), queryFn: () => api_managementService.getResource(id), enabled: Boolean(id) });
  const versions = useQuery({ queryKey: QUERY_KEYS.RESOURCE_VERSIONS(id), queryFn: () => api_managementService.listResourceVersions(id), enabled: Boolean(id) });
  const configuration = useQuery({ queryKey: QUERY_KEYS.RUNTIME_CONFIGURATION, queryFn: api_managementService.getRuntimeConfiguration });
  const policy = configuration.data?.document;

  useEffect(() => { document.title = resource.data ? `${resource.data.name} · API Management · SARAISE` : 'API Management resource · SARAISE'; }, [resource.data]);

  const lifecycle = useMutation({
    mutationFn: () => {
      if (!resource.data) throw new Error('Resource state is unavailable.');
      return resource.data.is_active ? api_managementService.deactivateResource(resource.data.id) : api_managementService.activateResource(resource.data.id);
    },
    onSuccess: async (updated) => { queryClient.setQueryData(QUERY_KEYS.RESOURCE(id), updated); await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCES() }); toast.success('Resource state updated'); },
    onError: () => toast.error('The state transition was rejected.'),
  });
  const restore = useMutation({
    mutationFn: (resourceId: string) => api_managementService.restoreResource(resourceId),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCES() }); toast.success('Resource restored'); },
    onError: () => toast.error('The restore operation was rejected.'),
  });
  const archive = useMutation({
    mutationFn: (resourceId: string) => api_managementService.deleteResource(resourceId),
    onSuccess: async (_result, resourceId) => { await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCES() }); toast.success('Resource archived', { action: { label: 'Restore', onClick: () => restore.mutate(resourceId) } }); navigate(ROUTES.RESOURCES); },
    onError: () => toast.error('The archive operation was rejected.'),
  });
  const rollback = useMutation({
    mutationFn: (version: number) => api_managementService.rollbackResource(id, {
      version,
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: async (updated, sourceVersion) => {
      queryClient.setQueryData(QUERY_KEYS.RESOURCE(id), updated);
      setRollbackVersion(null);
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCE_VERSIONS(id) });
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCES() });
      toast.success(`Resource restored from version ${sourceVersion}`);
    },
    onError: () => toast.error('The resource rollback was rejected.'),
  });

  if (resource.isLoading || configuration.isLoading) return <div className="p-8 text-muted-foreground" role="status">Loading resource…</div>;
  if (resource.error instanceof ApiError && resource.error.status === 404) return <div className="p-8"><ErrorState title="Resource not found" message="No tenant-owned resource exists for this identifier." /></div>;
  if (resource.error) return <div className="p-8"><ErrorState title="Resource request failed" message={resource.error instanceof Error ? resource.error.message : 'The resource could not be loaded.'} onRetry={() => { void resource.refetch(); }} /></div>;
  if (configuration.error || !policy) return <div className="p-8"><ErrorState title="Configuration unavailable" message="Privileged resource operations are disabled because tenant policy could not be loaded." onRetry={() => { void configuration.refetch(); }} /></div>;
  if (!resource.data) return <div className="p-8"><ErrorState title="Resource not found" message="No tenant-owned resource exists for this identifier." /></div>;

  const item = resource.data;
  const transitionAllowed = item.is_active ? policy.deactivation_enabled : policy.activation_enabled;
  return (
    <main className="space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-3xl font-bold text-foreground">{item.name}</h1><p className="mt-2 text-muted-foreground">{item.description || 'No description'}</p></div>
        <div className="flex gap-2">
          {transitionAllowed ? <Button variant="outline" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate()}><Power className="mr-2 h-4 w-4" />{lifecycle.isPending ? 'Applying…' : item.is_active ? 'Deactivate' : 'Activate'}</Button> : null}
          <Button variant="danger" disabled={archive.isPending} onClick={() => setArchiveOpen(true)}><Trash2 className="mr-2 h-4 w-4" />Archive</Button>
        </div>
      </header>
      <Card className="p-6">
        <dl className="grid gap-5 sm:grid-cols-2">
          <div><dt className="text-sm font-medium text-muted-foreground">Identifier</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.id}</dd></div>
          <div><dt className="text-sm font-medium text-muted-foreground">Status</dt><dd className="mt-1"><span className={item.is_active ? 'rounded bg-primary/10 px-2 py-1 text-xs text-primary' : 'rounded bg-muted px-2 py-1 text-xs text-muted-foreground'}>{item.is_active ? 'Active' : 'Inactive'}</span></dd></div>
          <div><dt className="text-sm font-medium text-muted-foreground">Created</dt><dd className="mt-1 text-foreground">{new Date(item.created_at).toLocaleString()}</dd></div>
          <div><dt className="text-sm font-medium text-muted-foreground">Updated</dt><dd className="mt-1 text-foreground">{new Date(item.updated_at).toLocaleString()}</dd></div>
        </dl>
        <div className="mt-6"><h2 className="text-sm font-medium text-muted-foreground">Resource configuration</h2><pre className="mt-2 overflow-auto rounded bg-muted p-3 text-sm text-foreground">{JSON.stringify(item.config, null, 2)}</pre></div>
      </Card>
      <Card className="space-y-3 p-6">
        <h2 className="text-lg font-semibold">Immutable resource versions</h2>
        <p className="text-sm text-muted-foreground">Rollback creates a new audited version; it never rewrites evidence.</p>
        {versions.isLoading ? <p role="status">Loading resource versions…</p> : versions.error ? <ErrorState message="Resource version history could not be loaded." onRetry={() => { void versions.refetch(); }} /> : (
          <div className="divide-y rounded border">
            {versions.data?.results.map((version) => (
              <div key={version.version} className="flex items-center justify-between gap-3 p-3 text-sm">
                <div><strong>Version {version.version}</strong><p className="text-muted-foreground">{version.reason} · {new Date(version.created_at).toLocaleString()}</p></div>
                <Button variant="outline" size="sm" disabled={version.version === item.version || rollback.isPending} onClick={() => setRollbackVersion(version.version)}><RotateCcw className="mr-2 h-3 w-3" />Rollback</Button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Dialog open={archiveOpen} onOpenChange={(open) => { if (!archive.isPending) setArchiveOpen(open); }} title="Archive API resource?" description={policy.deletion_confirmation_message} size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" disabled={archive.isPending} onClick={() => setArchiveOpen(false)}>Cancel</Button><Button variant="danger" disabled={archive.isPending} onClick={() => archive.mutate(id)}>{archive.isPending ? 'Archiving…' : 'Archive'}</Button></div>
      </Dialog>
      <Dialog open={rollbackVersion !== null} onOpenChange={(open) => { if (!open && !rollback.isPending) setRollbackVersion(null); }} title={`Rollback resource to version ${rollbackVersion ?? ''}?`} description="The selected immutable snapshot will be restored as a new audited resource version." size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" disabled={rollback.isPending} onClick={() => setRollbackVersion(null)}>Cancel</Button><Button disabled={rollbackVersion === null || rollback.isPending} onClick={() => { if (rollbackVersion !== null) rollback.mutate(rollbackVersion); }}>{rollback.isPending ? 'Rolling back…' : 'Create rollback version'}</Button></div>
      </Dialog>
    </main>
  );
}
