/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Permission Sets Page
 *
 * Lists and manages permission sets for the current tenant.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, KeyRound, Search, Edit, Trash2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { securityService, type PermissionSet } from '../services/security-service';
import { useState, useDeferredValue } from 'react';
import { toast } from 'sonner';

export const PermissionSetsPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const { data: permissionSets, isLoading, error, refetch } = useQuery({
    queryKey: ['security-permission-sets', deferredSearchQuery],
    queryFn: () => securityService.permissionSets.list({
      search: deferredSearchQuery || undefined,
    }),
    refetchInterval: 60000, // Refetch every minute
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => securityService.permissionSets.delete(id),
    onSuccess: () => {
      toast.success('Permission set deleted successfully');
      void queryClient.invalidateQueries({ queryKey: ['security-permission-sets'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to delete permission set';
      toast.error(message);
    },
  });

  const filteredPermissionSets = permissionSets?.filter((set) => {
    if (deferredSearchQuery) {
      const query = deferredSearchQuery.toLowerCase();
      return (
        set.name?.toLowerCase().includes(query) ||
        set.description?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const handleDelete = (permissionSet: PermissionSet) => {
    if (confirm(`Are you sure you want to delete permission set "${permissionSet.name}"?`)) {
      deleteMutation.mutate(permissionSet.id!);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <ErrorState
          message="Failed to load permission sets. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Permission Sets</h1>
          <p className="text-muted-foreground">Manage reusable collections of permissions</p>
        </div>
        <Button onClick={() => navigate('/security-access-control/permission-sets/create')}>
          <Plus className="w-4 h-4 mr-2" />
          Create Permission Set
        </Button>
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search permission sets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>
      </Card>

      {/* Permission Sets List */}
      {filteredPermissionSets && filteredPermissionSets.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredPermissionSets.map((set) => (
            <Card
              key={set.id}
              className="p-6 hover:shadow-lg transition-all"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
                    <KeyRound className="w-5 h-5 text-primary-main" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg text-foreground">{set.name}</h3>
                  </div>
                </div>
              </div>

              {set.description && (
                <p className="text-sm text-muted-foreground mb-4">{set.description}</p>
              )}

              <div className="space-y-2 text-sm mb-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium">Permissions:</span>
                  <span>{set.permission_count ?? 0}</span>
                </div>
                {set.default_duration_days && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="font-medium">Default Duration:</span>
                    <span>{set.default_duration_days} days</span>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 pt-4 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/security-access-control/permission-sets/${set.id}`)}
                  className="flex-1"
                >
                  <Edit className="w-4 h-4 mr-2" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDelete(set)}
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={KeyRound}
          title="No permission sets found"
          description="Create your first permission set to get started."
          action={{
            label: 'Create Permission Set',
            onClick: () => navigate('/security-access-control/permission-sets/create'),
          }}
        />
      )}
    </div>
  );
};
