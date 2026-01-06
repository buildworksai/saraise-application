/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Platform Dashboard - Overview for Platform Owners
 * 
 * Shows platform-wide metrics, health status, and quick access to key features.
 * Now integrated with real Platform Management API.
 */
import { Link } from 'react-router-dom';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import {
  Users,
  Building2,
  Activity,
  TrendingUp,
  Shield,
  Zap,
  BarChart3,
  Settings,
  Bot,
  AlertCircle,
  CheckCircle2,
  Clock,
  Info,
  Loader2,
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { ChartSkeleton } from '@/components/ui';
import { AreaChart, BarChart, LineChart } from '@/components/charts';
import { Button } from '@/components/ui/Button';
import { exportTimeseriesToCSV } from '@/utils/export';
import { Download } from 'lucide-react';
import { platformService } from '@/modules/platform_management/services/platform-service';
import { MetricCard, HealthStatusBadge, type HealthStatus } from '@/modules/platform_management/components';

// Type definitions for metrics data
interface TenantMetrics {
  total: number;
  active_30d: number;
  new_this_month: number;
  churned_this_month: number;
}

interface UserMetrics {
  total: number;
  active_7d: number;
  active_30d: number;
  new_this_month: number;
}

interface ApiMetrics {
  total_api_calls_30d: number | null;
  average_response_time_ms: number | null;
  error_rate_percent: number | null;
}

interface RevenueMetrics {
  mrr: number | null;
  arr: number | null;
  average_revenue_per_tenant: number | null;
}

interface CompleteMetrics {
  tenant_metrics?: TenantMetrics;
  user_metrics?: UserMetrics;
  api_metrics?: ApiMetrics;
  revenue_metrics?: RevenueMetrics;
}

interface QuickActionCardProps {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  available?: boolean;
}

const QuickActionCard = ({ title, description, icon: Icon, href, available = true }: QuickActionCardProps) => {
  const content = (
    <Card className={`p-6 hover:shadow-lg transition-all ${available ? 'cursor-pointer hover:border-primary-main' : 'opacity-60'}`}>
      <div className="flex items-start gap-4">
        <div className="p-3 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
          <Icon className="w-6 h-6 text-primary-main" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-lg mb-1">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
          {!available && (
            <span className="inline-block mt-2 text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
              Coming Soon
            </span>
          )}
        </div>
      </div>
    </Card>
  );

  if (available) {
    return <Link to={href}>{content}</Link>;
  }

  return content;
};

export const PlatformDashboard = () => {
  const { user } = useAuthStore();

  // Fetch real platform data
  const healthQuery: UseQueryResult<unknown, Error> = useQuery({
    queryKey: ['platform-health'],
    queryFn: () => platformService.health.getCurrent(),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
  const health = healthQuery.data;
  const healthLoading = healthQuery.isLoading;

  const metricsQuery: UseQueryResult<CompleteMetrics, Error> = useQuery<CompleteMetrics>({
    queryKey: ['platform-metrics', '30d'],
    queryFn: () => platformService.metrics.getCurrent('30d', 'complete') as Promise<CompleteMetrics>,
    refetchInterval: 60000, // Refetch every minute
  });
  const metrics = metricsQuery.data;
  const metricsLoading = metricsQuery.isLoading;

  const alertsQuery: UseQueryResult<unknown, Error> = useQuery({
    queryKey: ['platform-alerts', 'active'],
    queryFn: () => platformService.alerts.getActive(),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
  const activeAlerts = alertsQuery.data;
  const alertsLoading = alertsQuery.isLoading;

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
    queryKey: ['platform-metrics-timeseries', '30d', 'day'],
    queryFn: async (): Promise<TimeseriesData> => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call
      const result = await platformService.metrics.getTimeseries('complete', '30d', 'day');
      // Type assertion needed because apiClient.get returns generic type
      // eslint-disable-next-line @typescript-eslint/no-unsafe-return
      return result as TimeseriesData;
    },
    refetchInterval: 60000, // Refetch every minute
  });
  const timeseriesData = timeseriesQuery.data;
  const timeseriesLoading = timeseriesQuery.isLoading;

  const isLoading = healthLoading || metricsLoading || alertsLoading || timeseriesLoading;

  // Extract metrics data from API response
  const healthObj =
    health && typeof health === 'object'
      ? (health as Record<string, unknown>)
      : null;
  const healthStatus: HealthStatus =
    typeof healthObj?.status === 'string'
      ? (healthObj.status as HealthStatus)
      : 'healthy';
  const uptimePercent =
    typeof healthObj?.uptime_percent === 'string' ? healthObj.uptime_percent : null;
  const incidentsCount =
    typeof healthObj?.incidents_count === 'number' ? healthObj.incidents_count : 0;

  const platformStats = {
    tenants: metrics?.tenant_metrics ?? {
      total: 0,
      active_30d: 0,
      new_this_month: 0,
      churned_this_month: 0,
    },
    users: metrics?.user_metrics ?? {
      total: 0,
      active_7d: 0,
      active_30d: 0,
      new_this_month: 0,
    },
    api: metrics?.api_metrics ?? {
      total_api_calls_30d: null,
      average_response_time_ms: null,
      error_rate_percent: null,
    },
    revenue: metrics?.revenue_metrics ?? {
      mrr: null,
      arr: null,
      average_revenue_per_tenant: null,
    },
    health: {
      status: healthStatus,
      uptime: uptimePercent ? `${uptimePercent}%` : 'N/A',
      incidents: incidentsCount,
    },
  };

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-center">
            <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-primary-main" />
            <p className="text-muted-foreground">Loading platform data...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">
          Platform Dashboard
        </h1>
        <p className="text-muted-foreground">
          Welcome back, {user?.email}. Monitor platform health, metrics, and operations.
        </p>
      </div>

      {/* Platform Health Alert */}
      {healthObj ? (
        <div className="mb-6">
          <HealthStatusBadge 
            status={platformStats.health.status}
            uptime={platformStats.health.uptime}
          />
        </div>
      ) : null}

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Total Tenants"
          value={platformStats.tenants.total}
          icon={Building2}
          trend={{ value: `+${platformStats.tenants.new_this_month} this month`, isPositive: true }}
          description={`${platformStats.tenants.active_30d} active`}
        />
        <MetricCard
          title="Total Users"
          value={platformStats.users.total.toLocaleString()}
          icon={Users}
          trend={{ value: `+${platformStats.users.new_this_month} this month`, isPositive: true }}
          description={`${platformStats.users.active_7d.toLocaleString()} active (7d)`}
        />
        <MetricCard
          title="API Calls (30d)"
          value={typeof platformStats.api.total_api_calls_30d === 'number' ? platformStats.api.total_api_calls_30d.toLocaleString() : 'N/A'}
          icon={Zap}
          trend={{ value: typeof platformStats.api.average_response_time_ms === 'number' ? `${platformStats.api.average_response_time_ms}ms avg` : 'N/A', isPositive: true }}
          description={typeof platformStats.api.error_rate_percent === 'number' ? `${platformStats.api.error_rate_percent}% error rate` : 'Error rate N/A'}
        />
        <MetricCard
          title="Monthly Recurring Revenue"
          value={typeof platformStats.revenue.mrr === 'number' ? `$${(platformStats.revenue.mrr / 1000).toFixed(0)}k` : 'N/A'}
          icon={TrendingUp}
          trend={{ value: typeof platformStats.revenue.arr === 'number' ? `$${platformStats.revenue.arr.toLocaleString()} ARR` : 'N/A', isPositive: true }}
          description={typeof platformStats.revenue.average_revenue_per_tenant === 'number' ? `$${platformStats.revenue.average_revenue_per_tenant}/tenant avg` : 'Avg/tenant N/A'}
        />
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
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.api_calls, 'api_calls')}
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
            <AreaChart
              data={timeseriesData.data.api_calls.map((point) => ({
                date: point.date,
                calls: point.value ?? 0,
              }))}
              dataKey="calls"
              xAxisKey="date"
              areas={[{ dataKey: 'calls', name: 'API Calls', color: 'hsl(var(--primary))' }]}
              height={250}
            />
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              API call data not available
            </div>
          )}
        </Card>

        {/* Tenant Growth */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Tenant Growth (Last 30 Days)</h3>
            {timeseriesData?.data?.tenants && timeseriesData.data.tenants.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.tenants, 'tenant_growth')}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
            )}
          </div>
          {timeseriesLoading ? (
            <ChartSkeleton height={250} />
          ) : timeseriesData?.data?.tenants && timeseriesData.data.tenants.length > 0 ? (
            <LineChart
              data={timeseriesData.data.tenants.map((point) => ({
                date: point.date,
                tenants: point.value ?? 0,
              }))}
              dataKey="tenants"
              xAxisKey="date"
              lines={[{ dataKey: 'tenants', name: 'Total Tenants', color: 'hsl(var(--primary))' }]}
              height={250}
            />
          ) : platformStats.tenants.total > 0 ? (
            <BarChart
              data={[
                { period: 'This Month', tenants: platformStats.tenants.new_this_month },
                { period: 'Active (30d)', tenants: platformStats.tenants.active_30d },
                { period: 'Total', tenants: platformStats.tenants.total },
              ]}
              dataKey="tenants"
              xAxisKey="period"
              bars={[{ dataKey: 'tenants', name: 'Tenants', color: 'hsl(var(--primary))' }]}
              height={250}
            />
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              Tenant data not available
            </div>
          )}
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <QuickActionCard
            title="AI Agent Management"
            description="Create, manage, and monitor AI agents across all tenants"
            icon={Bot}
            href="/ai-agents"
            available={true}
          />
          <QuickActionCard
            title="Tenant Management"
            description="View, create, and manage tenant accounts and subscriptions"
            icon={Building2}
            href="/tenant-management"
            available={true}
          />
          <QuickActionCard
            title="Platform Analytics"
            description="Deep dive into platform metrics, usage patterns, and trends"
            icon={BarChart3}
            href="/platform/analytics"
            available={false}
          />
          <QuickActionCard
            title="System Health"
            description="Monitor infrastructure health, alerts, and incidents"
            icon={Activity}
            href="/platform/health"
            available={false}
          />
          <QuickActionCard
            title="Security Dashboard"
            description="View security posture, threats, and compliance status"
            icon={Shield}
            href="/platform/security"
            available={false}
          />
          <QuickActionCard
            title="Platform Settings"
            description="Configure platform-wide settings, features, and policies"
            icon={Settings}
            href="/platform/settings"
            available={false}
          />
        </div>
      </div>

      {/* Recent Activity / Coming Soon */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <Clock className="w-5 h-5 text-primary-main" />
            <h3 className="text-xl font-semibold">Recent Activity</h3>
          </div>
          <div className="space-y-3">
            <div className="text-sm text-muted-foreground">
              Activity feed will be available in the full Platform Management module.
            </div>
            <div className="pt-4 border-t border-border">
              <p className="text-xs text-muted-foreground">
                This will show: tenant provisioning events, module installations, security alerts, and system changes.
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <AlertCircle className="w-5 h-5 text-primary-main" />
            <h3 className="text-xl font-semibold">System Alerts</h3>
          </div>
          <div className="space-y-3">
            {alertsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-primary-main" />
              </div>
            ) : Array.isArray(activeAlerts) && activeAlerts.length > 0 ? (
              (activeAlerts as unknown[]).map((alertUnknown) => {
                const alertObj =
                  alertUnknown && typeof alertUnknown === 'object'
                    ? (alertUnknown as Record<string, unknown>)
                    : null;
                const id = typeof alertObj?.id === 'string' ? alertObj.id : null;
                if (!id) return null;
                return (
                  <div key={id} className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-red-900 dark:text-red-100">
                          {typeof alertObj?.title === 'string' ? alertObj.title : 'Alert'}
                        </p>
                        <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                          {typeof alertObj?.description === 'string' ? alertObj.description : ''}
                        </p>
                        {typeof alertObj?.severity === 'string' && (
                          <span className="inline-block mt-2 text-xs bg-red-100 dark:bg-red-900/40 px-2 py-1 rounded">
                            {alertObj.severity}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                <div>
                  <p className="text-sm font-medium">All systems operational</p>
                  <p className="text-xs text-muted-foreground">No active alerts</p>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Implementation Status Notice */}
      <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5" />
          <div>
            <p className="font-semibold text-blue-900 dark:text-blue-100 mb-1">
              Platform Management Module - Week 5 Implementation
            </p>
            <p className="text-sm text-blue-700 dark:text-blue-300">
              Backend API is operational. Full dashboards (Operations, Infrastructure, Business, Security, Tenant Health, Cost) are being implemented.
              This dashboard now shows real-time data from the Platform Management API.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

