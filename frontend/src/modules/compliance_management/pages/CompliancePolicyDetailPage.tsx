/**
 * Compliance Policy Detail Page - Compliance Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { complianceService } from '../services/compliance-service';

const MODULE_PATH = '/compliance-management/policies';

export const CompliancePolicyDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: policy, isLoading, error } = useQuery({
    queryKey: ['compliance-policy', id],
    queryFn: () => (id ? complianceService.getPolicy(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (policyId: string) => complianceService.deletePolicy(policyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['compliance-policies'] });
      toast.success('Policy deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete policy. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this policy?')) {
      void deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4" />
          <div className="h-64 bg-muted rounded" />
        </div>
      </div>
    );
  }

  if (error || !policy) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Policy not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Policies</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold text-foreground">
            {policy.policy_code} - {policy.policy_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${policy.id}/edit`)}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Policy Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{policy.policy_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{policy.policy_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Regulation Type</label>
              <p className="text-sm">{policy.regulation_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Effective Date</label>
              <p className="text-sm">{new Date(policy.effective_date).toLocaleDateString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{policy.is_active ? 'Active' : 'Inactive'}</p>
            </div>
            {policy.expiry_date && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Expiry Date</label>
                <p className="text-sm">{new Date(policy.expiry_date).toLocaleDateString()}</p>
              </div>
            )}
            {policy.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <p className="text-sm">{policy.description}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(policy.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(policy.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
