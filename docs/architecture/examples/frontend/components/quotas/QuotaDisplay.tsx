/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: User Quota Display Component
// frontend/src/components/quotas/QuotaDisplay.tsx
// Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
// CRITICAL NOTES:
// - Quotas tracked per-tenant and per-user (row-level multitenancy enforcement)
// - Usage metrics fetched from GET /api/v1/quotas/usage (real-time usage tracking)
// - Progress bars display current_usage / limit ratio (visual feedback)
// - Warning badges shown when usage >80% of limit (user-friendly alerts)
// - Violations count represents times quota exceeded (historical metric)
// - Server enforces quota limits (client display is informational only)
// - Quota enforcement happens during API calls (rate-limiter backend service)
// - Exceeded quota returns 429 Too Many Requests (standard HTTP status)
// - Tenant admins can adjust quotas server-side (requires authorization check)
// - Quota reset occurs per billing period (configured per plan/subscription)
// Source: docs/architecture/application-architecture.md § 4.3

import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/lib/api-client'
import { useAuth } from '@/hooks/use-auth'

interface QuotaStats {
  [key: string]: {
    current_usage: number
    limit: number
    remaining: number
    usage_percent: number
    violations: number
    warning_sent: boolean
  }
}

export function QuotaDisplay() {
  const { hasTenantRole } = useAuth()

  const { data: stats, isLoading } = useQuery({
    queryKey: ['quotas', 'usage'],
    queryFn: async () => {
      const response = await apiClient.get('/quotas/usage')
      return response.data as QuotaStats
    },
    enabled: hasTenantRole('tenant_admin')
  })

  if (!hasTenantRole('tenant_admin') || isLoading) {
    return null
  }

  return (
    <Card className="p-4">
      <h3 className="font-semibold mb-4">Subscription Quotas</h3>
      <div className="space-y-4">
        {Object.entries(stats || {}).map(([quotaType, quota]) => {
          const isWarning = quota.usage_percent > 80
          const isCritical = quota.usage_percent > 95

          return (
            <div key={quotaType} className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium capitalize">
                  {quotaType.replace('_', ' ')}
                </span>
                <div className="flex items-center gap-2">
                  <span className={`text-sm ${isCritical ? 'text-red-500' : isWarning ? 'text-yellow-500' : ''}`}>
                    {quota.current_usage} / {quota.limit}
                  </span>
                  {quota.warning_sent && (
                    <Badge variant="warning">Warning Sent</Badge>
                  )}
                  {quota.violations > 0 && (
                    <Badge variant="destructive">{quota.violations} Violations</Badge>
                  )}
                </div>
              </div>
              <Progress
                value={quota.usage_percent}
                className={isCritical ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : ''}
              />
            </div>
          )
        })}
      </div>
    </Card>
  )
}

