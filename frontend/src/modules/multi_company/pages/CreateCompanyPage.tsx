/**
 * Create Company Page - Multi-Company
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { multiCompanyService } from '../services/multi-company-service';
import type { CompanyCreate } from '../contracts';

const MODULE_PATH = '/multi-company/companies';

export const CreateCompanyPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CompanyCreate>({
    company_code: '',
    company_name: '',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: CompanyCreate) => multiCompanyService.createCompany(data),
    onSuccess: (company) => {
      void queryClient.invalidateQueries({ queryKey: ['multi-company-companies'] });
      toast.success('Company created successfully');
      navigate(`${MODULE_PATH}/${company.id}`);
    },
    onError: () => {
      toast.error('Failed to create company. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.company_code.trim() || !form.company_name.trim()) {
      toast.error('Code and name are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Company</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Company Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Company Code</label>
              <Input
                value={form.company_code}
                onChange={(e) => setForm({ ...form, company_code: e.target.value })}
                placeholder="e.g. CO001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Company Name</label>
              <Input
                value={form.company_name}
                onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                placeholder="Company name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Legal Name</label>
              <Input
                value={form.legal_name ?? ''}
                onChange={(e) => setForm({ ...form, legal_name: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Tax ID</label>
              <Input
                value={form.tax_id ?? ''}
                onChange={(e) => setForm({ ...form, tax_id: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Address</label>
              <Input
                value={form.address ?? ''}
                onChange={(e) => setForm({ ...form, address: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Company'}
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
