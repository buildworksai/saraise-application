import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Edit, Power, PowerOff, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { ErrorState } from '@/components/ui/ErrorState';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { REGIONAL_QUERY_KEYS, ROUTES } from '../contracts';
import { regionalService } from '../services/regional-service';
import { useRegionalDocumentTitle } from '../use-regional-document-title';

export const RegionalDetailPage = () => {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const resource = useQuery({
    queryKey: REGIONAL_QUERY_KEYS.resource(id),
    queryFn: () => regionalService.getResource(id),
    enabled: Boolean(id),
  });
  const configuration = useQuery({
    queryKey: [...REGIONAL_QUERY_KEYS.configuration('active'), 'active'],
    queryFn: regionalService.getActiveConfiguration,
  });
  useRegionalDocumentTitle(resource.data?.name ?? 'Regional resource');

  const remove = useMutation({
    mutationFn: () => regionalService.deleteResource(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resources });
      toast.success('Resource archived successfully');
      navigate(ROUTES.ROOT);
    },
    onError: () => toast.error('Failed to archive resource. Please try again.'),
  });
  const lifecycle = useMutation({
    mutationFn: (action: 'activate' | 'deactivate') =>
      action === 'activate'
        ? regionalService.activateResource(id)
        : regionalService.deactivateResource(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(REGIONAL_QUERY_KEYS.resource(id), updated);
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resources });
      toast.success(updated.is_active ? 'Resource activated' : 'Resource deactivated');
    },
    onError: () => toast.error('The lifecycle transition failed.'),
  });

  if (resource.isLoading || configuration.isLoading) {
    return <p role="status" className="p-8 text-muted-foreground">Loading resource…</p>;
  }
  if (resource.isError) {
    return (
      <div className="p-8">
        <ErrorState
          title="Unable to load resource"
          message={
            resource.error instanceof Error
              ? resource.error.message
              : 'The resource request failed.'
          }
          onRetry={() => void resource.refetch()}
        />
      </div>
    );
  }
  if (configuration.isError || !configuration.data) {
    return (
      <div className="p-8">
        <ErrorState
          title="Configuration unavailable"
          message="Lifecycle and deletion controls are disabled because the governed workflow could not be loaded."
          onRetry={() => void configuration.refetch()}
        />
      </div>
    );
  }
  if (!resource.data) {
    return (
      <div className="p-8">
        <ErrorState title="Resource not found" message="No Regional resource exists at this address." />
      </div>
    );
  }

  const item = resource.data;
  const workflow = configuration.data.document.workflow;
  const executeDelete = () => remove.mutate();
  const requestDelete = () => {
    if (workflow.require_delete_confirmation) setDeleteDialogOpen(true);
    else executeDelete();
  };

  return (
    <main id="main-content" className="space-y-6 p-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div>
          <h1 className="text-3xl font-bold text-foreground">{item.name}</h1>
          <p className="mt-2 text-muted-foreground">
            {item.description || 'No description provided.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate(ROUTES.EDIT(item.id))}>
            <Edit className="mr-2 h-4 w-4" />Edit
          </Button>
          {item.is_active ? (
            <Button
              variant="outline"
              disabled={lifecycle.isPending}
              onClick={() => lifecycle.mutate('deactivate')}
            >
              <PowerOff className="mr-2 h-4 w-4" />Deactivate
            </Button>
          ) : (
            <Button
              variant="outline"
              disabled={lifecycle.isPending}
              onClick={() => lifecycle.mutate('activate')}
            >
              <Power className="mr-2 h-4 w-4" />Activate
            </Button>
          )}
          <Button variant="danger" disabled={remove.isPending} onClick={requestDelete}>
            <Trash2 className="mr-2 h-4 w-4" />Archive
          </Button>
        </div>
      </div>
      {(remove.error || lifecycle.error) ? (
        <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          {(remove.error ?? lifecycle.error) instanceof Error
            ? (remove.error ?? lifecycle.error)?.message
            : 'The requested operation failed.'}
        </p>
      ) : null}
      <Card>
        <CardHeader><CardTitle>Resource details</CardTitle></CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Identifier</p>
            <p className="mt-1 font-mono text-sm text-foreground">{item.id}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Status</p>
            <p className="mt-1"><StatusBadge status={item.is_active ? 'active' : 'inactive'} /></p>
          </div>
          <div className="md:col-span-2">
            <p className="text-sm font-medium text-muted-foreground">Configuration</p>
            <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-muted p-3 text-sm text-foreground">
              {JSON.stringify(item.config, null, 2)}
            </pre>
          </div>
        </CardContent>
      </Card>
      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Archive this resource?"
        description="The resource is retained as a tombstone and can be restored through the governed API."
        confirmLabel="Archive resource"
        variant="danger"
        onConfirm={executeDelete}
      />
    </main>
  );
};
