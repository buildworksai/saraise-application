/**
 * System Health Page
 * 
 * Displays system health dashboard.
 */
import { useQuery } from '@tanstack/react-query';
import { platformService } from '../services/platform-service';
import { Activity, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ErrorState } from '@/components/ui';

export const SystemHealthPage = () => {
  const { data: healthList, isLoading: isLoadingList } = useQuery({
    queryKey: ['system-health-list'],
    queryFn: () => platformService.health.list(),
  });

  const { data: healthSummary, isLoading: isLoadingSummary } = useQuery({
    queryKey: ['system-health-summary'],
    queryFn: () => platformService.health.getSummary(),
  });

  if (isLoadingList || isLoadingSummary) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'degraded':
        return <AlertTriangle className="w-5 h-5 text-yellow-500" />;
      case 'unhealthy':
        return <XCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Activity className="w-5 h-5 text-muted-foreground" />;
    }
  };

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">System Health</h1>
        <p className="text-muted-foreground mt-2">Monitor platform service health and status</p>
      </div>

      {/* Health Summary */}
      {healthSummary && (
        <Card className="p-6 mb-6">
          <div className="flex items-center gap-4 mb-4">
            <Activity className="w-6 h-6 text-primary" />
            <h2 className="text-xl font-semibold">Health Summary</h2>
          </div>
          <div className="grid grid-cols-4 gap-4">
            <div className="p-4 bg-muted/30 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Overall Status</p>
              <div className="flex items-center gap-2">
                {getStatusIcon(healthSummary.status)}
                <p className="text-lg font-semibold capitalize">{healthSummary.status}</p>
              </div>
            </div>
            <div className="p-4 bg-muted/30 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Healthy</p>
              <p className="text-lg font-semibold text-green-500">{healthSummary.healthy}</p>
            </div>
            <div className="p-4 bg-muted/30 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Degraded</p>
              <p className="text-lg font-semibold text-yellow-500">{healthSummary.degraded}</p>
            </div>
            <div className="p-4 bg-muted/30 rounded-lg">
              <p className="text-sm text-muted-foreground mb-1">Unhealthy</p>
              <p className="text-lg font-semibold text-red-500">{healthSummary.unhealthy}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Health Services List */}
      <Card className="overflow-hidden">
        <div className="p-6 border-b">
          <h2 className="text-xl font-semibold">Service Health</h2>
        </div>
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Service
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Latency
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Last Check
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {healthList && healthList.length > 0 ? (
              healthList.map((health) => (
                <tr key={health.service} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{health.service}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(health.status)}
                      <StatusBadge status={health.status === 'healthy' ? 'active' : health.status === 'degraded' ? 'warning' : 'error'} />
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {health.latency_ms}ms
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {new Date(health.last_check).toLocaleString()}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-muted-foreground">
                  No health data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
