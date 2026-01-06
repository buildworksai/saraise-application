/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Tenant Health Dashboard
 * 
 * Shows per-tenant metrics, tenant status (active, restricted, suspended), usage statistics, and health scores.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, Building2, CheckCircle2, AlertTriangle, XCircle, Activity } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { platformService } from '../services/platform-service';
import { tenantService } from '@/modules/tenant_management/services/tenant-service';
import { formatDistanceToNow } from 'date-fns';

export const TenantHealthDashboard = () => {
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['platform-metrics', 'tenant'],
    queryFn: () => platformService.metrics.getCurrent('30d', 'tenant'),
    refetchInterval: 60000,
  });

  // Fetch real tenant data from Tenant Management API
  const { data: tenants, isLoading: tenantsLoading } = useQuery({
    queryKey: ['tenants', 'all'],
    queryFn: () => tenantService.tenants.list(),
    refetchInterval: 60000,
  });

  // Fetch health scores for all tenants
  const { data: healthScores, isLoading: healthScoresLoading } = useQuery({
    queryKey: ['tenant-health-scores'],
    queryFn: async () => {
      const tenantIds = (tenants ?? [])
        .map((t) => t.id)
        .filter((id): id is string => typeof id === 'string' && id.length > 0);
      if (tenantIds.length === 0) return [];
      // Fetch health scores for each tenant
      const scoresPromises = tenantIds.map(async (tenantId) => {
        try {
          const scores = await tenantService.tenants.getHealthScores(tenantId, {
            date_from: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          });
          return { tenantId, latestScore: scores?.[0] };
        } catch {
          return { tenantId, latestScore: null };
        }
      });
      return Promise.all(scoresPromises);
    },
    enabled: !!tenants && tenants.length > 0,
    refetchInterval: 60000,
  });

  // Fetch resource usage for all tenants
  const { data: resourceUsage, isLoading: resourceUsageLoading } = useQuery({
    queryKey: ['tenant-resource-usage'],
    queryFn: async () => {
      const tenantIds = (tenants ?? [])
        .map((t) => t.id)
        .filter((id): id is string => typeof id === 'string' && id.length > 0);
      if (tenantIds.length === 0) return [];
      const usagePromises = tenantIds.map(async (tenantId) => {
        try {
          const usage = await tenantService.tenants.getResourceUsage(tenantId, {
            date_from: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          });
          return { tenantId, latestUsage: usage?.[0] };
        } catch {
          return { tenantId, latestUsage: null };
        }
      });
      return Promise.all(usagePromises);
    },
    enabled: !!tenants && tenants.length > 0,
    refetchInterval: 60000,
  });

  const isLoading = metricsLoading || tenantsLoading || healthScoresLoading || resourceUsageLoading;

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary-main" />
        </div>
      </div>
    );
  }

  const tenantMetrics = metrics as { total?: number; active_30d?: number; new_this_month?: number; churned_this_month?: number } | undefined;

  // Build tenant health data from real API responses
  const tenantHealthData = (tenants ?? []).map((tenant) => {
    const healthScore = healthScores?.find((s) => s.tenantId === tenant.id)?.latestScore;
    const usage = resourceUsage?.find((u) => u.tenantId === tenant.id)?.latestUsage;
    
    return {
      id: tenant.id,
      name: tenant.name,
      status: tenant.status ?? 'active',
      users: usage?.active_users ?? 0,
      healthScore: healthScore?.overall_score ?? 0,
      lastActivity: tenant.updated_at ? formatDistanceToNow(new Date(tenant.updated_at), { addSuffix: true }) : 'Unknown',
    };
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />;
      case 'restricted':
        return <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />;
      case 'suspended':
        return <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />;
      default:
        return <Activity className="w-5 h-5 text-muted-foreground" />;
    }
  };

  const getHealthScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600 dark:text-green-400';
    if (score >= 70) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Tenant Health</h1>
        <p className="text-muted-foreground">Monitor per-tenant metrics, status, and health scores</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Total Tenants</p>
              <p className="text-3xl font-bold text-foreground">
                {tenantMetrics?.total ?? 0}
              </p>
            </div>
            <Building2 className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Active Tenants</p>
              <p className="text-3xl font-bold text-foreground">
                {tenantMetrics?.active_30d ?? 0}
              </p>
            </div>
            <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">New This Month</p>
              <p className="text-3xl font-bold text-foreground">
                {tenantMetrics?.new_this_month ?? 0}
              </p>
            </div>
            <Activity className="w-8 h-8 text-primary-main" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Churned This Month</p>
              <p className="text-3xl font-bold text-foreground">
                {tenantMetrics?.churned_this_month ?? 0}
              </p>
            </div>
            <XCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
          </div>
        </Card>
      </div>

      {/* Tenant Health Table */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Tenant Health Overview</h2>
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Tenant</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Users</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Health Score</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Last Activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tenantHealthData.length > 0 ? (
                  tenantHealthData.map((tenant) => (
                    <tr key={tenant.id} className="hover:bg-muted/50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="font-medium text-foreground">{tenant.name}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          {getStatusIcon(tenant.status)}
                          <span className="capitalize">{tenant.status}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-foreground">
                        {tenant.users.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <span className={`font-semibold ${getHealthScoreColor(tenant.healthScore)}`}>
                            {tenant.healthScore > 0 ? tenant.healthScore : 'N/A'}
                          </span>
                          {tenant.healthScore > 0 && (
                            <div className="w-24 bg-muted rounded-full h-2">
                              <div 
                                className={`h-2 rounded-full ${tenant.healthScore >= 90 ? 'bg-green-600' : tenant.healthScore >= 70 ? 'bg-yellow-600' : 'bg-red-600'}`}
                                style={{ width: `${tenant.healthScore}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">
                        {tenant.lastActivity}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                      No tenants found. Create your first tenant to see health metrics here.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
};
