/**
 * Quota Management Page
 *
 * Displays current usage vs limits and allows quota management.
 */
import { useQuery } from '@tanstack/react-query';
import { BarChart3, Users, HardDrive, Zap, AlertCircle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { quotaService } from '../services/quota-service';
import { cn } from '@/lib/utils';

export const QuotaManagementPage = () => {
  const { data: quotas, isLoading, error, refetch } = useQuery({
    queryKey: ['billing-quotas'],
    queryFn: quotaService.getQuotas,
  });

  const getUsagePercentage = (used: number, limit: number): number => {
    if (limit <= 0) return 0; // Unlimited
    return Math.min((used / limit) * 100, 100);
  };

  const getUsageColor = (percentage: number): string => {
    if (percentage >= 90) return 'bg-red-500';
    if (percentage >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={4} columns={2} />
      </div>
    );
  }

  if (error) {
    return <ErrorState message="Failed to load quota information" onRetry={() => void refetch()} />;
  }

  if (!quotas) {
    return <EmptyState title="No quota information" description="Quota information is not available." />;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <BarChart3 className="h-8 w-8" />
          Quota Management
        </h1>
        <p className="text-muted-foreground mt-2">
          Monitor your resource usage and limits
        </p>
      </div>

      {/* Usage Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Active Users */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-blue-500" />
              <h3 className="font-semibold">Active Users</h3>
            </div>
            {quotas.users.used >= quotas.users.limit * 0.9 && (
              <AlertCircle className="h-5 w-5 text-yellow-500" />
            )}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Used</span>
              <span className="font-semibold">
                {quotas.users.used} / {quotas.users.limit > 0 ? quotas.users.limit : 'Unlimited'}
              </span>
            </div>
            {quotas.users.limit > 0 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className={cn(
                    "h-2 rounded-full transition-all",
                    getUsageColor(getUsagePercentage(quotas.users.used, quotas.users.limit))
                  )}
                  style={{ width: `${getUsagePercentage(quotas.users.used, quotas.users.limit)}%` }}
                />
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              {quotas.users.limit > 0
                ? `${Math.round(getUsagePercentage(quotas.users.used, quotas.users.limit))}% used`
                : 'Unlimited'}
            </div>
          </div>
        </Card>

        {/* Storage */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-green-500" />
              <h3 className="font-semibold">Storage</h3>
            </div>
            {quotas.storage.used >= quotas.storage.limit * 0.9 && (
              <AlertCircle className="h-5 w-5 text-yellow-500" />
            )}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Used</span>
              <span className="font-semibold">
                {quotas.storage.used.toFixed(2)} GB / {quotas.storage.limit > 0 ? `${quotas.storage.limit} GB` : 'Unlimited'}
              </span>
            </div>
            {quotas.storage.limit > 0 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className={cn(
                    "h-2 rounded-full transition-all",
                    getUsageColor(getUsagePercentage(quotas.storage.used, quotas.storage.limit))
                  )}
                  style={{ width: `${getUsagePercentage(quotas.storage.used, quotas.storage.limit)}%` }}
                />
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              {quotas.storage.limit > 0
                ? `${Math.round(getUsagePercentage(quotas.storage.used, quotas.storage.limit))}% used`
                : 'Unlimited'}
            </div>
          </div>
        </Card>

        {/* API Calls */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-purple-500" />
              <h3 className="font-semibold">API Calls (Today)</h3>
            </div>
            {quotas.api_calls.used >= quotas.api_calls.limit * 0.9 && (
              <AlertCircle className="h-5 w-5 text-yellow-500" />
            )}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Used</span>
              <span className="font-semibold">
                {formatNumber(quotas.api_calls.used)} / {quotas.api_calls.limit > 0 ? formatNumber(quotas.api_calls.limit) : 'Unlimited'}
              </span>
            </div>
            {quotas.api_calls.limit > 0 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className={cn(
                    "h-2 rounded-full transition-all",
                    getUsageColor(getUsagePercentage(quotas.api_calls.used, quotas.api_calls.limit))
                  )}
                  style={{ width: `${getUsagePercentage(quotas.api_calls.used, quotas.api_calls.limit)}%` }}
                />
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              {quotas.api_calls.limit > 0
                ? `${Math.round(getUsagePercentage(quotas.api_calls.used, quotas.api_calls.limit))}% used`
                : 'Unlimited'}
            </div>
          </div>
        </Card>
      </div>

      {/* Warning for high usage */}
      {(quotas.users.used >= quotas.users.limit * 0.9 ||
        quotas.storage.used >= quotas.storage.limit * 0.9 ||
        quotas.api_calls.used >= quotas.api_calls.limit * 0.9) && (
        <Card className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mt-0.5" />
            <div>
              <h3 className="font-semibold text-yellow-900 dark:text-yellow-100">
                Approaching Quota Limits
              </h3>
              <p className="text-sm text-yellow-800 dark:text-yellow-200 mt-1">
                You are approaching one or more quota limits. Consider upgrading your plan to avoid service interruptions.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};
