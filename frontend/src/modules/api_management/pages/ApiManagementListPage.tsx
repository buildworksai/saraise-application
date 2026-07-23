import { useDeferredValue, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Settings } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui';
import { QUERY_KEYS, ROUTES, type ApiManagementResource } from '../contracts';
import { api_managementService } from '../services/api_management-service';

const resourceColumns = ['Name', 'Description', 'Status', 'Actions'] as const;

// eslint-disable-next-line complexity, max-lines-per-function -- server filtering, pagination, fail-closed policy, and lifecycle states are intentionally explicit.
export function ApiManagementListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>();
  const [pendingDelete, setPendingDelete] = useState<ApiManagementResource | null>(null);
  const deferredSearch = useDeferredValue(search.trim());

  useEffect(() => { document.title = 'API Management resources · SARAISE'; }, []);

  const configuration = useQuery({
    queryKey: QUERY_KEYS.RUNTIME_CONFIGURATION,
    queryFn: api_managementService.getRuntimeConfiguration,
  });
  const policy = configuration.data?.document;
  const filters = {
    search: deferredSearch || undefined,
    ordering: policy?.default_ordering,
    is_active: activeFilter,
    page,
    page_size: policy?.page_size,
  };
  const resources = useQuery({
    queryKey: QUERY_KEYS.RESOURCES(filters),
    queryFn: () => api_managementService.listResources(filters),
    enabled: Boolean(policy?.feature_enabled),
    placeholderData: (previous) => previous,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.ROOT });
  const lifecycle = useMutation({
    mutationFn: (resource: ApiManagementResource) => resource.is_active
      ? api_managementService.deactivateResource(resource.id)
      : api_managementService.activateResource(resource.id),
    onSuccess: async () => { await refresh(); toast.success('Resource state updated'); },
    onError: () => toast.error('The state transition was rejected.'),
  });
  const restore = useMutation({
    mutationFn: (resourceId: string) => api_managementService.restoreResource(resourceId),
    onSuccess: async () => { await refresh(); toast.success('Resource restored'); },
    onError: () => toast.error('The restore operation was rejected.'),
  });
  const archive = useMutation({
    mutationFn: (resource: ApiManagementResource) => api_managementService.deleteResource(resource.id),
    onSuccess: async (_result, resource) => { setPendingDelete(null); await refresh(); toast.success('Resource archived', { action: { label: 'Restore', onClick: () => restore.mutate(resource.id) } }); },
    onError: () => toast.error('The archive operation was rejected.'),
  });

  if (configuration.isLoading) return <div className="p-8" role="status">Loading tenant configuration…</div>;
  if (configuration.error || !policy) {
    return <div className="p-8"><ErrorState title="Configuration unavailable" message="Resource operations are disabled because the tenant policy could not be loaded." onRetry={() => { void configuration.refetch(); }} /></div>;
  }
  if (!policy.feature_enabled) {
    return <div className="p-8"><ErrorState title="API Management is disabled" message="The tenant configuration currently disables this capability." /></div>;
  }
  if (resources.isLoading) return <div className="p-8" role="status" aria-label="Loading resources"><TableSkeleton rows={policy.table_skeleton_rows} columns={resourceColumns.length} /></div>;
  if (resources.error) {
    return <div className="p-8"><ErrorState message={resources.error instanceof Error ? resources.error.message : 'Resources could not be loaded.'} onRetry={() => { void resources.refetch(); }} /></div>;
  }

  const items = resources.data?.results ?? [];
  const canSearch = policy.search_fields.length > 0;

  return (
    <main className="space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-3xl font-bold text-foreground">API Management</h1><p className="text-sm text-muted-foreground">Tenant-isolated API resources governed by versioned policy.</p></div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(ROUTES.CONFIGURATION)}><Settings className="mr-2 h-4 w-4" />Configuration</Button>
          <Button onClick={() => navigate(ROUTES.RESOURCE_CREATE)}><Plus className="mr-2 h-4 w-4" />Create resource</Button>
        </div>
      </header>

      <Card className="p-6">
        <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px]">
          <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input aria-label="Search resources" placeholder={canSearch ? `Search ${policy.search_fields.join(' or ')}…` : 'Search disabled by tenant policy'} value={search} disabled={!canSearch} onChange={(event) => { setSearch(event.target.value); setPage(1); }} className="pl-10" />
          </div>
          <select aria-label="Filter status" className="rounded-md border bg-background px-3 py-2 text-sm" disabled={!policy.filter_fields.includes('is_active')} value={activeFilter === undefined ? '' : String(activeFilter)} onChange={(event) => { setActiveFilter(event.target.value === '' ? undefined : event.target.value === 'true'); setPage(1); }}><option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select>
        </div>
        {items.length === 0 ? (
          <EmptyState icon={Plus} title={deferredSearch ? 'No matching resources' : 'No resources yet'} description={deferredSearch ? 'Change the server-side search term.' : 'Create the first governed API resource.'} action={deferredSearch ? undefined : { label: 'Create resource', onClick: () => navigate(ROUTES.RESOURCE_CREATE) }} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b text-left">{resourceColumns.map((column) => <th key={column} className={column === 'Actions' ? 'p-2 text-right' : 'p-2'}>{column}</th>)}</tr></thead>
              <tbody>{items.map((resource) => (
                <tr key={resource.id} className="border-b hover:bg-muted/40">
                  <td className="p-2"><button onClick={() => navigate(ROUTES.RESOURCE_DETAIL(resource.id))} className="text-primary hover:underline">{resource.name}</button></td>
                  <td className="p-2 text-muted-foreground">{resource.description || 'No description'}</td>
                  <td className="p-2"><span className={resource.is_active ? 'rounded bg-primary/10 px-2 py-1 text-xs text-primary' : 'rounded bg-muted px-2 py-1 text-xs text-muted-foreground'}>{resource.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td className="p-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => navigate(ROUTES.RESOURCE_DETAIL(resource.id))}>View</Button>
                    {resource.is_active && policy.deactivation_enabled ? <Button size="sm" variant="ghost" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate(resource)}>Deactivate</Button> : null}
                    {!resource.is_active && policy.activation_enabled ? <Button size="sm" variant="ghost" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate(resource)}>Activate</Button> : null}
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setPendingDelete(resource)}>Archive</Button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {resources.data && resources.data.count > policy.page_size ? <nav aria-label="Resource pages" className="mt-4 flex items-center justify-end gap-2"><Button variant="outline" size="sm" disabled={!resources.data.previous} onClick={() => setPage((value) => value - 1)}>Previous</Button><span className="text-sm text-muted-foreground">Page {page}</span><Button variant="outline" size="sm" disabled={!resources.data.next} onClick={() => setPage((value) => value + 1)}>Next</Button></nav> : null}
      </Card>

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => { if (!open && !archive.isPending) setPendingDelete(null); }} title="Archive API resource?" description={policy.deletion_confirmation_message} size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" disabled={archive.isPending} onClick={() => setPendingDelete(null)}>Cancel</Button><Button variant="danger" disabled={!pendingDelete || archive.isPending} onClick={() => { if (pendingDelete) archive.mutate(pendingDelete); }}>{archive.isPending ? 'Archiving…' : 'Archive'}</Button></div>
      </Dialog>
    </main>
  );
}
