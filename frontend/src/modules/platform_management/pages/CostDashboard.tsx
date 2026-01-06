/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Cost Optimization Dashboard
 * 
 * Shows resource costs, cost per tenant, optimization recommendations, and cost trends.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, DollarSign, TrendingDown, TrendingUp, Lightbulb, BarChart3, Download } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ChartSkeleton } from '@/components/ui';
import { AreaChart } from '@/components/charts';
import { exportTimeseriesToCSV } from '@/utils/export';
import { platformService } from '../services/platform-service';
import { TimeRangeSelector, type TimeRange } from '../components/TimeRangeSelector';
import { useState } from 'react';

export const CostDashboard = () => {
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['platform-metrics', 'revenue', timeRange],
    queryFn: () => platformService.metrics.getCurrent(timeRange, 'revenue'),
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
    queryKey: ['platform-metrics-timeseries', 'revenue', timeRange, 'day'],
    queryFn: async (): Promise<TimeseriesData> => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call
      const result = await platformService.metrics.getTimeseries('revenue', timeRange, 'day');
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

  const revenueMetrics = metrics as { mrr?: number | null; arr?: number | null; average_revenue_per_tenant?: number | null } | undefined;

  // CRITICAL: Do not estimate or fabricate costs.
  // Until a real cost tracking pipeline exists (Billing/Subscriptions + usage metering),
  // cost metrics are "not configured".
  const costTrackingConfigured = false;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Cost Optimization</h1>
          <p className="text-muted-foreground">Monitor resource costs and identify optimization opportunities</p>
        </div>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
      </div>

      {/* Cost Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Total Monthly Cost</p>
              <p className="text-3xl font-bold text-foreground">
                N/A
              </p>
              {!costTrackingConfigured && (
                <p className="text-xs text-muted-foreground mt-1">Cost tracking not configured</p>
              )}
            </div>
            <DollarSign className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Cost per Tenant</p>
              <p className="text-3xl font-bold text-foreground">
                N/A
              </p>
              {!costTrackingConfigured && (
                <p className="text-xs text-muted-foreground mt-1">Requires real usage + billing data</p>
              )}
            </div>
            <TrendingDown className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Potential Savings</p>
              <p className="text-3xl font-bold text-foreground">
                N/A
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {costTrackingConfigured ? 'From optimizations' : 'No data available'}
              </p>
            </div>
            <Lightbulb className="w-8 h-8 text-yellow-600 dark:text-yellow-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Cost Efficiency</p>
              <p className="text-3xl font-bold text-foreground">
                N/A
              </p>
              <p className="text-xs mt-1 text-muted-foreground">
                {costTrackingConfigured ? 'Measured' : 'No data'}
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>
      </div>

      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Cost Tracking Status</h2>
        <Card className="p-6">
          <div className="text-muted-foreground">
            <p className="mb-2">
              Cost dashboards require **real cost ingestion** (infrastructure billing + usage metering) and are not configured yet.
            </p>
            <p className="text-sm">
              Current revenue metrics: MRR {typeof revenueMetrics?.mrr === 'number' ? `$${revenueMetrics.mrr.toLocaleString()}` : 'N/A'} ·
              ARR {typeof revenueMetrics?.arr === 'number' ? `$${revenueMetrics.arr.toLocaleString()}` : 'N/A'}
            </p>
          </div>
        </Card>
      </div>

      {/* Revenue Trend Chart (since cost tracking not configured) */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Revenue Trend</h2>
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Monthly Recurring Revenue (MRR)</h3>
            {timeseriesData?.data?.revenue && timeseriesData.data.revenue.some((p) => p.value !== null) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportTimeseriesToCSV(timeseriesData.data.revenue, 'revenue_trend_cost')}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
            )}
          </div>
          {timeseriesLoading ? (
            <ChartSkeleton height={300} />
          ) : timeseriesData?.data?.revenue?.some((p) => p.value !== null) ? (
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
          ) : (
            <div className="flex items-center justify-center h-[300px] text-muted-foreground">
              <div className="text-center">
                <BarChart3 className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Revenue trend data not available</p>
                <p className="text-sm mt-2">Cost trend charts will be available when cost tracking is configured.</p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
