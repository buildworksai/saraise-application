/**
 * Tenant Settings Page
 * 
 * Displays and manages tenant settings.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, TenantSettings } from '../contracts';
import { Plus, Search, Settings } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const TenantSettingsPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-settings', deferredSearchTerm],
    queryFn: () => apiClient.get<TenantSettings[]>(ENDPOINTS.SETTINGS.LIST),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(ENDPOINTS.SETTINGS.DELETE(id)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings'] });
      toast.success('Tenant setting deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete tenant setting. Please try again.');
    },
  });

  const filteredSettings = settings?.filter((setting) => {
    return deferredSearchTerm === '' || 
      setting.tenant_id.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      setting.setting_key.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this tenant setting?')) {
      await deleteMutation.mutateAsync(id);
    }
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
          message="Failed to load tenant settings. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredSettings || filteredSettings.length === 0) {
    if (settings?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Tenant Settings</h1>
            <Button onClick={() => navigate('/tenant-management/settings/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Setting
            </Button>
          </div>
          <EmptyState
            icon={Settings}
            title="No tenant settings yet"
            description="Create settings to configure tenant behavior."
            action={{
              label: "Create Setting",
              onClick: () => navigate('/tenant-management/settings/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Tenant Settings</h1>
        <Button onClick={() => navigate('/tenant-management/settings/create')}>
          <Plus className="w-4 h-4" />
          Create Setting
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search settings..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Settings Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tenant ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Setting Key
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Setting Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredSettings?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No settings found matching your search
                </td>
              </tr>
            ) : (
              filteredSettings?.map((setting) => (
                <tr key={setting.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{setting.tenant_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{setting.setting_key}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    {setting.setting_value || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {setting.created_at ? new Date(setting.created_at).toLocaleDateString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/tenant-management/settings/${setting.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(setting.id);
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
