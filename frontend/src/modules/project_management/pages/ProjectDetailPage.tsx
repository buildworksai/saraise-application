/**
 * Project Detail Page - Project Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { projectService } from '../services/project-service';

const MODULE_PATH = '/project-management/projects';

export const ProjectDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: project, isLoading, error } = useQuery({
    queryKey: ['project-project', id],
    queryFn: () => (id ? projectService.getProject(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => projectService.deleteProject(projectId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project-projects'] });
      toast.success('Project deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete project. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this project?')) {
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

  if (error || !project) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Project not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Projects</Button>
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
            {project.project_code} - {project.project_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${project.id}/edit`)}>
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
          <CardTitle>Project Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{project.project_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{project.project_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{project.status}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Currency</label>
              <p className="text-sm">{project.currency}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Start Date</label>
              <p className="text-sm">
                {project.start_date ? new Date(project.start_date).toLocaleDateString() : '-'}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">End Date</label>
              <p className="text-sm">
                {project.end_date ? new Date(project.end_date).toLocaleDateString() : '-'}
              </p>
            </div>
            {project.budget && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Budget</label>
                <p className="text-sm">{project.budget} {project.currency}</p>
              </div>
            )}
            {project.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <p className="text-sm">{project.description}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(project.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(project.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
