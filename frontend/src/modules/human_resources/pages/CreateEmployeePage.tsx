/**
 * Create Employee Page - Human Resources
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
import { hrService } from '../services/hr-service';
import type { EmployeeCreate } from '../contracts';

const MODULE_PATH = '/human-resources/employees';

export const CreateEmployeePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EmployeeCreate>({
    employee_number: '',
    first_name: '',
    last_name: '',
    email: '',
    hire_date: new Date().toISOString().split('T')[0] ?? '',
    employment_type: 'full_time',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: EmployeeCreate) => hrService.createEmployee(data),
    onSuccess: (employee) => {
      void queryClient.invalidateQueries({ queryKey: ['hr-employees'] });
      toast.success('Employee created successfully');
      navigate(`${MODULE_PATH}/${employee.id}`);
    },
    onError: () => {
      toast.error('Failed to create employee. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.employee_number.trim() ||
      !form.first_name.trim() ||
      !form.last_name.trim() ||
      !form.email.trim() ||
      !form.hire_date ||
      !form.employment_type.trim()
    ) {
      toast.error('Employee number, name, email, hire date, and employment type are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Employee</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Employee Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Employee Number</label>
              <Input
                value={form.employee_number}
                onChange={(e) => setForm({ ...form, employee_number: e.target.value })}
                placeholder="e.g. EMP001"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-2 block">First Name</label>
                <Input
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  placeholder="First name"
                  required
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Last Name</label>
                <Input
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  placeholder="Last name"
                  required
                />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Email</label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="email@example.com"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Hire Date</label>
              <Input
                type="date"
                value={form.hire_date}
                onChange={(e) => setForm({ ...form, hire_date: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Employment Type</label>
              <Select
                value={form.employment_type}
                onValueChange={(v) => setForm({ ...form, employment_type: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full_time">Full Time</SelectItem>
                  <SelectItem value="part_time">Part Time</SelectItem>
                  <SelectItem value="contract">Contract</SelectItem>
                  <SelectItem value="temporary">Temporary</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Employee'}
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
