/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Real-time Operations Dashboard
 * 
 * Shows platform health, active alerts, recent incidents, system uptime, and API response times.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, Activity, AlertTriangle, CheckCircle2, Clock, Zap, Download } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ChartSkeleton } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { exportTimeseriesToCSV } from '@/utils/export';
import { platformService, type PlatformHealth, type PlatformAlert } from '../services/platform-service';
import { HealthStatusBadge, AlertCard, type HealthStatus } from '../components';

export const OperationsDashboard = () => {
  const { data: health, isLoading: healthLoading } = useQuery<PlatformHealth>({
    queryKey: ['platform-health'],
    queryFn: () => platformService.health.getCurrent(),
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  const { data: activeAlerts, isLoading: alertsLoading } = useQuery<PlatformAlert[]>({
    queryKey: ['platform-alerts', 'active'],
    queryFn: () => platformService.alerts.getActive(),
    refetchInterval: 30000,
  });

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['platform-metrics', 'api'],
    queryFn: () => platformService.metrics.getCurrent('30d', 'api'),
    refetchInterval: 60000,
  });

  // Fetch time-series data for charts
  interface TimeseriesDataPoint {
    timestamp: string;
    date: string;
    value: number | null;
  }

  interface TimeseriesData {
    metric_type: string;
    time_range: string;
    interval: string;
    data: {
      api_calls: TimeseriesDataPoint[];
      tenants: TimeseriesDataPoint[];
      users: TimeseriesDataPoint[];
      revenue: TimeseriesDataPoint[];
    };
  }

  const timeseriesQuery = useQuery<TimeseriesData, Error>({
    queryKey: ['platform-metrics-timeseries', 'api', '30d', 'day'],
    queryFn: async (): Promise<TimeseriesData> => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call
      const result = await platformService.metrics.getTimeseries('api', '30d', 'day');
      // eslint-disable-next-line @typescript-eslint/no-unsafe-return
      return result as TimeseriesData;
    },
    refetchInterval: 60000,
  });
  const timeseriesData = timeseriesQuery.data;
  const timeseriesLoading = timeseriesQuery.isLoading;

  const isLoading = healthLoading || alertsLoading || metricsLoading || timeseriesLoading;

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary-main" />
        </div>
      </div>
    );
  }

  const apiMetrics = metrics as { average_response_time_ms?: number; error_rate_percent?: number; total_api_calls_30d?: number } | undefined;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Real-time Operations</h1>
        <p className="text-muted-foreground">Monitor platform health, alerts, and system performance</p>
      </div>

      {/* Platform Health Status */}
      {health ? (
        <div className="mb-6">
          <HealthStatusBadge
            status={(typeof health.status === 'string' ? (health.status as HealthStatus) : 'healthy')}
            uptime="N/A"
          />
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">System Uptime</p>
              <p className="text-3xl font-bold text-foreground">
                N/A
              </p>
            </div>
            <Activity className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Active Incidents</p>
              <p className="text-3xl font-bold text-foreground">
                {activeAlerts?.length ?? 0}
              </p>
            </div>
            <AlertTriangle className="w-8 h-8 text-yellow-600 dark:text-yellow-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Avg Response Time</p>
              <p className="text-3xl font-bold text-foreground">
                {typeof apiMetrics?.average_response_time_ms === 'number' ? `${apiMetrics.average_response_time_ms}ms` : 'N/A'}
              </p>
            </div>
            <Zap className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Error Rate</p>
              <p className="text-3xl font-bold text-foreground">
                {typeof apiMetrics?.error_rate_percent === 'number' ? `${apiMetrics.error_rate_percent}%` : 'N/A'}
              </p>
            </div>
            <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>
      </div>

      {/* Active Alerts */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Active Alerts</h2>
        {alertsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-primary-main" />
          </div>
        ) : activeAlerts && activeAlerts.length > 0 ? (
          <div className="space-y-3">
            {activeAlerts.map((alert) => (
              <AlertCard key={alert.id} alert={alert} />
            ))}
          </div>
        ) : (
          <Card className="p-6">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
              <div>
                <p className="font-medium">All systems operational</p>
                <p className="text-sm text-muted-foreground">No active alerts</p>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* API Calls Over Time */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">API Calls (Last 30 Days)</h3>
            {timeseriesData?.data?.api_calls && timeseriesData.data.api_calls.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.api_calls, 'api_calls_operations')}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
            )}
          </div>
          {timeseriesLoading ? (
            <ChartSkeleton height={250} />
          ) : timeseriesData?.data?.api_calls && timeseriesData.data.api_calls.length > 0 ? (
            <LineChart
              data={timeseriesData.data.api_calls.map((point) => ({
                date: point.date,
                calls: point.value ?? 0,
              }))}
              dataKey="calls"
              xAxisKey="date"
              lines={[{ dataKey: 'calls', name: 'API Calls', color: 'hsl(var(--primary))' }]}
              height={250}
            />
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              API call data not available
            </div>
          )}
        </Card>

        {/* System Health Trend */}
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">System Health Trend</h3>
          {timeseriesLoading ? (
            <ChartSkeleton height={250} />
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              Health trend data will be available when historical health records are saved.
            </div>
          )}
        </Card>
      </div>

      {/* Health Checks */}
      {health?.checks ? (
        <div className="mb-8">
          <h2 className="text-2xl font-semibold mb-4">System Health Checks</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(health.checks).map(([key, value]) => (
              <Card key={key} className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground capitalize">{key.replace('_', ' ')}</p>
                    <p className={`text-lg font-semibold ${value === 'ok' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {String(value)}
                    </p>
                  </div>
                  {value === 'ok' ? (
                    <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      ) : null}

      {/* Recent Activity */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Recent Activity</h2>
        <Card className="p-6">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Clock className="w-5 h-5" />
            <p>Activity feed will show recent platform events, incidents, and system changes.</p>
          </div>
        </Card>
      </div>
    </div>
  );
};
