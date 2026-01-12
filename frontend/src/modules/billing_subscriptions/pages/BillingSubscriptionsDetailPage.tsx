/**
 * BillingSubscriptions Detail Page
 * 
 * Displays resource details and allows editing.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { billing_subscriptionsService } from '../services/billing_subscriptions-service';
import type { Subscription } from '../contracts';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

export const BillingSubscriptionsDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: resource, isLoading } = useQuery({
    queryKey: ['billing_subscriptions-subscription', id],
    queryFn: () => billing_subscriptionsService.getSubscription(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (resourceId: string) => billing_subscriptionsService.deleteSubscription(resourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['billing_subscriptions-resources'] });
      toast.success('Resource deleted successfully');
      navigate('/billing-subscriptions');
    },
    onError: () => {
      toast.error('Failed to delete resource. Please try again.');
    },
  });

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this resource?')) {
      await deleteMutation.mutateAsync(id!);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="text-gray-600">Loading resource...</div>
      </div>
    );
  }

  if (!resource) {
    return (
      <div className="p-8">
        <div className="text-red-600">Resource not found</div>
      </div>
    );
  }

  const resourceData = resource as Subscription;

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Subscription {String(resourceData.id)}</h1>
          <p className="mt-2 text-gray-600">Plan: {String(resourceData.plan)}</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => navigate('/billing-subscriptions/' + id + '/edit')}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <Card className="p-6">
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700">ID</label>
            <p className="mt-1 text-gray-900">{String(resourceData.id)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Plan</label>
            <p className="mt-1 text-gray-900">{String(resourceData.plan)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Status</label>
            <p className="mt-1">
              <span className={resourceData.status === 'active' ? 'px-2 py-1 rounded text-xs bg-green-100 text-green-800' : resourceData.status === 'cancelled' ? 'px-2 py-1 rounded text-xs bg-red-100 text-red-800' : 'px-2 py-1 rounded text-xs bg-gray-100 text-gray-800'}>
                {resourceData.status}
              </span>
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Current Period Start</label>
            <p className="mt-1 text-gray-900">{new Date(resourceData.current_period_start).toLocaleDateString()}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Current Period End</label>
            <p className="mt-1 text-gray-900">{new Date(resourceData.current_period_end).toLocaleDateString()}</p>
          </div>
        </div>
      </Card>
    </div>
  );
};
