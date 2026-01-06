/**
 * Platform Settings Page
 * 
 * Displays and manages platform settings with CRUD operations.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type PlatformSetting } from '../services/platform-service';
import { Plus, Search, Settings } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { CreateSettingDialog } from '../components/CreateSettingDialog';
import { EditSettingDialog } from '../components/EditSettingDialog';

export const SettingsPage = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedSetting, setSelectedSetting] = useState<PlatformSetting | null>(null);

  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-settings'],
    queryFn: platformService.settings.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => platformService.settings.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
      toast.success('Setting deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete setting. Please try again.');
    },
  });

  const filteredSettings = settings?.filter((setting) => {
    const matchesSearch = deferredSearchTerm === '' ||
      setting.key.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      setting.category?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    return matchesSearch;
  });

  const handleDelete = async (id?: string) => {
    if (!id) {
      toast.error('Unable to delete setting: missing ID');
      return;
    }
    if (window.confirm('Are you sure you want to delete this setting?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleEdit = (setting: PlatformSetting) => {
    setSelectedSetting(setting);
    setEditDialogOpen(true);
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load settings. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Platform Settings</h1>
          <p className="text-muted-foreground mt-1">
            Manage platform-wide and tenant-specific configuration settings
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Setting
        </Button>
      </div>

      <Card className="p-6">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search settings by key or category..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {filteredSettings?.length === 0 ? (
          <EmptyState
            icon={Settings}
            title="No settings found"
            description="Create your first platform setting to get started."
            action={{
              label: 'Create Setting',
              onClick: () => setCreateDialogOpen(true),
            }}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-semibold">Key</th>
                  <th className="text-left p-3 font-semibold">Value</th>
                  <th className="text-left p-3 font-semibold">Category</th>
                  <th className="text-left p-3 font-semibold">Type</th>
                  <th className="text-left p-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSettings?.map((setting) => (
                  <tr key={setting.id ?? setting.key} className="border-b hover:bg-muted/50">
                    <td className="p-3 font-mono text-sm">{setting.key}</td>
                    <td className="p-3">
                      {setting.is_secret ? (
                        <span className="text-muted-foreground">********</span>
                      ) : (
                        <span className="text-sm">{setting.value}</span>
                      )}
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-muted-foreground">{setting.category}</span>
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-muted-foreground">{setting.data_type}</span>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(setting)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            void handleDelete(setting.id);
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CreateSettingDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />

      {selectedSetting && (
        <EditSettingDialog
          open={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          setting={selectedSetting}
        />
      )}
    </div>
  );
};
