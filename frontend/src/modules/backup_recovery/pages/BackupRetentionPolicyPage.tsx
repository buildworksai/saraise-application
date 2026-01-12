/**
 * Backup Retention Policy Page
 * 
 * Displays and manages backup retention policies.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { Plus, Search, Shield } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const BackupRetentionPolicyPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: policies, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-retention-policies', deferredSearchTerm],
    queryFn: backupRecoveryService.listRetentionPolicies,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => backupRecoveryService.deleteRetentionPolicy(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-retention-policies'] });
      toast.success('Retention policy deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete retention policy. Please try again.');
    },
  });

  const filteredPolicies = policies?.filter((policy) => {
    return deferredSearchTerm === '' || 
      policy.policy_name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      policy.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this retention policy?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load retention policies. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredPolicies || filteredPolicies.length === 0) {
    if (policies?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Retention Policies</h1>
            <Button onClick={() => navigate('/backup-recovery/retention-policies/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Policy
            </Button>
          </div>
          <EmptyState
            icon={Shield}
            title="No retention policies yet"
            description="Create your first retention policy to manage backup lifecycle."
            action={{
              label: "Create Policy",
              onClick: () => navigate('/backup-recovery/retention-policies/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Retention Policies</h1>
        <Button onClick={() => navigate('/backup-recovery/retention-policies/create')}>
          <Plus className="w-4 h-4" />
          Create Policy
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search policies..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Policies Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Policy Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Retention Days
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Archive After Days
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredPolicies?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No policies found matching your search
                </td>
              </tr>
            ) : (
              filteredPolicies?.map((policy) => (
                <tr key={policy.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{policy.policy_name}</div>
                    {policy.description && (
                      <div className="text-sm text-muted-foreground">{policy.description}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {policy.retention_days} days
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {policy.archive_after_days} days
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={policy.is_active ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {new Date(policy.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/backup-recovery/retention-policies/${policy.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(policy.id);
                      }}
                      className="text-destructive hover:opacity-80"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
