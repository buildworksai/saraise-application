/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Rate Limit Indicator Component
// frontend/src/components/rate-limits/RateLimitIndicator.tsx
// Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
// CRITICAL NOTES:
// - Rate limit info extracted from response headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
// - Rate limits enforced server-side (backend RateLimitService per tenant and user)
// - Limits configured per plan/subscription (different tiers have different limits)
// - Client display of remaining requests is informational (real enforcement on backend)
// - 429 Too Many Requests returned when quota exceeded (standard HTTP status)
// - Reset time provided in headers allows client to implement backoff/retry logic
// - Rate limiting prevents abuse and protects platform stability
// - Per-tenant and per-user rate limits enforced separately (isolation)
// - API key and user-based rate limits tracked independently
// - Shared quota across multiple clients for same API key (coordinated via Redis)
// Source: docs/architecture/application-architecture.md § 4.3

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { apiClient } from '@/lib/api-client'

export function RateLimitIndicator() {
  const [rateLimitInfo, setRateLimitInfo] = useState<{
    limit: number
    remaining: number
    reset: string
  } | null>(null)

  useEffect(() => {
    // Get rate limit info from last API response headers
    const lastResponse = apiClient.getLastResponse()
    if (lastResponse) {
      const limit = parseInt(lastResponse.headers['x-ratelimit-limit'] || '0')
      const remaining = parseInt(lastResponse.headers['x-ratelimit-remaining'] || '0')
      const reset = lastResponse.headers['x-ratelimit-reset'] || ''

      if (limit > 0) {
        setRateLimitInfo({ limit, remaining, reset })
      }
    }
  }, [])

  if (!rateLimitInfo) {
    return null
  }

  const usagePercent = ((rateLimitInfo.limit - rateLimitInfo.remaining) / rateLimitInfo.limit) * 100
  const isWarning = usagePercent > 80
  const isCritical = usagePercent > 95

  return (
    <Card className="p-2">
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span>API Rate Limit</span>
          <span className={isCritical ? 'text-red-500' : isWarning ? 'text-yellow-500' : ''}>
            {rateLimitInfo.remaining} / {rateLimitInfo.limit}
          </span>
        </div>
        <Progress
          value={usagePercent}
          className={isCritical ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : ''}
        />
      </div>
    </Card>
  )
}

