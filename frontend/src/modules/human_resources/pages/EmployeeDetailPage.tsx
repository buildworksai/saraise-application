/**
 * Employee Detail Page - Human Resources
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { hrService } from '../services/hr-service';

const MODULE_PATH = '/human-resources/employees';

export const EmployeeDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: employee, isLoading, error } = useQuery({
    queryKey: ['hr-employee', id],
    queryFn: () => (id ? hrService.getEmployee(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (employeeId: string) => hrService.deleteEmployee(employeeId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['hr-employees'] });
      toast.success('Employee deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete employee. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this employee?')) {
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

  if (error || !employee) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Employee not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Employees</Button>
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
            {employee.employee_number} - {employee.first_name} {employee.last_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${employee.id}/edit`)}>
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
          <CardTitle>Employee Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Employee Number</label>
              <p className="text-sm font-medium">{employee.employee_number}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">
                {employee.first_name} {employee.last_name}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Email</label>
              <p className="text-sm">{employee.email}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Phone</label>
              <p className="text-sm">{employee.phone ?? '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Department</label>
              <p className="text-sm">{employee.department ?? '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Position</label>
              <p className="text-sm">{employee.position ?? '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Hire Date</label>
              <p className="text-sm">{new Date(employee.hire_date).toLocaleDateString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Employment Type</label>
              <p className="text-sm">{employee.employment_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{employee.is_active ? 'Active' : 'Inactive'}</p>
            </div>
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(employee.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(employee.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
