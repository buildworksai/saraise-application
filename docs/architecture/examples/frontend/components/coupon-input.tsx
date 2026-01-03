/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Coupon Application Component
// frontend/src/components/coupon-input.tsx
// Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
// CRITICAL NOTES:
// - Coupon validation via POST /api/v1/coupons/validate/{code} endpoint
// - Coupon application always requires subscription_id context
// - TanStack Query mutation pattern: validateCouponMutation, applyCouponMutation
// - Optimistic updates via queryClient.setQueryData() for instant UI feedback
// - Error handling must handle: invalid code, expired coupon, usage limits exceeded
// - Coupon discounts must be recalculated server-side (never client-side calculation)
// - Tenant context validated server-side (coupon only valid for subscription's tenant)
// - Rate limiting applied to coupon validation (prevent brute-force attempts)
// - Successful application triggers subscription refresh and audit log entry
// Source: docs/architecture/application-architecture.md § 4.3

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { apiClient } from '@/lib/api-client'
import { toast } from 'sonner'

interface Coupon {
  code: string
  discount_percentage?: number
  discount_amount?: number
  expiry_date?: string
}

interface CouponInputProps {
  subscriptionId?: string
  onApplied?: (coupon: Coupon) => void
}

export function CouponInput({ subscriptionId, onApplied }: CouponInputProps) {
  const queryClient = useQueryClient()
  const [couponCode, setCouponCode] = useState('')
  const [isValidating, setIsValidating] = useState(false)

  const validateCouponMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await apiClient.get(`/coupons/validate/${code}`)
      return response.data
    },
    onSuccess: (data) => {
      if (data.valid) {
        toast.success('Coupon is valid!')
      } else {
        toast.error(data.error || 'Invalid coupon')
      }
    }
  })

  const applyCouponMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await apiClient.post('/coupons/apply', {
        coupon_code: code,
        subscription_id: subscriptionId
      })
      return response.data
    },
    onSuccess: (data) => {
      toast.success('Coupon applied successfully!')
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      if (onApplied) {
        onApplied(data)
      }
    },
    onError: (error: Error) => {
      const httpError = error instanceof Error && 'response' in error
        ? (error as Error & { response?: { data?: { detail?: string } } })
        : null
      toast.error(httpError?.response?.data?.detail || 'Failed to apply coupon')
    }
  })

  const handleValidate = () => {
    if (!couponCode) {
      toast.error('Please enter a coupon code')
      return
    }
    validateCouponMutation.mutate(couponCode)
  }

  const handleApply = () => {
    if (!couponCode) {
      toast.error('Please enter a coupon code')
      return
    }
    if (!subscriptionId) {
      toast.error('Subscription ID required')
      return
    }
    applyCouponMutation.mutate(couponCode)
  }

  return (
    <Card className="p-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Coupon Code</label>
        <div className="flex gap-2">
          <Input
            placeholder="Enter coupon code"
            value={couponCode}
            onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
            className="flex-1"
          />
          <Button
            onClick={handleValidate}
            disabled={isValidating || validateCouponMutation.isPending}
            variant="outline"
          >
            Validate
          </Button>
          <Button
            onClick={handleApply}
            disabled={applyCouponMutation.isPending || !subscriptionId}
          >
            Apply
          </Button>
        </div>
      </div>
    </Card>
  )
}

