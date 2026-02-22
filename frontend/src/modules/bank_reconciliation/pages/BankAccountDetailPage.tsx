/**
 * Bank Account Detail Page - Bank Reconciliation
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { bankReconciliationService } from '../services/bank-reconciliation-service';

const MODULE_PATH = '/bank-reconciliation/accounts';

export const BankAccountDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: account, isLoading, error } = useQuery({
    queryKey: ['bank-account', id],
    queryFn: () =>
      id ? bankReconciliationService.getBankAccount(id) : Promise.reject(new Error('No ID')),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (accountId: string) => bankReconciliationService.deleteBankAccount(accountId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
      toast.success('Bank account deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete bank account. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this bank account?')) {
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

  if (error || !account) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Bank account not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Bank Accounts</Button>
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
            {account.account_name} - {account.account_number}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${account.id}/edit`)}>
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
          <CardTitle>Bank Account Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Account Number</label>
              <p className="text-sm font-medium">{account.account_number}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Bank Name</label>
              <p className="text-sm font-medium">{account.bank_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Account Name</label>
              <p className="text-sm">{account.account_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Account Type</label>
              <p className="text-sm">{account.account_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Currency</label>
              <p className="text-sm">{account.currency}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{account.is_active ? 'Active' : 'Inactive'}</p>
            </div>
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(account.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(account.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
