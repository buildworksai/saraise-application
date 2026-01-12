/**
 * Tenant Detail Page
 *
 * Displays tenant details, modules, resource usage, and health scores.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Building2, Package, Activity, Heart, ArrowLeft, Edit, Trash2, Power, PowerOff } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TableSkeleton, ErrorState } from '@/components/ui';
import { tenantService, type Tenant } from '../services/tenant-service';
import { TenantStatusBadge, type TenantStatus } from '../components';

export const TenantDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: tenant, isLoading, error, refetch } = useQuery<Tenant>({
    queryKey: ['tenant', id],
    queryFn: () => tenantService.tenants.get(id!),
    enabled: !!id,
  });

  const { data: modules } = useQuery({
    queryKey: ['tenant-modules', id],
    queryFn: () => tenantService.tenants.getModules(id!),
    enabled: !!id,
  });

  const { data: resourceUsage } = useQuery({
    queryKey: ['tenant-resource-usage', id],
    queryFn: () => tenantService.tenants.getResourceUsage(id!),
    enabled: !!id,
  });

  const { data: healthScores } = useQuery({
    queryKey: ['tenant-health-scores', id],
    queryFn: () => tenantService.tenants.getHealthScores(id!),
    enabled: !!id,
  });

  const suspendMutation = useMutation({
    mutationFn: (id: string) => tenantService.tenants.suspend(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', id] });
      void queryClient.invalidateQueries({ queryKey: ['tenants'] });
      toast.success('Tenant suspended successfully');
    },
    onError: () => {
      toast.error('Failed to suspend tenant. Please try again.');
    },
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => tenantService.tenants.activate(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', id] });
      void queryClient.invalidateQueries({ queryKey: ['tenants'] });
      toast.success('Tenant activated successfully');
    },
    onError: () => {
      toast.error('Failed to activate tenant. Please try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => tenantService.tenants.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenants'] });
      toast.success('Tenant deleted successfully');
      navigate('/tenant-management');
    },
    onError: () => {
      toast.error('Failed to delete tenant. Please try again.');
    },
  });

  const handleSuspend = async () => {
    if (window.confirm('Are you sure you want to suspend this tenant?')) {
      await suspendMutation.mutateAsync(id!);
    }
  };

  const handleActivate = async () => {
    if (window.confirm('Are you sure you want to activate this tenant?')) {
      await activateMutation.mutateAsync(id!);
    }
  };

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this tenant? This action cannot be undone.')) {
      await deleteMutation.mutateAsync(id!);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <TableSkeleton rows={5} columns={2} />
      </div>
    );
  }

  if (error || !tenant) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <ErrorState
          message="Failed to load tenant. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <Button
          variant="ghost"
          onClick={() => {
            navigate('/tenant-management');
          }}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Tenants
        </Button>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
              <Building2 className="w-8 h-8 text-primary-main" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground mb-2">{tenant.name}</h1>
              <p className="text-muted-foreground">{tenant.slug}</p>
            </div>
            <TenantStatusBadge status={(tenant.status ?? 'trial') as TenantStatus} />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => navigate(`/tenant-management/${id}/edit`)}
            >
              <Edit className="w-4 h-4 mr-2" />
              Edit
            </Button>
            {tenant.status === 'active' ? (
              <Button
                variant="outline"
                onClick={() => {
                  void handleSuspend();
                }}
                disabled={suspendMutation.isPending}
              >
                <PowerOff className="w-4 h-4 mr-2" />
                Suspend
              </Button>
            ) : tenant.status === 'suspended' ? (
              <Button
                variant="outline"
                onClick={() => {
                  void handleActivate();
                }}
                disabled={activateMutation.isPending}
              >
                <Power className="w-4 h-4 mr-2" />
                Activate
              </Button>
            ) : null}
            <Button
              variant="danger"
              onClick={() => {
                void handleDelete();
              }}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>
      </div>

      {/* Tenant Information */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card className="p-6">
          <h2 className="text-xl font-semibold mb-4">Basic Information</h2>
          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-muted-foreground">Name</span>
              <p className="text-foreground">{tenant.name}</p>
            </div>
            <div>
              <span className="text-sm font-medium text-muted-foreground">Slug</span>
              <p className="text-foreground">{tenant.slug}</p>
            </div>
            {tenant.subdomain && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Subdomain</span>
                <p className="text-foreground">{tenant.subdomain}</p>
              </div>
            )}
            {tenant.custom_domain && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Custom Domain</span>
                <p className="text-foreground">{tenant.custom_domain}</p>
              </div>
            )}
            <div>
              <span className="text-sm font-medium text-muted-foreground">Status</span>
              <div className="mt-1">
                <TenantStatusBadge status={tenant.status!} />
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-xl font-semibold mb-4">Contact Information</h2>
          <div className="space-y-3">
            {tenant.primary_contact_email && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Primary Contact Email</span>
                <p className="text-foreground">{tenant.primary_contact_email}</p>
              </div>
            )}
            {tenant.primary_contact_name && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Primary Contact Name</span>
                <p className="text-foreground">{tenant.primary_contact_name}</p>
              </div>
            )}
            {tenant.primary_contact_phone && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Primary Contact Phone</span>
                <p className="text-foreground">{tenant.primary_contact_phone}</p>
              </div>
            )}
            {tenant.billing_email && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Billing Email</span>
                <p className="text-foreground">{tenant.billing_email}</p>
              </div>
            )}
            {tenant.technical_email && (
              <div>
                <span className="text-sm font-medium text-muted-foreground">Technical Email</span>
                <p className="text-foreground">{tenant.technical_email}</p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Modules */}
      <Card className="p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Package className="w-5 h-5" />
            Modules ({modules?.length ?? 0})
          </h2>
        </div>
        {modules && modules.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {modules.map((module) => (
              <div
                key={module.id}
                className="p-4 border rounded-lg bg-muted/50"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium">{module.module_name}</span>
                  <span className={`text-xs px-2 py-1 rounded ${module.is_enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' : 'bg-gray-100 text-gray-800 dark:bg-gray-900/20 dark:text-gray-400'}`}>
                    {module.is_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                {module.version && (
                  <p className="text-sm text-muted-foreground">Version: {module.version}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground">No modules installed</p>
        )}
      </Card>

      {/* Resource Usage */}
      {resourceUsage && resourceUsage.length > 0 && (
        <Card className="p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Resource Usage
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Date</th>
                  <th className="text-right p-2">API Calls</th>
                  <th className="text-right p-2">Storage (GB)</th>
                  <th className="text-right p-2">Active Users</th>
                </tr>
              </thead>
              <tbody>
                {resourceUsage.slice(0, 10).map((usage) => (
                  <tr key={usage.id} className="border-b">
                    <td className="p-2">{usage.date}</td>
                    <td className="text-right p-2">{usage.api_calls ?? 0}</td>
                    <td className="text-right p-2">{usage.storage_used_gb ?? 0}</td>
                    <td className="text-right p-2">{usage.active_users ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Health Scores */}
      {healthScores && healthScores.length > 0 && (
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Heart className="w-5 h-5" />
              Health Scores
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Date</th>
                  <th className="text-right p-2">Overall Score</th>
                  <th className="text-right p-2">Usage Score</th>
                  <th className="text-right p-2">Performance Score</th>
                  <th className="text-right p-2">Error Score</th>
                  <th className="text-right p-2">Churn Risk</th>
                </tr>
              </thead>
              <tbody>
                {healthScores.slice(0, 10).map((score) => (
                  <tr key={score.id} className="border-b">
                    <td className="p-2">{score.date}</td>
                    <td className="text-right p-2">{score.overall_score ?? 0}</td>
                    <td className="text-right p-2">{score.usage_score ?? 0}</td>
                    <td className="text-right p-2">{score.performance_score ?? 0}</td>
                    <td className="text-right p-2">{score.error_score ?? 0}</td>
                    <td className="text-right p-2">{score.churn_risk ?? 0}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
