/**
 * Create Compliance Risk Page - Compliance Risk Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { complianceRiskService } from '../services/compliance-risk-service';
import type { ComplianceRiskCreate } from '../contracts';

const MODULE_PATH = '/compliance-risk-management/risks';

export const CreateComplianceRiskPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ComplianceRiskCreate>({
    risk_code: '',
    risk_name: '',
    risk_level: 'medium',
    status: 'open',
  });

  const createMutation = useMutation({
    mutationFn: (data: ComplianceRiskCreate) => complianceRiskService.createRisk(data),
    onSuccess: (risk) => {
      void queryClient.invalidateQueries({ queryKey: ['compliance-risk-risks'] });
      toast.success('Risk created successfully');
      navigate(`${MODULE_PATH}/${risk.id}`);
    },
    onError: () => {
      toast.error('Failed to create risk. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.risk_code.trim() ||
      !form.risk_name.trim() ||
      !form.risk_level.trim() ||
      !form.status.trim()
    ) {
      toast.error('Code, name, risk level, and status are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Compliance Risk</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Risk Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Risk Code</label>
              <Input
                value={form.risk_code}
                onChange={(e) => setForm({ ...form, risk_code: e.target.value })}
                placeholder="e.g. RISK001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Risk Name</label>
              <Input
                value={form.risk_name}
                onChange={(e) => setForm({ ...form, risk_name: e.target.value })}
                placeholder="Risk name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Risk Level</label>
              <Select
                value={form.risk_level}
                onValueChange={(v) => setForm({ ...form, risk_level: v as ComplianceRiskCreate['risk_level'] })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <Input
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                placeholder="e.g. open, mitigated"
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
                {createMutation.isPending ? 'Creating...' : 'Create Risk'}
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
