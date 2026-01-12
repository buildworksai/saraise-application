/**
 * Tenant Resource Usage Page
 * 
 * Displays tenant resource usage metrics.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, TenantResourceUsage } from '../contracts';
import { Search, BarChart } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const TenantResourceUsagePage = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: resourceUsage, isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-resource-usage', deferredSearchTerm],
    queryFn: () => apiClient.get<TenantResourceUsage[]>(ENDPOINTS.RESOURCE_USAGE.LIST),
  });

  const filteredUsage = resourceUsage?.filter((usage) => {
    return deferredSearchTerm === '' || 
      usage.tenant_id.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load resource usage. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredUsage || filteredUsage.length === 0) {
    if (resourceUsage?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-foreground">Resource Usage</h1>
          </div>
          <EmptyState
            icon={BarChart}
            title="No resource usage data yet"
            description="Resource usage metrics will appear here as tenants use the platform."
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Resource Usage</h1>
        <p className="text-muted-foreground mt-2">Monitor tenant resource consumption and limits</p>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search by tenant ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Usage Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tenant ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Resource Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Usage
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Limit
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Period
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredUsage?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No resource usage found matching your search
                </td>
              </tr>
            ) : (
              filteredUsage?.map((usage) => (
                <tr key={usage.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{usage.tenant_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize">
                    {usage.resource_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {usage.usage_value}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {usage.limit_value || 'Unlimited'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {usage.period_start ? new Date(usage.period_start).toLocaleDateString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/tenant-management/resource-usage/${usage.id}`)}
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
