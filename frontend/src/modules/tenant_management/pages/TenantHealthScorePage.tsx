/**
 * Tenant Health Score Page
 * 
 * Displays tenant health scores and metrics.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, TenantHealthScore } from '../contracts';
import { Search, Heart } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const TenantHealthScorePage = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: healthScores, isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-health-scores', deferredSearchTerm],
    queryFn: () => apiClient.get<TenantHealthScore[]>(ENDPOINTS.HEALTH_SCORES.LIST),
  });

  const filteredScores = healthScores?.filter((score) => {
    return deferredSearchTerm === '' || 
      score.tenant_id.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const getHealthStatus = (score: number) => {
    if (score >= 80) return 'active';
    if (score >= 60) return 'warning';
    return 'error';
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
          message="Failed to load health scores. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredScores || filteredScores.length === 0) {
    if (healthScores?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-foreground">Tenant Health Scores</h1>
          </div>
          <EmptyState
            icon={Heart}
            title="No health scores yet"
            description="Health scores will appear here as they are calculated for tenants."
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Tenant Health Scores</h1>
        <p className="text-muted-foreground mt-2">Monitor tenant health metrics and performance</p>
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

      {/* Health Scores Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tenant ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Health Score
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Calculated At
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredScores?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No health scores found matching your search
                </td>
              </tr>
            ) : (
              filteredScores?.map((score) => (
                <tr key={score.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{score.tenant_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-semibold">{score.health_score}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={getHealthStatus(score.health_score)} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {score.calculated_at ? new Date(score.calculated_at).toLocaleString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/tenant-management/health-scores/${score.id}`)}
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
