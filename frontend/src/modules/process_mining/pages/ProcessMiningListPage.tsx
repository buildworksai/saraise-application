/**
 * ProcessMining List Page
 * 
 * Displays all resources with filtering, search, and CRUD operations.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { process_miningService } from '../services/process_mining-service';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const ProcessMiningListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: resources, isLoading, error, refetch } = useQuery({
    queryKey: ['process_mining-resources', deferredSearchTerm],
    queryFn: process_miningService.listResources,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => process_miningService.deleteResource(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['process_mining-resources'] });
      toast.success('Resource deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete resource. Please try again.');
    },
  });

  const filteredResources = (resources as unknown[])?.filter((resource: unknown) => {
    if (!deferredSearchTerm) return true;
    const resourceRecord = resource as Record<string, unknown>;
    const name = String(resourceRecord.name ?? '');
    const description = String(resourceRecord.description ?? '');
    return name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
           description.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this resource?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load resources. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredResources || filteredResources.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">ProcessMining</h1>
          <Button onClick={() => navigate('/process-mining/create')}>
            <Plus className="w-4 h-4 mr-2" />
            Create Resource
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No resources yet"
          description="Get started by creating your first resource."
          action={{label: 'Create Resource', onClick: () => navigate('/process-mining/create')}}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">ProcessMining</h1>
        <Button onClick={() => navigate(`/process-mining/create`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Resource
        </Button>
      </div>

      <Card className="p-6">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <Input
              type="text"
              placeholder="Search resources..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Name</th>
                <th className="text-left p-2">Description</th>
                <th className="text-left p-2">Status</th>
                <th className="text-right p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredResources.map((resource: unknown) => {
                const resourceRecord = resource as Record<string, unknown>;
                return (
                <tr key={String(resourceRecord.id)} className="border-b hover:bg-gray-50">
                  <td className="p-2">
                    <button
                      onClick={() => navigate('/process-mining/' + resourceRecord.id)}
                      className="text-blue-600 hover:underline"
                    >
                      {String(resourceRecord.name)}
                    </button>
                  </td>
                  <td className="p-2 text-gray-600">{String(resourceRecord.description || '')}</td>
                  <td className="p-2">
                    <span className={resourceRecord.is_active ? 'px-2 py-1 rounded text-xs bg-green-100 text-green-800' : 'px-2 py-1 rounded text-xs bg-gray-100 text-gray-800'}>
                      {resourceRecord.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="p-2 text-right">
                    <button
                      onClick={() => navigate('/process-mining/' + resourceRecord.id)}
                      className="text-blue-600 hover:underline mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleDelete(String(resourceRecord.id))}
                      className="text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
