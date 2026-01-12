/**
 * Create DocumentIntelligence Resource Page
 * 
 * Form for creating a new resource with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { document_intelligenceService } from '../services/document_intelligence-service';
import type { DocumentIntelligenceResourceCreate } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Card } from '@/components/ui/Card';

const resourceSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  config: z.record(z.unknown()).optional(),
});

type ResourceFormData = z.infer<typeof resourceSchema>;

export const CreateDocumentIntelligenceResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<ResourceFormData>({
    resolver: zodResolver(resourceSchema),
    defaultValues: {
      name: '',
      description: '',
      config: {},
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: DocumentIntelligenceResourceCreate) => document_intelligenceService.createResource(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['document_intelligence-resources'] });
      toast.success('Resource created successfully');
      navigate('/document-intelligence');
    },
    onError: () => {
      toast.error('Failed to create resource. Please try again.');
    },
  });

  const onSubmit = async (data: ResourceFormData) => {
    try {
      await createMutation.mutateAsync({
        name: data.name,
        description: data.description,
        config: data.config ?? {},
      });
    } catch (err) {
      console.error('Failed to create resource:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create DocumentIntelligence Resource</h1>
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

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Resource'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/document-intelligence')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
