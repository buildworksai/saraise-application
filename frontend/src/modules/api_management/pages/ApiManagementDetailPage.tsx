import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Power, Trash2 } from 'lucide-react';
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
  const resource = useQuery({ queryKey: QUERY_KEYS.RESOURCE(id), queryFn: () => api_managementService.getResource(id), enabled: Boolean(id) });
  const configuration = useQuery({ queryKey: QUERY_KEYS.CONFIGURATION, queryFn: api_managementService.getConfiguration });
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
      <Dialog open={archiveOpen} onOpenChange={(open) => { if (!archive.isPending) setArchiveOpen(open); }} title="Archive API resource?" description={policy.deletion_confirmation_message} size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" disabled={archive.isPending} onClick={() => setArchiveOpen(false)}>Cancel</Button><Button variant="danger" disabled={archive.isPending} onClick={() => archive.mutate(id)}>{archive.isPending ? 'Archiving…' : 'Archive'}</Button></div>
      </Dialog>
    </main>
  );
}
