/**
 * Employee List Page - Human Resources
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { hrService } from '../services/hr-service';
import type { Employee } from '../contracts';

const MODULE_PATH = '/human-resources/employees';

export const EmployeeListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: employees, isLoading, error, refetch } = useQuery({
    queryKey: ['hr-employees'],
    queryFn: () => hrService.listEmployees(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => hrService.deleteEmployee(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['hr-employees'] });
      toast.success('Employee deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete employee. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this employee?')) {
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
          message="Failed to load employees. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!employees || employees.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Employees</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Employee
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No employees yet"
          description="Create your first employee to get started."
          action={{
            label: 'Create Employee',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Employees</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Employee
        </Button>
      </div>

      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Employee #
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Email
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Department
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
            {employees.map((employee) => (
              <tr key={employee.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {employee.employee_number}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {employee.first_name} {employee.last_name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {employee.email}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{employee.department ?? '-'}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {employee.is_active ? 'Active' : 'Inactive'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${employee.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(employee.id)}
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
