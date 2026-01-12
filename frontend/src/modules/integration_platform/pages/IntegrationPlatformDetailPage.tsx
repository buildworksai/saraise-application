/**
 * IntegrationPlatform Detail Page
 * 
 * Displays resource details and allows editing.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { integration_platformService } from '../services/integration_platform-service';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

export const IntegrationPlatformDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: resource, isLoading } = useQuery({
    queryKey: ['integration_platform-resource', id],
    queryFn: () => integration_platformService.getResource(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (resourceId: string) => integration_platformService.deleteResource(resourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['integration_platform-resources'] });
      toast.success('Resource deleted successfully');
      navigate('/integration-platform');
    },
    onError: () => {
      toast.error('Failed to delete resource. Please try again.');
    },
  });

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this resource?')) {
      await deleteMutation.mutateAsync(id!);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="text-gray-600">Loading resource...</div>
      </div>
    );
  }

  if (!resource) {
    return (
      <div className="p-8">
        <div className="text-red-600">Resource not found</div>
      </div>
    );
  }

  const resourceData = resource as { name: string; description?: string; id: string; status: string; integration_type: string; config?: Record<string, unknown> };

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{String(resourceData.name)}</h1>
          {resourceData.description && (
            <p className="mt-2 text-gray-600">{String(resourceData.description)}</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button onClick={() => navigate('/integration-platform/' + id + '/edit')}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <Card className="p-6">
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700">ID</label>
            <p className="mt-1 text-gray-900">{String(resourceData.id)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Name</label>
            <p className="mt-1 text-gray-900">{String(resourceData.name)}</p>
          </div>
          {resourceData.description && (
            <div>
              <label className="text-sm font-medium text-gray-700">Description</label>
              <p className="mt-1 text-gray-900">{String(resourceData.description)}</p>
            </div>
          )}
          <div>
            <label className="text-sm font-medium text-gray-700">Status</label>
            <p className="mt-1">
              <span className={resourceData.status === 'active' ? 'px-2 py-1 rounded text-xs bg-green-100 text-green-800' : resourceData.status === 'error' ? 'px-2 py-1 rounded text-xs bg-red-100 text-red-800' : 'px-2 py-1 rounded text-xs bg-gray-100 text-gray-800'}>
                {resourceData.status}
              </span>
            </p>
          </div>
          {resourceData.config && (
            <div>
              <label className="text-sm font-medium text-gray-700">Configuration</label>
              <pre className="mt-1 p-2 bg-gray-100 rounded text-sm overflow-auto">
                {JSON.stringify(resourceData.config, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
