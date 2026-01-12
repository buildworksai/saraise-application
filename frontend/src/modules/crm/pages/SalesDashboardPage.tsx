/**
 * Sales Dashboard Page
 *
 * Displays sales metrics, pipeline, and forecasting.
 */
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, DollarSign, Target, BarChart3 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { WeightedPipelineChart } from '../components/WeightedPipelineChart';
import { AIInsights } from '../components/AIInsights';
import { crmService } from '../services/crm-service';

export const SalesDashboardPage = () => {
  const navigate = useNavigate();

  const { data: pipeline } = useQuery({
    queryKey: ['crm-forecasting-pipeline'],
    queryFn: () => crmService.getPipeline({ period: 90 }),
  });

  const { data: winRate } = useQuery({
    queryKey: ['crm-forecasting-win-rate'],
    queryFn: () => crmService.getWinRate({ period: 90 }),
  });

  const { data: opportunities } = useQuery({
    queryKey: ['crm-opportunities'],
    queryFn: () => crmService.listOpportunities({ status: 'open' }),
  });

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Sales Dashboard</h1>
        <Button onClick={() => navigate('/crm/opportunities')}>View All Opportunities</Button>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Pipeline</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${pipeline?.total_pipeline_value.toLocaleString() || '0'}
            </div>
            <p className="text-xs text-muted-foreground">All open opportunities</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Weighted Pipeline</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${pipeline?.weighted_pipeline_value.toLocaleString() || '0'}
            </div>
            <p className="text-xs text-muted-foreground">Probability-weighted</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{winRate?.win_rate.toFixed(1) || '0'}%</div>
            <p className="text-xs text-muted-foreground">Last 90 days</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Open Opportunities</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{opportunities?.length || 0}</div>
            <p className="text-xs text-muted-foreground">Active deals</p>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline Chart */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Pipeline by Stage</CardTitle>
        </CardHeader>
        <CardContent>
          {opportunities && opportunities.length > 0 ? (
            <WeightedPipelineChart opportunities={opportunities} />
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground">
              No opportunities to display
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pipeline Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Pipeline Overview</CardTitle>
          </CardHeader>
          <CardContent>
            {pipeline && (
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Total Value</span>
                    <span className="font-medium">${pipeline.total_pipeline_value.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Weighted Value</span>
                    <span className="font-medium">${pipeline.weighted_pipeline_value.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Opportunities</span>
                    <span className="font-medium">{pipeline.opportunity_count}</span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Win Rate Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            {winRate && (
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Win Rate</span>
                    <span className="font-medium">{winRate.win_rate.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Won</span>
                    <span className="font-medium">{winRate.won_count}</span>
                  </div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Lost</span>
                    <span className="font-medium">{winRate.lost_count}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Total Closed</span>
                    <span className="font-medium">{winRate.total_closed}</span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      <div className="mt-6">
        <AIInsights />
      </div>
    </div>
  );
};
