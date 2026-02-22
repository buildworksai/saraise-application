/**
 * Project List Page - Project Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { projectService } from '../services/project-service';
import type { Project } from '../contracts';

const MODULE_PATH = '/project-management/projects';

export const ProjectListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: projects, isLoading, error, refetch } = useQuery({
    queryKey: ['project-projects'],
    queryFn: () => projectService.listProjects(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectService.deleteProject(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project-projects'] });
      toast.success('Project deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete project. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this project?')) {
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
          message="Failed to load projects. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!projects || projects.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Projects</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Project
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No projects yet"
          description="Create your first project to get started."
          action={{
            label: 'Create Project',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Projects</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Project
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
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Start Date
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Budget
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {projects.map((project) => (
              <tr key={project.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {project.project_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{project.project_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {project.status}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {project.start_date
                    ? new Date(project.start_date).toLocaleDateString()
                    : '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {project.budget ? `${project.budget} ${project.currency}` : '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${project.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(project.id)}
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
