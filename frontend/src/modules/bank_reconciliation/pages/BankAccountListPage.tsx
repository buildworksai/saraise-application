/**
 * Bank Account List Page - Bank Reconciliation
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { bankReconciliationService } from '../services/bank-reconciliation-service';
import type { BankAccount } from '../contracts';

const MODULE_PATH = '/bank-reconciliation/accounts';

export const BankAccountListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: accounts, isLoading, error, refetch } = useQuery({
    queryKey: ['bank-accounts'],
    queryFn: () => bankReconciliationService.listBankAccounts(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => bankReconciliationService.deleteBankAccount(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
      toast.success('Bank account deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete bank account. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this bank account?')) {
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
          message="Failed to load bank accounts. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!accounts || accounts.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Bank Accounts</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Bank Account
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No bank accounts yet"
          description="Create your first bank account to get started."
          action={{
            label: 'Create Bank Account',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Bank Accounts</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Bank Account
        </Button>
      </div>

      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Account Number
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Bank Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Account Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {accounts.map((account) => (
              <tr key={account.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {account.account_number}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{account.bank_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{account.account_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {account.account_type}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {account.is_active ? 'Active' : 'Inactive'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${account.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(account.id)}
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
