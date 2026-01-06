/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Business Metrics Dashboard
 * 
 * Shows tenant growth, user growth, MRR/ARR, tenant churn rate, and customer acquisition metrics.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, Building2, Users, TrendingUp, DollarSign, ArrowUpRight, Download } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ChartSkeleton } from '@/components/ui';
import { AreaChart, LineChart } from '@/components/charts';
import { exportTimeseriesToCSV } from '@/utils/export';
import { MetricCard } from '../components';
import { platformService } from '../services/platform-service';
import { TimeRangeSelector, type TimeRange } from '../components/TimeRangeSelector';
import { useState } from 'react';

export const BusinessDashboard = () => {
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');

  const { data: metrics, isLoading: metricsLoading } = useQuery<unknown, Error>({
    queryKey: ['platform-metrics', 'complete', timeRange],
    queryFn: () => platformService.metrics.getCurrent(timeRange, 'complete'),
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
    queryKey: ['platform-metrics-timeseries', 'complete', timeRange, 'day'],
    queryFn: async (): Promise<TimeseriesData> => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call
      const result = await platformService.metrics.getTimeseries('complete', timeRange, 'day');
      // eslint-disable-next-line @typescript-eslint/no-unsafe-return
      return result as TimeseriesData;
    },
    refetchInterval: 60000,
  });
  const timeseriesData = timeseriesQuery.data;
  const timeseriesLoading = timeseriesQuery.isLoading;

  const isLoading = metricsLoading || timeseriesLoading;

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary-main" />
        </div>
      </div>
    );
  }

  const tenantMetrics = metrics as { tenant_metrics?: { total?: number; active_30d?: number; new_this_month?: number; churned_this_month?: number; growth_rate?: string } } | undefined;
  const userMetrics = metrics as { user_metrics?: { total?: number; active_7d?: number; active_30d?: number; new_this_month?: number } } | undefined;
  const revenueMetrics = metrics as { revenue_metrics?: { mrr?: number; arr?: number; average_revenue_per_tenant?: number; customer_lifetime_value?: number; customer_acquisition_cost?: number } } | undefined;

  const tenants = tenantMetrics?.tenant_metrics ?? { total: 0, active_30d: 0, new_this_month: 0, churned_this_month: 0, growth_rate: null as string | null };
  const users = userMetrics?.user_metrics ?? { total: 0, active_7d: 0, active_30d: 0, new_this_month: 0 };
  const revenue = revenueMetrics?.revenue_metrics ?? { mrr: null as number | null, arr: null as number | null, average_revenue_per_tenant: null as number | null, customer_lifetime_value: null as number | null, customer_acquisition_cost: null as number | null };

  const churnRate = tenants.total && tenants.total > 0
    ? ((tenants.churned_this_month ?? 0) / tenants.total * 100).toFixed(2)
    : null;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Business Metrics</h1>
          <p className="text-muted-foreground">Track tenant growth, revenue, and customer metrics</p>
        </div>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Total Tenants"
          value={tenants.total ?? 0}
          icon={Building2}
          trend={{ 
            value: tenants.growth_rate ? `${tenants.growth_rate} growth` : 'N/A',
            isPositive: true
          }}
          description={`${tenants.active_30d ?? 0} active (30d)`}
        />
        <MetricCard
          title="Total Users"
          value={(users.total ?? 0).toLocaleString()}
          icon={Users}
          trend={{ 
            value: `+${users.new_this_month ?? 0} this month`, 
            isPositive: true 
          }}
          description={`${(users.active_30d ?? 0).toLocaleString()} active (30d)`}
        />
        <MetricCard
          title="Monthly Recurring Revenue"
          value={typeof revenue.mrr === 'number' ? `$${(revenue.mrr / 1000).toFixed(0)}k` : 'N/A'}
          icon={DollarSign}
          trend={{ 
            value: typeof revenue.arr === 'number' ? `$${revenue.arr.toLocaleString()} ARR` : 'N/A',
            isPositive: true 
          }}
          description={typeof revenue.average_revenue_per_tenant === 'number' ? `$${revenue.average_revenue_per_tenant}/tenant avg` : 'Avg/tenant N/A'}
        />
        <MetricCard
          title="Tenant Churn Rate"
          value={churnRate ? `${churnRate}%` : 'N/A'}
          icon={TrendingUp}
          trend={{ 
            value: `${tenants.churned_this_month ?? 0} churned this month`, 
            isPositive: (tenants.churned_this_month ?? 0) === 0
          }}
          description="Monthly churn rate"
        />
      </div>

      {/* Revenue Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Customer Lifetime Value</p>
              <p className="text-3xl font-bold text-foreground">
                {typeof revenue.customer_lifetime_value === 'number' ? `$${revenue.customer_lifetime_value.toLocaleString()}` : 'N/A'}
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Customer Acquisition Cost</p>
              <p className="text-3xl font-bold text-foreground">
                {typeof revenue.customer_acquisition_cost === 'number' ? `$${revenue.customer_acquisition_cost.toLocaleString()}` : 'N/A'}
              </p>
            </div>
            <DollarSign className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">LTV:CAC Ratio</p>
              <p className="text-3xl font-bold text-foreground">
                {revenue.customer_acquisition_cost && revenue.customer_lifetime_value && revenue.customer_acquisition_cost > 0
                  ? (revenue.customer_lifetime_value / revenue.customer_acquisition_cost).toFixed(2)
                  : 'N/A'}
              </p>
            </div>
            <ArrowUpRight className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>
      </div>

      {/* Growth Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Tenant Growth</h3>
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
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              Tenant growth data not available
            </div>
          )}
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">User Growth</h3>
            {timeseriesData?.data?.users && timeseriesData.data.users.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.users, 'user_growth')}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
            )}
          </div>
          {timeseriesLoading ? (
            <ChartSkeleton height={250} />
          ) : timeseriesData?.data?.users && timeseriesData.data.users.length > 0 ? (
            <LineChart
              data={timeseriesData.data.users.map((point) => ({
                date: point.date,
                users: point.value ?? 0,
              }))}
              dataKey="users"
              xAxisKey="date"
              lines={[{ dataKey: 'users', name: 'Total Users', color: 'hsl(var(--primary))' }]}
              height={250}
            />
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              User growth data not available
            </div>
          )}
        </Card>
      </div>

      {/* Revenue Chart */}
      {timeseriesData?.data?.revenue?.some((p) => p.value !== null) && (
        <div className="mt-6">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Revenue Trend (MRR)</h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.revenue, 'revenue_trend')}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
            </div>
            {timeseriesLoading ? (
              <ChartSkeleton height={300} />
            ) : (
              <AreaChart
                data={timeseriesData.data.revenue.map((point) => ({
                  date: point.date,
                  revenue: point.value ?? 0,
                }))}
                dataKey="revenue"
                xAxisKey="date"
                areas={[{ dataKey: 'revenue', name: 'MRR', color: 'hsl(var(--primary))' }]}
                height={300}
              />
            )}
          </Card>
        </div>
      )}
    </div>
  );
};

