/**
 * Create Project Page - Project Management
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
import { projectService } from '../services/project-service';
import type { ProjectCreate } from '../contracts';

const MODULE_PATH = '/project-management/projects';

export const CreateProjectPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProjectCreate>({
    project_code: '',
    project_name: '',
    status: 'planning',
    currency: 'USD',
  });

  const createMutation = useMutation({
    mutationFn: (data: ProjectCreate) => projectService.createProject(data),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['project-projects'] });
      toast.success('Project created successfully');
      navigate(`${MODULE_PATH}/${project.id}`);
    },
    onError: () => {
      toast.error('Failed to create project. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.project_code.trim() || !form.project_name.trim() || !form.currency.trim()) {
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
        <h1 className="text-3xl font-bold text-foreground">Create Project</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Project Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Project Code</label>
              <Input
                value={form.project_code}
                onChange={(e) => setForm({ ...form, project_code: e.target.value })}
                placeholder="e.g. PRJ001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Project Name</label>
              <Input
                value={form.project_name}
                onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                placeholder="Project name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <Select value={form.status ?? 'planning'} onValueChange={(v) => setForm({ ...form, status: v as ProjectCreate['status'] })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="planning">Planning</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="on_hold">On Hold</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
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
              <label className="text-sm font-medium mb-2 block">Description</label>
              <Input
                value={form.description ?? ''}
                onChange={(e) => setForm({ ...form, description: e.target.value || undefined })}
                placeholder="Optional"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Project'}
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
