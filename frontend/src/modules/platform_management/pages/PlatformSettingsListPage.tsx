/**
 * Platform Settings List Page
 * 
 * Displays all platform settings (read-only).
 */
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { platformService } from '../services/platform-service';
import { Search, Settings } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const PlatformSettingsListPage = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-settings', deferredSearchTerm],
    queryFn: () => platformService.settings.list({ search: deferredSearchTerm }),
  });

  const filteredSettings = settings?.filter((setting) => {
    return deferredSearchTerm === '' || 
      setting.key.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      setting.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

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
          message="Failed to load platform settings. Please check your connection and try again."
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
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-foreground">Platform Settings</h1>
          </div>
          <EmptyState
            icon={Settings}
            title="No platform settings yet"
            description="Platform settings will appear here once configured."
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Platform Settings</h1>
        <p className="text-muted-foreground mt-2">View platform configuration settings (read-only)</p>
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
                Key
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Secret
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Description
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
                    <div className="text-sm font-medium">{setting.key}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {setting.is_secret ? '••••••••' : setting.value}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={setting.is_secret ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    {setting.description || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/platform/settings/${setting.id}`)}
                      className="text-primary hover:opacity-80"
                    >
                      View
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
