/**
 * Feature Flags Page
 * 
 * Displays and manages feature flags with toggle functionality.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type FeatureFlag } from '../services/platform-service';
import { Plus, Search, Flag, ToggleLeft, ToggleRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { CreateFeatureFlagDialog } from '../components/CreateFeatureFlagDialog';
import { EditFeatureFlagDialog } from '../components/EditFeatureFlagDialog';

export const FeatureFlagsPage = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedFlag, setSelectedFlag] = useState<FeatureFlag | null>(null);

  const { data: flags, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-feature-flags'],
    queryFn: platformService.featureFlags.list,
  });

  const toggleMutation = useMutation({
    mutationFn: (id: string) => platformService.featureFlags.toggle(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-feature-flags'] });
      toast.success('Feature flag toggled successfully');
    },
    onError: () => {
      toast.error('Failed to toggle feature flag. Please try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => platformService.featureFlags.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-feature-flags'] });
      toast.success('Feature flag deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete feature flag. Please try again.');
    },
  });

  const filteredFlags = flags?.filter((flag) => {
    const matchesSearch = deferredSearchTerm === '' ||
      flag.name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      flag.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    return matchesSearch;
  });

  const handleToggle = async (id?: string) => {
    if (!id) {
      toast.error('Unable to toggle feature flag: missing ID');
      return;
    }
    await toggleMutation.mutateAsync(id);
  };

  const handleDelete = async (id?: string) => {
    if (!id) {
      toast.error('Unable to delete feature flag: missing ID');
      return;
    }
    if (window.confirm('Are you sure you want to delete this feature flag?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleEdit = (flag: FeatureFlag) => {
    setSelectedFlag(flag);
    setEditDialogOpen(true);
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
          message="Failed to load feature flags. Please check your connection and try again."
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
          <h1 className="text-3xl font-bold">Feature Flags</h1>
          <p className="text-muted-foreground mt-1">
            Manage feature flags for gradual rollout and A/B testing
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Feature Flag
        </Button>
      </div>

      <Card className="p-6">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search feature flags by name or description..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {filteredFlags?.length === 0 ? (
          <EmptyState
            icon={Flag}
            title="No feature flags found"
            description="Create your first feature flag to get started."
            action={{
              label: 'Create Feature Flag',
              onClick: () => setCreateDialogOpen(true),
            }}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-semibold">Name</th>
                  <th className="text-left p-3 font-semibold">Status</th>
                  <th className="text-left p-3 font-semibold">Rollout</th>
                  <th className="text-left p-3 font-semibold">Description</th>
                  <th className="text-left p-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFlags?.map((flag) => (
                  <tr key={flag.id ?? flag.name} className="border-b hover:bg-muted/50">
                    <td className="p-3 font-mono text-sm">{flag.name}</td>
                    <td className="p-3">
                      <button
                        onClick={() => {
                          void handleToggle(flag.id);
                        }}
                        className="flex items-center gap-2"
                      >
                        {flag.enabled ? (
                          <>
                            <ToggleRight className="h-5 w-5 text-green-600" />
                            <span className="text-sm text-green-600">Enabled</span>
                          </>
                        ) : (
                          <>
                            <ToggleLeft className="h-5 w-5 text-gray-400" />
                            <span className="text-sm text-gray-400">Disabled</span>
                          </>
                        )}
                      </button>
                    </td>
                    <td className="p-3">
                      <span className="text-sm">{flag.rollout_percentage}%</span>
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-muted-foreground">{flag.description ?? '-'}</span>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(flag)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            void handleDelete(flag.id);
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

      <CreateFeatureFlagDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />

      {selectedFlag && (
        <EditFeatureFlagDialog
          open={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          flag={selectedFlag}
        />
      )}
    </div>
  );
};
