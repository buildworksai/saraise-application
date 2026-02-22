/**
 * Create Compliance Policy Page - Compliance Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { complianceService } from '../services/compliance-service';
import type { CompliancePolicyCreate } from '../contracts';

const MODULE_PATH = '/compliance-management/policies';

export const CreateCompliancePolicyPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CompliancePolicyCreate>({
    policy_code: '',
    policy_name: '',
    regulation_type: '',
    effective_date: new Date().toISOString().split('T')[0] ?? '',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: CompliancePolicyCreate) => complianceService.createPolicy(data),
    onSuccess: (policy) => {
      void queryClient.invalidateQueries({ queryKey: ['compliance-policies'] });
      toast.success('Policy created successfully');
      navigate(`${MODULE_PATH}/${policy.id}`);
    },
    onError: () => {
      toast.error('Failed to create policy. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.policy_code.trim() ||
      !form.policy_name.trim() ||
      !form.regulation_type.trim() ||
      !form.effective_date
    ) {
      toast.error('Code, name, regulation type, and effective date are required');
      return;
    }
    createMutation.mutate(form);
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Create Compliance Policy</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Policy Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Policy Code</label>
              <Input
                value={form.policy_code}
                onChange={(e) => setForm({ ...form, policy_code: e.target.value })}
                placeholder="e.g. POL001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Policy Name</label>
              <Input
                value={form.policy_name}
                onChange={(e) => setForm({ ...form, policy_name: e.target.value })}
                placeholder="Policy name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Regulation Type</label>
              <Input
                value={form.regulation_type}
                onChange={(e) => setForm({ ...form, regulation_type: e.target.value })}
                placeholder="e.g. GDPR, SOX"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Effective Date</label>
              <Input
                type="date"
                value={form.effective_date}
                onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Description</label>
              <Input
                value={form.description ?? ''}
                onChange={(e) => setForm({ ...form, description: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Policy'}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(MODULE_PATH)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
