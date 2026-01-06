/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Roles Page
 * 
 * Lists and manages roles for the current tenant.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Shield, Search, Edit, Trash2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { securityService, type Role } from '../services/security-service';
import { useState, useDeferredValue } from 'react';
import { toast } from 'sonner';

export const RolesPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [roleTypeFilter, setRoleTypeFilter] = useState<string>('');
  const [isActiveFilter, setIsActiveFilter] = useState<string>('');

  const { data: roles, isLoading, error, refetch } = useQuery({
    queryKey: ['security-roles', roleTypeFilter, isActiveFilter, deferredSearchQuery],
    queryFn: () => securityService.roles.list({
      role_type: roleTypeFilter || undefined,
      is_active: isActiveFilter === 'true' ? true : isActiveFilter === 'false' ? false : undefined,
      search: deferredSearchQuery || undefined,
    }),
    refetchInterval: 60000, // Refetch every minute
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => securityService.roles.delete(id),
    onSuccess: () => {
      toast.success('Role deleted successfully');
      void queryClient.invalidateQueries({ queryKey: ['security-roles'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to delete role';
      toast.error(message);
    },
  });

  const filteredRoles = roles?.filter((role) => {
    if (deferredSearchQuery) {
      const query = deferredSearchQuery.toLowerCase();
      return (
        role.name?.toLowerCase().includes(query) ||
        role.code?.toLowerCase().includes(query) ||
        role.description?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const handleDelete = (role: Role) => {
    if (role.is_system) {
      toast.error('Cannot delete system roles');
      return;
    }
    if (confirm(`Are you sure you want to delete role "${role.name}"?`)) {
      deleteMutation.mutate(role.id!);
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
          message="Failed to load roles. Please check your connection and try again."
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
          <h1 className="text-4xl font-bold text-foreground mb-2">Roles</h1>
          <p className="text-muted-foreground">Manage roles and their permissions</p>
        </div>
        <Button onClick={() => navigate('/security-access-control/roles/create')}>
          <Plus className="w-4 h-4 mr-2" />
          Create Role
        </Button>
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search roles by name, code, or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="w-48">
            <Select
              value={roleTypeFilter}
              onChange={(e) => setRoleTypeFilter(e.target.value)}
              options={[
                { value: '', label: 'All Types' },
                { value: 'system', label: 'System' },
                { value: 'functional', label: 'Functional' },
                { value: 'custom', label: 'Custom' },
                { value: 'temporary', label: 'Temporary' },
              ]}
            />
          </div>
          <div className="w-48">
            <Select
              value={isActiveFilter}
              onChange={(e) => setIsActiveFilter(e.target.value)}
              options={[
                { value: '', label: 'All Statuses' },
                { value: 'true', label: 'Active' },
                { value: 'false', label: 'Inactive' },
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Roles List */}
      {filteredRoles && filteredRoles.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredRoles.map((role) => (
            <Card
              key={role.id}
              className="p-6 hover:shadow-lg transition-all"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
                    <Shield className="w-5 h-5 text-primary-main" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg text-foreground">{role.name}</h3>
                    <p className="text-sm text-muted-foreground">{role.code}</p>
                  </div>
                </div>
                {role.is_system && (
                  <span className="px-2 py-1 text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
                    System
                  </span>
                )}
              </div>

              {role.description && (
                <p className="text-sm text-muted-foreground mb-4">{role.description}</p>
              )}

              <div className="space-y-2 text-sm mb-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium">Type:</span>
                  <span className="capitalize">{role.role_type}</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium">Permissions:</span>
                  <span>{role.permission_count ?? 0}</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium">Status:</span>
                  <span className={role.is_active ? 'text-green-600' : 'text-red-600'}>
                    {role.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-4 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/security-access-control/roles/${role.id}`)}
                  className="flex-1"
                >
                  <Edit className="w-4 h-4 mr-2" />
                  Edit
                </Button>
                {!role.is_system && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDelete(role)}
                    className="text-red-600 hover:text-red-700"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Shield}
          title="No roles found"
          description="Create your first role to get started with role-based access control."
          action={{
            label: 'Create Role',
            onClick: () => navigate('/security-access-control/roles/create'),
          }}
        />
      )}
    </div>
  );
};

