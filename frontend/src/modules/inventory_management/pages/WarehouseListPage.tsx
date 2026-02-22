/**
 * Warehouse List Page - Inventory Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { inventoryService } from '../services/inventory-service';
import type { Warehouse } from '../contracts';

const MODULE_PATH = '/inventory-management/warehouses';

export const WarehouseListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: warehouses, isLoading, error, refetch } = useQuery({
    queryKey: ['inventory-warehouses'],
    queryFn: () => inventoryService.listWarehouses(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => inventoryService.deleteWarehouse(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-warehouses'] });
      toast.success('Warehouse deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete warehouse. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this warehouse?')) {
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
          message="Failed to load warehouses. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!warehouses || warehouses.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Warehouses</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Warehouse
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No warehouses yet"
          description="Create your first warehouse to get started."
          action={{
            label: 'Create Warehouse',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Warehouses</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Warehouse
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
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Address
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
            {warehouses.map((warehouse) => (
              <tr key={warehouse.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {warehouse.warehouse_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{warehouse.warehouse_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {warehouse.warehouse_type}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{warehouse.address ?? '-'}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {warehouse.is_active ? 'Active' : 'Inactive'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${warehouse.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(warehouse.id)}
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
