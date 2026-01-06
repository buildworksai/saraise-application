/**
 * System Health Page
 * 
 * Displays system health status and metrics.
 */
import { useQuery } from '@tanstack/react-query';
import { platformService } from '../services/platform-service';
import { Activity, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, ErrorState } from '@/components/ui';

export const HealthPage = () => {
  const { data: healthRecords, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-health'],
    queryFn: platformService.health.list,
  });

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['platform-health-summary'],
    queryFn: platformService.health.summary,
  });

  if (isLoading || summaryLoading) {
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
          message="Failed to load health status. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  const getStatusIcon = (status: string | undefined) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="h-5 w-5 text-green-600" />;
      case 'degraded':
        return <AlertTriangle className="h-5 w-5 text-yellow-600" />;
      case 'unhealthy':
        return <XCircle className="h-5 w-5 text-red-600" />;
      default:
        return <Activity className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string | undefined) => {
    switch (status) {
      case 'healthy':
        return 'text-green-600';
      case 'degraded':
        return 'text-yellow-600';
      case 'unhealthy':
        return 'text-red-600';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">System Health</h1>
        <p className="text-muted-foreground mt-1">
          Monitor platform service health and status
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Overall Status</p>
                <p className={`text-2xl font-bold mt-1 ${getStatusColor(summary.status)}`}>
                  {summary.status.charAt(0).toUpperCase() + summary.status.slice(1)}
                </p>
              </div>
              {getStatusIcon(summary.status)}
            </div>
          </Card>

          <Card className="p-6">
            <div>
              <p className="text-sm text-muted-foreground">Healthy</p>
              <p className="text-2xl font-bold mt-1 text-green-600">{summary.healthy}</p>
            </div>
          </Card>

          <Card className="p-6">
            <div>
              <p className="text-sm text-muted-foreground">Degraded</p>
              <p className="text-2xl font-bold mt-1 text-yellow-600">{summary.degraded}</p>
            </div>
          </Card>

          <Card className="p-6">
            <div>
              <p className="text-sm text-muted-foreground">Unhealthy</p>
              <p className="text-2xl font-bold mt-1 text-red-600">{summary.unhealthy}</p>
            </div>
          </Card>
        </div>
      )}

      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">Service Status</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left p-3 font-semibold">Service</th>
                <th className="text-left p-3 font-semibold">Status</th>
                <th className="text-left p-3 font-semibold">Response Time</th>
                <th className="text-left p-3 font-semibold">Last Check</th>
                <th className="text-left p-3 font-semibold">Details</th>
              </tr>
            </thead>
            <tbody>
              {healthRecords?.map((record) => {
                const status = record.status ?? 'unknown';
                return (
                <tr key={record.id ?? record.service_name} className="border-b hover:bg-muted/50">
                  <td className="p-3 font-medium">{record.service_name}</td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(status)}
                      <span className={`text-sm ${getStatusColor(status)}`}>
                        {status.charAt(0).toUpperCase() + status.slice(1)}
                      </span>
                    </div>
                  </td>
                  <td className="p-3">
                    <span className="text-sm">
                      {record.response_time_ms ? `${record.response_time_ms}ms` : '-'}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="text-sm text-muted-foreground">
                      {record.last_check ? new Date(record.last_check).toLocaleString() : '-'}
                    </span>
                  </td>
                  <td className="p-3">
                    {record.error_message ? (
                      <span className="text-sm text-red-600">{record.error_message}</span>
                    ) : (
                      <span className="text-sm text-muted-foreground">-</span>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
