/**
 * Create BillingSubscriptions Resource Page
 * 
 * Form for creating a new resource with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { billing_subscriptionsService } from '../services/billing_subscriptions-service';
import type { SubscriptionCreate } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';

const resourceSchema = z.object({
  plan: z.string().min(1, 'Plan is required'),
  billing_cycle: z.enum(['monthly', 'yearly']).optional(),
});

type ResourceFormData = z.infer<typeof resourceSchema>;

export const CreateBillingSubscriptionsResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<ResourceFormData>({
    resolver: zodResolver(resourceSchema),
    defaultValues: {
      plan: '',
      billing_cycle: 'monthly',
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: SubscriptionCreate) => {
      return billing_subscriptionsService.createSubscription(data);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['billing_subscriptions-subscriptions'] });
      toast.success('Subscription created successfully');
      navigate('/billing-subscriptions');
    },
    onError: () => {
      toast.error('Failed to create subscription. Please try again.');
    },
  });

  const onSubmit = async (data: ResourceFormData) => {
    try {
      await createMutation.mutateAsync({
        plan: data.plan,
        billing_cycle: data.billing_cycle,
      });
    } catch (err) {
      console.error('Failed to create subscription:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create BillingSubscriptions Resource</h1>
      </div>

      <Card className="p-6">
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="plan" className="block text-sm font-medium text-gray-700 mb-1">
              Plan ID *
            </label>
            <Input
              id="plan"
              {...form.register('plan')}
              error={form.formState.errors.plan?.message}
              placeholder="Enter plan ID"
            />
          </div>

          <div>
            <label htmlFor="billing_cycle" className="block text-sm font-medium text-gray-700 mb-1">
              Billing Cycle
            </label>
            <select
              id="billing_cycle"
              {...form.register('billing_cycle')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Resource'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/billing-subscriptions')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
