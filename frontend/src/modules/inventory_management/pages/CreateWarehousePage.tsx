/**
 * Create Warehouse Page - Inventory Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { inventoryService } from '../services/inventory-service';
import type { WarehouseCreate } from '../contracts';

const MODULE_PATH = '/inventory-management/warehouses';

export const CreateWarehousePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<WarehouseCreate>({
    warehouse_code: '',
    warehouse_name: '',
    warehouse_type: 'main',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: WarehouseCreate) => inventoryService.createWarehouse(data),
    onSuccess: (warehouse) => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-warehouses'] });
      toast.success('Warehouse created successfully');
      navigate(`${MODULE_PATH}/${warehouse.id}`);
    },
    onError: () => {
      toast.error('Failed to create warehouse. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.warehouse_code.trim() ||
      !form.warehouse_name.trim() ||
      !form.warehouse_type.trim()
    ) {
      toast.error('Code, name, and type are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Warehouse</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Warehouse Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Warehouse Code</label>
              <Input
                value={form.warehouse_code}
                onChange={(e) => setForm({ ...form, warehouse_code: e.target.value })}
                placeholder="e.g. WH001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Warehouse Name</label>
              <Input
                value={form.warehouse_name}
                onChange={(e) => setForm({ ...form, warehouse_name: e.target.value })}
                placeholder="Warehouse name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Warehouse Type</label>
              <Input
                value={form.warehouse_type}
                onChange={(e) => setForm({ ...form, warehouse_type: e.target.value })}
                placeholder="e.g. main, secondary"
                required
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
                {createMutation.isPending ? 'Creating...' : 'Create Warehouse'}
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
