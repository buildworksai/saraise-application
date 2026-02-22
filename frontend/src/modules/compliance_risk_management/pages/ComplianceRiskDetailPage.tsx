/**
 * Compliance Risk Detail Page - Compliance Risk Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { complianceRiskService } from '../services/compliance-risk-service';

const MODULE_PATH = '/compliance-risk-management/risks';

export const ComplianceRiskDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: risk, isLoading, error } = useQuery({
    queryKey: ['compliance-risk-risk', id],
    queryFn: () => (id ? complianceRiskService.getRisk(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (riskId: string) => complianceRiskService.deleteRisk(riskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['compliance-risk-risks'] });
      toast.success('Risk deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete risk. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this risk?')) {
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

  if (error || !risk) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Risk not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Risks</Button>
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
            {risk.risk_code} - {risk.risk_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${risk.id}/edit`)}>
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
          <CardTitle>Risk Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{risk.risk_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{risk.risk_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Risk Level</label>
              <p className="text-sm">{risk.risk_level}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{risk.status}</p>
            </div>
            {risk.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <p className="text-sm">{risk.description}</p>
              </div>
            )}
            {risk.mitigation_plan && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Mitigation Plan</label>
                <p className="text-sm">{risk.mitigation_plan}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(risk.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(risk.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
