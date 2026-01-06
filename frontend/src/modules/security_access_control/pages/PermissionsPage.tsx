/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Permissions Page
 * 
 * Lists all available permissions (platform-level, read-only).
 */
import { useQuery } from '@tanstack/react-query';
import { Key, Search } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { securityService } from '../services/security-service';
import { useState, useDeferredValue } from 'react';

export const PermissionsPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [moduleFilter, setModuleFilter] = useState<string>('');

  const { data: permissions, isLoading, error, refetch } = useQuery({
    queryKey: ['security-permissions', moduleFilter, deferredSearchQuery],
    queryFn: () => securityService.permissions.list({
      module: moduleFilter || undefined,
      search: deferredSearchQuery || undefined,
    }),
  });

  const filteredPermissions = permissions?.filter((permission) => {
    if (deferredSearchQuery) {
      const query = deferredSearchQuery.toLowerCase();
      return (
        (permission.permission_string ?? '').toLowerCase().includes(query) ||
        (permission.module ?? '').toLowerCase().includes(query) ||
        (permission.object ?? '').toLowerCase().includes(query) ||
        (permission.action ?? '').toLowerCase().includes(query) ||
        (permission.name ?? '').toLowerCase().includes(query)
      );
    }
    return true;
  });

  // Get unique modules for filter
  const modules = Array.from(new Set(permissions?.map((p) => p.module).filter((m): m is string => Boolean(m)) ?? []));

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
          message="Failed to load permissions. Please check your connection and try again."
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
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Permissions</h1>
        <p className="text-muted-foreground">View all available permissions (read-only)</p>
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search permissions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="w-48">
            <Select
              value={moduleFilter}
              onChange={(e) => setModuleFilter(e.target.value)}
              options={[
                { value: '', label: 'All Modules' },
                ...modules.map((module): { value: string; label: string } => ({ value: module, label: module })),
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Permissions List */}
      {filteredPermissions && filteredPermissions.length > 0 ? (
        <div className="space-y-4">
          {filteredPermissions.map((permission) => (
            <Card key={permission.id} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="p-2 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
                    <Key className="w-5 h-5 text-primary-main" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <code className="text-sm font-mono font-semibold text-foreground">
                        {permission.permission_string}
                      </code>
                    </div>
                    {permission.name && (
                      <p className="text-sm text-muted-foreground mb-2">{permission.name}</p>
                    )}
                    {permission.description && (
                      <p className="text-sm text-muted-foreground">{permission.description}</p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                      <span>Module: {permission.module}</span>
                      <span>Object: {permission.object}</span>
                      <span>Action: {permission.action}</span>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Key}
          title="No permissions found"
          description="No permissions match your search criteria."
        />
      )}
    </div>
  );
};

