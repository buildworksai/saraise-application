/**
 * Budget List Page - Budget Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { budgetService } from '../services/budget-service';
import type { Budget } from '../contracts';

const MODULE_PATH = '/budget-management/budgets';

export const BudgetListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: budgets, isLoading, error, refetch } = useQuery({
    queryKey: ['budget-budgets'],
    queryFn: () => budgetService.listBudgets(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => budgetService.deleteBudget(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budget-budgets'] });
      toast.success('Budget deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete budget. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this budget?')) {
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
          message="Failed to load budgets. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!budgets || budgets.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Budgets</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Budget
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No budgets yet"
          description="Create your first budget to get started."
          action={{
            label: 'Create Budget',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Budgets</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Budget
        </Button>
      </div>

      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Code
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Fiscal Year
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Total Budget
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {budgets.map((budget) => (
              <tr key={budget.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {budget.budget_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{budget.budget_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{budget.fiscal_year}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {budget.status}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {budget.total_budget} {budget.currency}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${budget.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(budget.id)}
                    className="text-destructive hover:opacity-80"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
