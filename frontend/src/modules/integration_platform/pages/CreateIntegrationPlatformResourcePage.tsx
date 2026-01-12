/**
 * Create IntegrationPlatform Resource Page
 * 
 * Form for creating a new resource with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { integration_platformService } from '../services/integration_platform-service';
import type { IntegrationCreate } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Card } from '@/components/ui/Card';

const resourceSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  integration_type: z.enum(['api', 'webhook', 'database', 'file', 'message_queue']),
  config: z.record(z.unknown()).optional(),
});

type ResourceFormData = z.infer<typeof resourceSchema>;

export const CreateIntegrationPlatformResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<ResourceFormData>({
    resolver: zodResolver(resourceSchema),
    defaultValues: {
      name: '',
      integration_type: 'api',
      config: {},
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: IntegrationCreate) => integration_platformService.createIntegration(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['integration_platform-integrations'] });
      toast.success('Integration created successfully');
      navigate('/integration-platform');
    },
    onError: () => {
      toast.error('Failed to create integration. Please try again.');
    },
  });

  const onSubmit = async (data: ResourceFormData) => {
    try {
      await createMutation.mutateAsync({
        name: data.name,
        integration_type: data.integration_type,
        config: data.config ?? {},
      });
    } catch (err) {
      console.error('Failed to create integration:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create IntegrationPlatform Resource</h1>
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
            <label htmlFor="integration_type" className="block text-sm font-medium text-gray-700 mb-1">
              Integration Type *
            </label>
            <select
              id="integration_type"
              {...form.register('integration_type')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="api">API</option>
              <option value="webhook">Webhook</option>
              <option value="database">Database</option>
              <option value="file">File</option>
              <option value="message_queue">Message Queue</option>
            </select>
          </div>

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Resource'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/integration-platform')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
