/**
 * Create Budget Page - Budget Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { budgetService } from '../services/budget-service';
import type { BudgetCreate } from '../contracts';

const MODULE_PATH = '/budget-management/budgets';

export const CreateBudgetPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentYear = new Date().getFullYear();
  const [form, setForm] = useState<BudgetCreate>({
    budget_code: '',
    budget_name: '',
    fiscal_year: currentYear,
    start_date: `${currentYear}-01-01`,
    end_date: `${currentYear}-12-31`,
    status: 'draft',
    currency: 'USD',
    total_budget: '0',
  });

  const createMutation = useMutation({
    mutationFn: (data: BudgetCreate) => budgetService.createBudget(data),
    onSuccess: (budget) => {
      void queryClient.invalidateQueries({ queryKey: ['budget-budgets'] });
      toast.success('Budget created successfully');
      navigate(`${MODULE_PATH}/${budget.id}`);
    },
    onError: () => {
      toast.error('Failed to create budget. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.budget_code.trim() ||
      !form.budget_name.trim() ||
      !form.status.trim() ||
      !form.currency.trim() ||
      !form.total_budget.trim()
    ) {
      toast.error('Code, name, status, currency, and total budget are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Budget</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Budget Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Budget Code</label>
              <Input
                value={form.budget_code}
                onChange={(e) => setForm({ ...form, budget_code: e.target.value })}
                placeholder="e.g. BUD2024"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Budget Name</label>
              <Input
                value={form.budget_name}
                onChange={(e) => setForm({ ...form, budget_name: e.target.value })}
                placeholder="Budget name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Fiscal Year</label>
              <Input
                type="number"
                value={form.fiscal_year}
                onChange={(e) => setForm({ ...form, fiscal_year: parseInt(e.target.value, 10) })}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-2 block">Start Date</label>
                <Input
                  type="date"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">End Date</label>
                <Input
                  type="date"
                  value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                  required
                />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <Input
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                placeholder="e.g. draft, approved"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Currency</label>
              <Input
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
                placeholder="e.g. USD"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Total Budget</label>
              <Input
                value={form.total_budget}
                onChange={(e) => setForm({ ...form, total_budget: e.target.value })}
                placeholder="0"
                required
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Budget'}
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
