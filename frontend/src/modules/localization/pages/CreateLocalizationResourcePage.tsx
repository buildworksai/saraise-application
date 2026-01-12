/**
 * Create Localization Resource Page
 * 
 * Form for creating a new resource with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { localizationService } from '../services/localization-service';
import type { TranslationCreate } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Card } from '@/components/ui/Card';

const resourceSchema = z.object({
  language: z.string().min(1, 'Language is required'),
  key: z.string().min(1, 'Key is required'),
  value: z.string().min(1, 'Value is required'),
  context: z.string().optional(),
});

type ResourceFormData = z.infer<typeof resourceSchema>;

export const CreateLocalizationResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<ResourceFormData>({
    resolver: zodResolver(resourceSchema),
    defaultValues: {
      language: '',
      key: '',
      value: '',
      context: '',
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: TranslationCreate) => localizationService.createTranslation(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['localization-translations'] });
      toast.success('Translation created successfully');
      navigate('/localization');
    },
    onError: () => {
      toast.error('Failed to create translation. Please try again.');
    },
  });

  const onSubmit = async (data: ResourceFormData) => {
    try {
      await createMutation.mutateAsync({
        language: data.language,
        key: data.key,
        value: data.value,
        context: data.context,
      });
    } catch (err) {
      console.error('Failed to create translation:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create Localization Resource</h1>
      </div>

      <Card className="p-6">
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="language" className="block text-sm font-medium text-gray-700 mb-1">
              Language ID *
            </label>
            <Input
              id="language"
              {...form.register('language')}
              error={form.formState.errors.language?.message}
              placeholder="e.g., en, es, fr"
            />
          </div>

          <div>
            <label htmlFor="key" className="block text-sm font-medium text-gray-700 mb-1">
              Translation Key *
            </label>
            <Input
              id="key"
              {...form.register('key')}
              error={form.formState.errors.key?.message}
              placeholder="e.g., common.save"
            />
          </div>

          <div>
            <label htmlFor="value" className="block text-sm font-medium text-gray-700 mb-1">
              Translation Value *
            </label>
            <Textarea
              id="value"
              {...form.register('value')}
              error={form.formState.errors.value?.message}
              rows={4}
              placeholder="Enter the translated text"
            />
          </div>

          <div>
            <label htmlFor="context" className="block text-sm font-medium text-gray-700 mb-1">
              Context (optional)
            </label>
            <Input
              id="context"
              {...form.register('context')}
              error={form.formState.errors.context?.message}
              placeholder="e.g., button, label"
            />
          </div>

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Resource'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/localization')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
