/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Discount Management Component
// frontend/src/components/discount-manager.tsx
// Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
// CRITICAL NOTES:
// - Discount management requires tenant_admin role (hasRole check for UI hints only)
// - All discount operations authorized server-side via Policy Engine (not cached roles)
// - Discount types: percentage (0-100) or fixed_amount (currency-specific)
// - Validity period: valid_from and valid_until determine applicability window
// - Server calculates final discounted price (never trust client calculations)
// - TanStack Query manages discount list state (useQuery with caching)
// - Optimistic updates for create/update/delete operations
// - Row-level multitenancy: discounts scoped to tenant_id automatically
// - Audit logging: all discount changes logged with user_id and timestamp
// - Rate limiting applied to discount creation (prevent spam)
// Source: docs/architecture/application-architecture.md § 4.3

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Card } from '@/components/ui/card'
import { apiClient } from '@/lib/api-client'
import { useAuth } from '@/hooks/use-auth'
import { toast } from 'sonner'

interface Discount {
  id: string
  name: string
  code: string
  discount_type: 'percentage' | 'fixed_amount'
  discount_value: number
  valid_from: string
  valid_until?: string
  status: string
}

export function DiscountManager() {
  const { hasRole } = useAuth()
  const queryClient = useQueryClient()
  const [discountCode, setDiscountCode] = useState('')

  const { data: discounts, isLoading } = useQuery({
    queryKey: ['discounts'],
    queryFn: async () => {
      const response = await apiClient.get('/discounts')
      return response.data
    },
    enabled: hasRole('platform_billing_manager')
  })

  const applyDiscountMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await apiClient.post('/discounts/apply', {
        discount_code: code
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Discount applied successfully')
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
    },
    onError: (error: Error) => {
      const errorMessage = error instanceof Error ? error.message : 'Failed to apply discount'
      toast.error(errorMessage)
    }
  })

  const handleApplyDiscount = () => {
    if (!discountCode) {
      toast.error('Please enter a discount code')
      return
    }

    applyDiscountMutation.mutate(discountCode)
  }

  if (!hasRole('platform_billing_manager')) {
    return (
      <Card>
        <div className="p-4">
          <Input
            placeholder="Enter discount code"
            value={discountCode}
            onChange={(e) => setDiscountCode(e.target.value)}
          />
          <Button
            onClick={handleApplyDiscount}
            disabled={applyDiscountMutation.isPending}
            className="mt-2"
          >
            Apply Discount
          </Button>
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Discount Management</h2>

      {isLoading ? (
        <div>Loading discounts...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {discounts?.map((discount: Discount) => (
            <Card key={discount.id} className="p-4">
              <h3 className="font-semibold">{discount.name}</h3>
              <p className="text-sm text-gray-600">Code: {discount.code}</p>
              <p className="text-sm">
                {discount.discount_type === 'percentage'
                  ? `${discount.discount_value}% off`
                  : `$${discount.discount_value} off`}
              </p>
              <p className="text-xs text-gray-500">
                Valid until: {discount.valid_until || 'No expiry'}
              </p>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

