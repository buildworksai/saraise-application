/**
 * Customer List Page - Sales Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { salesService } from '../services/sales-service';
import type { Customer } from '../contracts';

const MODULE_PATH = '/sales-management/customers';

export const CustomerListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: customers, isLoading, error, refetch } = useQuery({
    queryKey: ['sales-customers'],
    queryFn: () => salesService.listCustomers(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => salesService.deleteCustomer(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
      toast.success('Customer deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete customer. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this customer?')) {
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
          message="Failed to load customers. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!customers || customers.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Customers</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Customer
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No customers yet"
          description="Create your first customer to get started."
          action={{
            label: 'Create Customer',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Customers</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Customer
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
                Email
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Currency
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
            {customers.map((customer) => (
              <tr key={customer.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {customer.customer_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{customer.customer_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {customer.email ?? '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{customer.currency}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {customer.is_active ? 'Active' : 'Inactive'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${customer.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(customer.id)}
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
