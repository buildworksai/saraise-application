/**
 * Create Supplier Page - Purchase Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { purchaseService } from '../services/purchase-service';
import type { SupplierCreate } from '../contracts';

const MODULE_PATH = '/purchase-management/suppliers';

export const CreateSupplierPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SupplierCreate>({
    supplier_code: '',
    supplier_name: '',
    payment_terms: 'Net 30',
    currency: 'USD',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: SupplierCreate) => purchaseService.createSupplier(data),
    onSuccess: (supplier) => {
      void queryClient.invalidateQueries({ queryKey: ['purchase-suppliers'] });
      toast.success('Supplier created successfully');
      navigate(`${MODULE_PATH}/${supplier.id}`);
    },
    onError: () => {
      toast.error('Failed to create supplier. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.supplier_code.trim() ||
      !form.supplier_name.trim() ||
      !form.payment_terms.trim() ||
      !form.currency.trim()
    ) {
      toast.error('Code, name, payment terms, and currency are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Supplier</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Supplier Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Supplier Code</label>
              <Input
                value={form.supplier_code}
                onChange={(e) => setForm({ ...form, supplier_code: e.target.value })}
                placeholder="e.g. SUP001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Supplier Name</label>
              <Input
                value={form.supplier_name}
                onChange={(e) => setForm({ ...form, supplier_name: e.target.value })}
                placeholder="Supplier name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Payment Terms</label>
              <Input
                value={form.payment_terms}
                onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
                placeholder="e.g. Net 30"
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
              <label className="text-sm font-medium mb-2 block">Email</label>
              <Input
                type="email"
                value={form.email ?? ''}
                onChange={(e) => setForm({ ...form, email: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Supplier'}
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
