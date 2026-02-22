/**
 * Warehouse Detail Page - Inventory Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { inventoryService } from '../services/inventory-service';

const MODULE_PATH = '/inventory-management/warehouses';

export const WarehouseDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: warehouse, isLoading, error } = useQuery({
    queryKey: ['inventory-warehouse', id],
    queryFn: () => (id ? inventoryService.getWarehouse(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (warehouseId: string) => inventoryService.deleteWarehouse(warehouseId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['inventory-warehouses'] });
      toast.success('Warehouse deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete warehouse. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this warehouse?')) {
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

  if (error || !warehouse) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Warehouse not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Warehouses</Button>
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
            {warehouse.warehouse_code} - {warehouse.warehouse_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${warehouse.id}/edit`)}>
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
          <CardTitle>Warehouse Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{warehouse.warehouse_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{warehouse.warehouse_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Type</label>
              <p className="text-sm">{warehouse.warehouse_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{warehouse.is_active ? 'Active' : 'Inactive'}</p>
            </div>
            {warehouse.address && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Address</label>
                <p className="text-sm">{warehouse.address}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(warehouse.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(warehouse.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
