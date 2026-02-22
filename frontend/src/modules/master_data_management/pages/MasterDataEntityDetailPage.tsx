/**
 * Master Data Entity Detail Page - Master Data Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { masterDataService } from '../services/master-data-service';

const MODULE_PATH = '/master-data/entities';

export const MasterDataEntityDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: entity, isLoading, error } = useQuery({
    queryKey: ['master-data-entity', id],
    queryFn: () => (id ? masterDataService.getEntity(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (entityId: string) => masterDataService.deleteEntity(entityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['master-data-entities'] });
      toast.success('Entity deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete entity. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this entity?')) {
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

  if (error || !entity) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Entity not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Entities</Button>
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
            {entity.entity_code} - {entity.entity_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${entity.id}/edit`)}>
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
          <CardTitle>Entity Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Entity Type</label>
              <p className="text-sm font-medium">{entity.entity_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{entity.entity_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{entity.entity_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{entity.is_active ? 'Active' : 'Inactive'}</p>
            </div>
            {Object.keys(entity.data ?? {}).length > 0 && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Data</label>
                <pre className="text-sm bg-muted p-2 rounded overflow-auto max-h-32">
                  {JSON.stringify(entity.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(entity.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(entity.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
