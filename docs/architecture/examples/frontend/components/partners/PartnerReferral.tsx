/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Partner Referral Component
// frontend/src/components/partners/PartnerReferral.tsx
// Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
// CRITICAL NOTES:
// - Referral creation requires tenant-level partner permissions
// - hasTenantRole() used for UI hints only (authorization evaluated server-side)
// - Referral codes generated server-side (unique per partner, immutable)
// - Referral tracking: user_id, referral_code, status, created_at stored server-side
// - Row-level multitenancy: referrals scoped to tenant_id automatically
// - Partner commission calculation server-side (never trust client calculations)
// - TanStack Query handles referral list state and invalidation on update
// - Rate limiting applied to referral creation (prevent abuse)
// - Audit logging captures all referral state changes (security-model.md § 4.2)
// - Commission payouts processed asynchronously via background jobs
// Source: docs/architecture/application-architecture.md § 4.3

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { apiClient } from '@/lib/api-client'
import { useAuth } from '@/hooks/use-auth'
import { toast } from 'sonner'

export function PartnerReferral() {
  const { hasTenantRole } = useAuth()
  const queryClient = useQueryClient()
  const [referralCode, setReferralCode] = useState('')

  const createReferralMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await apiClient.post('/partners/referrals', {
        referral_code: code
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Referral created successfully')
      queryClient.invalidateQueries({ queryKey: ['tenant'] })
    },
    onError: (error: Error) => {
      const httpError = error instanceof Error && 'response' in error
        ? (error as Error & { response?: { data?: { detail?: string } } })
        : null
      toast.error(httpError?.response?.data?.detail || 'Failed to create referral')
    }
  })

  const handleSubmit = () => {
    if (!referralCode) {
      toast.error('Please enter a referral code')
      return
    }

    createReferralMutation.mutate(referralCode)
  }

  if (!hasTenantRole('tenant_admin')) {
    return null
  }

  return (
    <Card className="p-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Partner Referral Code</label>
        <div className="flex gap-2">
          <Input
            placeholder="Enter referral code"
            value={referralCode}
            onChange={(e) => setReferralCode(e.target.value.toUpperCase())}
            className="flex-1"
          />
          <Button
            onClick={handleSubmit}
            disabled={createReferralMutation.isPending}
          >
            Apply
          </Button>
        </div>
      </div>
    </Card>
  )
}

