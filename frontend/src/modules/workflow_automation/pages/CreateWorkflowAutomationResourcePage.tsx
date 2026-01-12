/**
 * Create WorkflowAutomation Workflow Page
 * 
 * Form for creating a new workflow with validation.
 * 
 * ROOT CAUSE FIX: Updated to use workflowService instead of non-existent workflow_automationService.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { workflowService } from '../services/workflow-service';
import type { Workflow } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Card } from '@/components/ui/Card';

const workflowSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  trigger_type: z.enum(['manual', 'event', 'scheduled']).default('manual'),
});

type WorkflowFormData = z.infer<typeof workflowSchema>;

export const CreateWorkflowAutomationResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<WorkflowFormData>({
    resolver: zodResolver(workflowSchema),
    defaultValues: {
      name: '',
      description: '',
      trigger_type: 'manual',
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: Partial<Workflow>) => workflowService.workflows.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow created successfully');
      navigate('/workflow-automation');
    },
    onError: () => {
      toast.error('Failed to create workflow. Please try again.');
    },
  });

  const onSubmit = async (data: WorkflowFormData) => {
    try {
      await createMutation.mutateAsync({
        name: data.name,
        description: data.description || '',
        trigger_type: data.trigger_type,
        status: 'draft',
      });
    } catch (err) {
      console.error('Failed to create workflow:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create Workflow</h1>
      </div>

      <Card className="p-6">
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
              Name *
            </label>
            <Input
              id="name"
              {...form.register('name')}
              error={form.formState.errors.name?.message}
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <Textarea
              id="description"
              {...form.register('description')}
              rows={4}
            />
          </div>

          <div>
            <label htmlFor="trigger_type" className="block text-sm font-medium text-gray-700 mb-1">
              Trigger Type
            </label>
            <select
              id="trigger_type"
              {...form.register('trigger_type')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="manual">Manual</option>
              <option value="event">Event</option>
              <option value="scheduled">Scheduled</option>
            </select>
          </div>

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Workflow'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/workflow-automation')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
