/**
 * Platform Settings Detail Page
 * 
 * Displays detailed information about a platform setting (read-only).
 */
import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { platformService } from '../services/platform-service';
import { ArrowLeft, Settings } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ErrorState } from '@/components/ui';

export const PlatformSettingsDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: setting, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-setting', id],
    queryFn: () => id ? platformService.settings.get(id) : Promise.reject(new Error('No ID')),
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
          message="Failed to load platform setting. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!setting) {
    return (
      <div className="p-8">
        <div className="text-center">
          <p className="text-muted-foreground">Platform setting not found</p>
          <Button onClick={() => navigate('/platform/settings')} className="mt-4">
            Back to Platform Settings
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate('/platform/settings')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Platform Setting Details</h1>
      </div>

      <Card className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <Settings className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-xl font-semibold">{setting.key}</h2>
              <p className="text-sm text-muted-foreground">ID: {setting.id}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Key</label>
              <div className="mt-1 text-sm font-mono">{setting.key}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Is Secret</label>
              <div className="mt-1">
                <StatusBadge status={setting.is_secret ? 'active' : 'inactive'} />
              </div>
            </div>

            <div className="col-span-2">
              <label className="text-sm font-medium text-muted-foreground">Value</label>
              <div className="mt-1 text-sm font-mono bg-muted p-2 rounded">
                {setting.is_secret ? '••••••••' : setting.value}
              </div>
            </div>

            {setting.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <div className="mt-1 text-sm">{setting.description}</div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-muted-foreground">Tenant ID</label>
              <div className="mt-1 text-sm">{setting.tenant_id || 'Platform-wide'}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Created At</label>
              <div className="mt-1 text-sm">{new Date(setting.created_at).toLocaleString()}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Updated At</label>
              <div className="mt-1 text-sm">{new Date(setting.updated_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};
