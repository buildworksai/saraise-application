/**
 * Create Dms Resource Page
 * 
 * Form for creating a new resource with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { dmsService } from '../services/dms-service';
import type { DocumentCreate } from '../contracts';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';

const resourceSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  file_path: z.string().min(1, 'File path is required'),
  mime_type: z.string().min(1, 'MIME type is required'),
  size: z.number().min(0),
  checksum: z.string().min(1, 'Checksum is required'),
  folder: z.string().optional(),
});

type ResourceFormData = z.infer<typeof resourceSchema>;

export const CreateDmsResourcePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<ResourceFormData>({
    resolver: zodResolver(resourceSchema),
    defaultValues: {
      name: '',
      file_path: '',
      mime_type: '',
      size: 0,
      checksum: '',
      folder: '',
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: DocumentCreate) => dmsService.createDocument(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['dms-documents'] });
      toast.success('Document created successfully');
      navigate('/dms');
    },
    onError: () => {
      toast.error('Failed to create document. Please try again.');
    },
  });

  const onSubmit = async (data: ResourceFormData) => {
    try {
      await createMutation.mutateAsync({
        name: data.name,
        file_path: data.file_path,
        mime_type: data.mime_type,
        size: data.size,
        checksum: data.checksum,
        folder: data.folder,
      });
    } catch (err) {
      console.error('Failed to create document:', err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Create Dms Resource</h1>
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
            <label htmlFor="file_path" className="block text-sm font-medium text-gray-700 mb-1">
              File Path *
            </label>
            <Input
              id="file_path"
              {...form.register('file_path')}
              error={form.formState.errors.file_path?.message}
            />
          </div>

          <div>
            <label htmlFor="mime_type" className="block text-sm font-medium text-gray-700 mb-1">
              MIME Type *
            </label>
            <Input
              id="mime_type"
              {...form.register('mime_type')}
              error={form.formState.errors.mime_type?.message}
              placeholder="e.g., application/pdf"
            />
          </div>

          <div>
            <label htmlFor="size" className="block text-sm font-medium text-gray-700 mb-1">
              Size (bytes) *
            </label>
            <Input
              id="size"
              type="number"
              {...form.register('size', { valueAsNumber: true })}
              error={form.formState.errors.size?.message}
            />
          </div>

          <div>
            <label htmlFor="checksum" className="block text-sm font-medium text-gray-700 mb-1">
              Checksum *
            </label>
            <Input
              id="checksum"
              {...form.register('checksum')}
              error={form.formState.errors.checksum?.message}
            />
          </div>

          <div>
            <label htmlFor="folder" className="block text-sm font-medium text-gray-700 mb-1">
              Folder ID (optional)
            </label>
            <Input
              id="folder"
              {...form.register('folder')}
              error={form.formState.errors.folder?.message}
            />
          </div>

          <div className="flex gap-4 pt-4">
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Resource'}
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate('/dms')}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
