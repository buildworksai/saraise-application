/**
 * Localization Detail Page
 * 
 * Displays resource details and allows editing.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { localizationService } from '../services/localization-service';
import type { Translation } from '../contracts';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

export const LocalizationDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: resource, isLoading } = useQuery({
    queryKey: ['localization-resource', id],
    queryFn: () => localizationService.getResource(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (resourceId: string) => localizationService.deleteResource(resourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['localization-resources'] });
      toast.success('Resource deleted successfully');
      navigate('/localization');
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

  const resourceData = resource as Translation;

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Translation Key: {String(resourceData.key)}</h1>
          <p className="mt-2 text-gray-600">Language: {String(resourceData.language)}</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => navigate('/localization/' + id + '/edit')}>
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
            <label className="text-sm font-medium text-gray-700">Key</label>
            <p className="mt-1 text-gray-900 font-mono">{String(resourceData.key)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Value</label>
            <p className="mt-1 text-gray-900">{String(resourceData.value)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Language</label>
            <p className="mt-1 text-gray-900">{String(resourceData.language)}</p>
          </div>
          {resourceData.context && (
            <div>
              <label className="text-sm font-medium text-gray-700">Context</label>
              <p className="mt-1 text-gray-900">{String(resourceData.context)}</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
