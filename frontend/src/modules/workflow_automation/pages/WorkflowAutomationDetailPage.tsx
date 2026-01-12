/**
 * WorkflowAutomation Detail Page
 * 
 * Displays workflow details and allows editing.
 * 
 * ROOT CAUSE FIX: Updated to use workflowService instead of non-existent workflow_automationService.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { workflowService } from '../services/workflow-service';
import type { Workflow } from '../contracts';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

export const WorkflowAutomationDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', id],
    queryFn: () => workflowService.workflows.get(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (workflowId: string) => workflowService.workflows.delete(workflowId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow deleted successfully');
      navigate('/workflow-automation');
    },
    onError: () => {
      toast.error('Failed to delete workflow. Please try again.');
    },
  });

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this workflow?')) {
      await deleteMutation.mutateAsync(id!);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="text-gray-600">Loading workflow...</div>
      </div>
    );
  }

  if (!workflow) {
    return (
      <div className="p-8">
        <div className="text-red-600">Workflow not found</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{workflow.name}</h1>
          {workflow.description && (
            <p className="mt-2 text-gray-600">{workflow.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button onClick={() => navigate('/workflow-automation/workflows/' + id)}>
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
            <p className="mt-1 text-gray-900">{workflow.id}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Name</label>
            <p className="mt-1 text-gray-900">{workflow.name}</p>
          </div>
          {workflow.description && (
            <div>
              <label className="text-sm font-medium text-gray-700">Description</label>
              <p className="mt-1 text-gray-900">{workflow.description}</p>
            </div>
          )}
          <div>
            <label className="text-sm font-medium text-gray-700">Status</label>
            <p className="mt-1">
              <span className={`px-2 py-1 rounded text-xs ${
                workflow.status === 'published' 
                  ? 'bg-green-100 text-green-800' 
                  : workflow.status === 'archived'
                  ? 'bg-gray-100 text-gray-800'
                  : 'bg-yellow-100 text-yellow-800'
              }`}>
                {workflow.status.toUpperCase()}
              </span>
            </p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Trigger Type</label>
            <p className="mt-1 text-gray-900">{workflow.trigger_type}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Steps</label>
            <p className="mt-1 text-gray-900">{workflow.steps.length} step(s)</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Created</label>
            <p className="mt-1 text-gray-900">{new Date(workflow.created_at).toLocaleString()}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Last Updated</label>
            <p className="mt-1 text-gray-900">{new Date(workflow.updated_at).toLocaleString()}</p>
          </div>
        </div>
      </Card>
    </div>
  );
};
