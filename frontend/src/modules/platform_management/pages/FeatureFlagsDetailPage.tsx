/**
 * Feature Flags Detail Page
 * 
 * Displays detailed information about a feature flag (read-only).
 */
import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { platformService } from '../services/platform-service';
import { ArrowLeft, Flag } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ErrorState } from '@/components/ui';

export const FeatureFlagsDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: flag, isLoading, error, refetch } = useQuery({
    queryKey: ['feature-flag', id],
    queryFn: () => id ? platformService.featureFlags.get(id) : Promise.reject(new Error('No ID')),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load feature flag. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!flag) {
    return (
      <div className="p-8">
        <div className="text-center">
          <p className="text-muted-foreground">Feature flag not found</p>
          <Button onClick={() => navigate('/platform/feature-flags')} className="mt-4">
            Back to Feature Flags
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate('/platform/feature-flags')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Feature Flag Details</h1>
      </div>

      <Card className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <Flag className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-xl font-semibold">{flag.key}</h2>
              <p className="text-sm text-muted-foreground">ID: {flag.id}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Key</label>
              <div className="mt-1 text-sm font-mono">{flag.key}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <div className="mt-1">
                <StatusBadge status={flag.enabled ? 'active' : 'inactive'} />
              </div>
            </div>

            {flag.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <div className="mt-1 text-sm">{flag.description}</div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-muted-foreground">Tenant ID</label>
              <div className="mt-1 text-sm">{flag.tenant_id || 'Platform-wide'}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Created At</label>
              <div className="mt-1 text-sm">{new Date(flag.created_at).toLocaleString()}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Updated At</label>
              <div className="mt-1 text-sm">{new Date(flag.updated_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};
