/**
 * Field Security Page
 * 
 * Displays and manages field-level security rules.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, FieldSecurity } from '../contracts';
import { Plus, Search, Lock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const FieldSecurityPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: fieldSecurityRules, isLoading, error, refetch } = useQuery({
    queryKey: ['field-security', deferredSearchTerm],
    queryFn: () => apiClient.get<FieldSecurity[]>(ENDPOINTS.FIELD_SECURITY.LIST),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(ENDPOINTS.FIELD_SECURITY.DELETE(id)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['field-security'] });
      toast.success('Field security rule deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete field security rule. Please try again.');
    },
  });

  const filteredRules = fieldSecurityRules?.filter((rule) => {
    return deferredSearchTerm === '' || 
      rule.model_name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      rule.field_name.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this field security rule?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={5} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load field security rules. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredRules || filteredRules.length === 0) {
    if (fieldSecurityRules?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Field Security</h1>
            <Button onClick={() => navigate('/security-access-control/field-security/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Rule
            </Button>
          </div>
          <EmptyState
            icon={Lock}
            title="No field security rules yet"
            description="Create your first field security rule to control field-level access."
            action={{
              label: "Create Rule",
              onClick: () => navigate('/security-access-control/field-security/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Field Security</h1>
        <Button onClick={() => navigate('/security-access-control/field-security/create')}>
          <Plus className="w-4 h-4" />
          Create Rule
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search field security rules..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Rules Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Model
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Field
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Visibility
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Edit Control
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredRules?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No rules found matching your search
                </td>
              </tr>
            ) : (
              filteredRules?.map((rule) => (
                <tr key={rule.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{rule.model_name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{rule.field_name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={rule.visibility === 'visible' ? 'active' : 'inactive'} />
                    <div className="text-sm text-muted-foreground capitalize">{rule.visibility}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize">
                    {rule.edit_control}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/security-access-control/field-security/${rule.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(rule.id);
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
