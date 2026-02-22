/**
 * Create Account Page - Chart of Accounts
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
import { accountingService } from '../services/accounting-service';
import type { AccountCreate } from '../contracts';

const MODULE_PATH = '/accounting-finance/accounts';

export const CreateAccountPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AccountCreate>({
    code: '',
    name: '',
    account_type: 'asset',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: AccountCreate) => accountingService.createAccount(data),
    onSuccess: (account) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting-accounts'] });
      toast.success('Account created successfully');
      navigate(`${MODULE_PATH}/${account.id}`);
    },
    onError: () => {
      toast.error('Failed to create account. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.code.trim() || !form.name.trim()) {
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
        <h1 className="text-3xl font-bold text-foreground">Create Account</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Account Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Code</label>
              <Input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                placeholder="e.g. 1000"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Name</label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Account name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Type</label>
              <Select
                value={form.account_type}
                onValueChange={(v) => setForm({ ...form, account_type: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="asset">Asset</SelectItem>
                  <SelectItem value="liability">Liability</SelectItem>
                  <SelectItem value="equity">Equity</SelectItem>
                  <SelectItem value="revenue">Revenue</SelectItem>
                  <SelectItem value="expense">Expense</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Description</label>
              <Input
                value={form.description ?? ''}
                onChange={(e) => setForm({ ...form, description: e.target.value || undefined })}
                placeholder="Optional description"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Account'}
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
