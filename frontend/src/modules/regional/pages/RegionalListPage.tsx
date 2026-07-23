import { useDeferredValue, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Settings, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import {
  REGIONAL_QUERY_KEYS,
  ROUTES,
  type RegionalResource,
} from '../contracts';
import { regionalService } from '../services/regional-service';
import { useRegionalDocumentTitle } from '../use-regional-document-title';

export const RegionalListPage = () => {
  useRegionalDocumentTitle('Regional resources');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [pendingDelete, setPendingDelete] = useState<RegionalResource | null>(null);
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const resources = useQuery({
    queryKey: [...REGIONAL_QUERY_KEYS.resources, deferredSearchTerm, page],
    queryFn: () => regionalService.listResources(deferredSearchTerm, page),
  });
  const configuration = useQuery({
    queryKey: [...REGIONAL_QUERY_KEYS.configuration('active'), 'active'],
    queryFn: regionalService.getActiveConfiguration,
  });
  const remove = useMutation({
    mutationFn: (id: string) => regionalService.deleteResource(id),
    onSuccess: () => {
      setPendingDelete(null);
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resources });
      toast.success('Resource archived successfully');
    },
    onError: () => toast.error('Failed to archive resource. Please try again.'),
  });

  if (resources.isLoading || configuration.isLoading) {
    return <div className="p-8"><TableSkeleton rows={5} columns={4} /></div>;
  }
  if (resources.isError || configuration.isError || !configuration.data) {
    const error = resources.error ?? configuration.error;
    return (
      <div className="p-8">
        <ErrorState
          message={error instanceof Error ? error.message : 'Failed to load Regional resources.'}
          onRetry={() => {
            void resources.refetch();
            void configuration.refetch();
          }}
        />
      </div>
    );
  }

  const items = resources.data?.results ?? [];
  const requireConfirmation =
    configuration.data.document.workflow.require_delete_confirmation;
  const requestDelete = (item: RegionalResource) => {
    if (requireConfirmation) setPendingDelete(item);
    else remove.mutate(item.id);
  };

  return (
    <main id="main-content" className="space-y-6 p-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Regional resources</h1>
          <p className="mt-2 text-muted-foreground">
            Tenant-scoped regional policies and jurisdiction records.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate(ROUTES.CONFIGURATION)}>
            <Settings className="mr-2 h-4 w-4" />Configuration
          </Button>
          <Button onClick={() => navigate(ROUTES.CREATE)}>
            <Plus className="mr-2 h-4 w-4" />Create resource
          </Button>
        </div>
      </div>
      <Card className="p-6">
        <div className="relative mb-4">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            aria-label="Search resources"
            placeholder={`Search ${configuration.data?.document.resource.search_fields.join(' or ') ?? 'resources'}…`}
            value={searchTerm}
            onChange={(event) => {
              setSearchTerm(event.target.value);
              setPage(1);
            }}
            className="pl-10"
          />
        </div>
        {items.length === 0 ? (
          <EmptyState
            icon={Plus}
            title="No resources found"
            description={searchTerm ? 'No resources match the governed search.' : 'Create the first Regional resource.'}
            action={{ label: 'Create resource', onClick: () => navigate(ROUTES.CREATE) }}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="p-2 text-left">Name</th>
                  <th className="p-2 text-left">Description</th>
                  <th className="p-2 text-left">Status</th>
                  <th className="p-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-border hover:bg-muted/50">
                    <td className="p-2">
                      <button
                        className="font-medium text-primary hover:underline"
                        onClick={() => navigate(ROUTES.DETAIL(item.id))}
                      >
                        {item.name}
                      </button>
                    </td>
                    <td className="p-2 text-muted-foreground">{item.description}</td>
                    <td className="p-2">
                      <StatusBadge status={item.is_active ? 'active' : 'inactive'} />
                    </td>
                    <td className="p-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => navigate(ROUTES.DETAIL(item.id))}>
                        View
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Archive ${item.name}`}
                        disabled={remove.isPending}
                        onClick={() => requestDelete(item)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(resources.data?.previous || resources.data?.next) ? (
          <div className="mt-4 flex items-center justify-between">
            <Button
              variant="outline"
              disabled={!resources.data.previous}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">Page {page}</span>
            <Button
              variant="outline"
              disabled={!resources.data.next}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </Button>
          </div>
        ) : null}
      </Card>
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Archive this resource?"
        description={`${pendingDelete?.name ?? 'This resource'} will be retained as an auditable tombstone.`}
        confirmLabel="Archive resource"
        variant="danger"
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
        }}
      />
    </main>
  );
};
