/**
 * Create Customer Page - Sales Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { salesService } from '../services/sales-service';
import type { CustomerCreate } from '../contracts';

const MODULE_PATH = '/sales-management/customers';

export const CreateCustomerPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CustomerCreate>({
    customer_code: '',
    customer_name: '',
    currency: 'USD',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: CustomerCreate) => salesService.createCustomer(data),
    onSuccess: (customer) => {
      void queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
      toast.success('Customer created successfully');
      navigate(`${MODULE_PATH}/${customer.id}`);
    },
    onError: () => {
      toast.error('Failed to create customer. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.customer_code.trim() || !form.customer_name.trim() || !form.currency.trim()) {
      toast.error('Code, name, and currency are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Customer</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Customer Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Customer Code</label>
              <Input
                value={form.customer_code}
                onChange={(e) => setForm({ ...form, customer_code: e.target.value })}
                placeholder="e.g. CUST001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Customer Name</label>
              <Input
                value={form.customer_name}
                onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
                placeholder="Customer name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Email</label>
              <Input
                type="email"
                value={form.email ?? ''}
                onChange={(e) => setForm({ ...form, email: e.target.value || undefined })}
                placeholder="email@example.com"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Phone</label>
              <Input
                value={form.phone ?? ''}
                onChange={(e) => setForm({ ...form, phone: e.target.value || undefined })}
                placeholder="Optional"
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
                {createMutation.isPending ? 'Creating...' : 'Create Customer'}
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
