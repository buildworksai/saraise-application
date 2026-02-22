/**
 * Create Bank Account Page - Bank Reconciliation
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { bankReconciliationService } from '../services/bank-reconciliation-service';
import type { BankAccountCreate } from '../contracts';

const MODULE_PATH = '/bank-reconciliation/accounts';

export const CreateBankAccountPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<BankAccountCreate>({
    account_number: '',
    bank_name: '',
    account_name: '',
    account_type: 'checking',
    currency: 'USD',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: BankAccountCreate) =>
      bankReconciliationService.createBankAccount(data),
    onSuccess: (account) => {
      void queryClient.invalidateQueries({ queryKey: ['bank-accounts'] });
      toast.success('Bank account created successfully');
      navigate(`${MODULE_PATH}/${account.id}`);
    },
    onError: () => {
      toast.error('Failed to create bank account. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.account_number.trim() ||
      !form.bank_name.trim() ||
      !form.account_name.trim() ||
      !form.account_type.trim() ||
      !form.currency.trim()
    ) {
      toast.error('Account number, bank name, account name, type, and currency are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Bank Account</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Bank Account Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Account Number</label>
              <Input
                value={form.account_number}
                onChange={(e) => setForm({ ...form, account_number: e.target.value })}
                placeholder="e.g. 1234567890"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Bank Name</label>
              <Input
                value={form.bank_name}
                onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
                placeholder="Bank name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Account Name</label>
              <Input
                value={form.account_name}
                onChange={(e) => setForm({ ...form, account_name: e.target.value })}
                placeholder="Account display name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Account Type</label>
              <Input
                value={form.account_type}
                onChange={(e) => setForm({ ...form, account_type: e.target.value })}
                placeholder="e.g. checking, savings"
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
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Bank Account'}
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
