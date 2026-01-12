/**
 * WorkflowAutomation List Page
 * 
 * Displays all workflows with filtering, search, and CRUD operations.
 * 
 * ROOT CAUSE FIX: Updated to use workflowService instead of non-existent workflow_automationService.
 * The backend API exposes /workflows/, /instances/, and /tasks/ endpoints, not a generic /resources/ endpoint.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { workflowService } from '../services/workflow-service';
import type { Workflow } from '../contracts';
import { Plus, Search, Inbox } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const WorkflowAutomationListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: workflows, isLoading, error, refetch } = useQuery({
    queryKey: ['workflows', deferredSearchTerm],
    queryFn: workflowService.workflows.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => workflowService.workflows.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete workflow. Please try again.');
    },
  });

  const filteredWorkflows = (workflows as Workflow[])?.filter((workflow: Workflow) => {
    if (!deferredSearchTerm) return true;
    const name = String(workflow.name || '');
    const description = String(workflow.description || '');
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

  if (!filteredWorkflows || filteredWorkflows.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Workflows</h1>
          <Button onClick={() => navigate('/workflow-automation/workflows/new')}>
            <Plus className="w-4 h-4 mr-2" />
            Create Workflow
          </Button>
        </div>
        <EmptyState
          icon={Inbox}
          title="No workflows yet"
          description="Get started by creating your first workflow."
          action={{label: 'Create Workflow', onClick: () => navigate('/workflow-automation/workflows/new')}}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Workflows</h1>
        <Button onClick={() => navigate('/workflow-automation/workflows/new')}>
          <Plus className="w-4 h-4 mr-2" />
          Create Workflow
        </Button>
      </div>

      <Card className="p-6">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <Input
              type="text"
              placeholder="Search workflows..."
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
                <th className="text-left p-2">Trigger Type</th>
                <th className="text-right p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredWorkflows.map((workflow: Workflow) => (
                <tr key={workflow.id} className="border-b hover:bg-gray-50">
                  <td className="p-2">
                    <button
                      onClick={() => navigate('/workflow-automation/workflows/' + workflow.id)}
                      className="text-blue-600 hover:underline"
                    >
                      {workflow.name}
                    </button>
                  </td>
                  <td className="p-2 text-gray-600">{workflow.description || ''}</td>
                  <td className="p-2">
                    <span className={`px-2 py-1 rounded text-xs ${
                      workflow.status === 'published' 
                        ? 'bg-green-100 text-green-800' 
                        : workflow.status === 'archived'
                        ? 'bg-gray-100 text-gray-800'
                        : 'bg-yellow-100 text-yellow-800'
                    }`}>
                      {workflow.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="p-2 text-gray-600">{workflow.trigger_type}</td>
                  <td className="p-2 text-right">
                    <button
                      onClick={() => navigate('/workflow-automation/workflows/' + workflow.id)}
                      className="text-blue-600 hover:underline mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleDelete(workflow.id)}
                      className="text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
