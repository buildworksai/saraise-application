/**
 * Tenant Module Management Page
 * 
 * Displays and manages tenant modules.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, TenantModule } from '../contracts';
import { Plus, Search, Package } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const TenantModuleManagementPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: modules, isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-modules', deferredSearchTerm],
    queryFn: () => apiClient.get<TenantModule[]>(ENDPOINTS.MODULES.LIST),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(ENDPOINTS.MODULES.DELETE(id)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant-modules'] });
      toast.success('Tenant module deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete tenant module. Please try again.');
    },
  });

  const toggleEnabledMutation = useMutation({
    mutationFn: ({ id, isEnabled }: { id: string; isEnabled: boolean }) =>
      isEnabled
        ? apiClient.post(ENDPOINTS.MODULES.ENABLE(id), {})
        : apiClient.post(ENDPOINTS.MODULES.DISABLE(id), {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant-modules'] });
      toast.success('Module status updated successfully');
    },
    onError: () => {
      toast.error('Failed to update module status. Please try again.');
    },
  });

  const filteredModules = modules?.filter((module) => {
    return deferredSearchTerm === '' || 
      module.module_id.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      module.module_name?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this tenant module?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleToggleEnabled = async (id: string, isEnabled: boolean) => {
    await toggleEnabledMutation.mutateAsync({ id, isEnabled: !isEnabled });
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={5} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load tenant modules. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredModules || filteredModules.length === 0) {
    if (modules?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Tenant Modules</h1>
            <Button onClick={() => navigate('/tenant-management/modules/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Add Module
            </Button>
          </div>
          <EmptyState
            icon={Package}
            title="No tenant modules yet"
            description="Add modules to tenants to enable functionality."
            action={{
              label: "Add Module",
              onClick: () => navigate('/tenant-management/modules/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Tenant Modules</h1>
        <Button onClick={() => navigate('/tenant-management/modules/create')}>
          <Plus className="w-4 h-4" />
          Add Module
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search modules..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Modules Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Module ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Module Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tenant ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredModules?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No modules found matching your search
                </td>
              </tr>
            ) : (
              filteredModules?.map((module) => (
                <tr key={module.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{module.module_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {module.module_name || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {module.tenant_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={module.is_enabled ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/tenant-management/modules/${module.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => void handleToggleEnabled(module.id, module.is_enabled)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      {module.is_enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(module.id);
                      }}
                      className="text-destructive hover:opacity-80"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
