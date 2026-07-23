import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import {
  REGIONAL_QUERY_KEYS,
  ROUTES,
  type RegionalResourceUpdate,
} from '../contracts';
import { regionalService } from '../services/regional-service';
import { useRegionalDocumentTitle } from '../use-regional-document-title';

type ResourceFormData = {
  name: string;
  description: string;
};

export const EditRegionalResourcePage = () => {
  useRegionalDocumentTitle('Edit regional resource');
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const resource = useQuery({
    queryKey: REGIONAL_QUERY_KEYS.resource(id),
    queryFn: () => regionalService.getResource(id),
    enabled: Boolean(id),
  });
  const configuration = useQuery({
    queryKey: [...REGIONAL_QUERY_KEYS.configuration('active'), 'active'],
    queryFn: regionalService.getActiveConfiguration,
  });
  const form = useForm<ResourceFormData>({ defaultValues: { name: '', description: '' } });

  useEffect(() => {
    if (resource.data) {
      form.reset({
        name: resource.data.name,
        description: resource.data.description,
      });
    }
  }, [form, resource.data]);

  const updateMutation = useMutation({
    mutationFn: (data: RegionalResourceUpdate) =>
      regionalService.updateResource(id, data),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resources });
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resource(id) });
      toast.success('Resource updated successfully');
      navigate(ROUTES.DETAIL(updated.id));
    },
    onError: () => toast.error('Failed to update resource. Please try again.'),
  });

  if (resource.isLoading || configuration.isLoading) {
    return <p role="status" className="p-8 text-muted-foreground">Loading resource…</p>;
  }
  const rules = configuration.data?.document.resource;
  if (resource.isError || configuration.isError || !resource.data || !rules) {
    return (
      <ErrorState
        message="The resource or its governed configuration could not be loaded."
        onRetry={() => {
          void resource.refetch();
          void configuration.refetch();
        }}
      />
    );
  }

  return (
    <main id="main-content" className="mx-auto max-w-4xl space-y-6 p-8">
      <h1 className="text-3xl font-bold text-foreground">Edit regional resource</h1>
      <Card>
        <CardHeader><CardTitle>Resource details</CardTitle></CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((data) =>
              updateMutation.mutate({
                name: data.name.trim(),
                description: data.description,
              }),
            )}
          >
            <Input
              id="name"
              label="Name"
              required
              minLength={rules.name_min_length}
              maxLength={rules.name_max_length}
              error={form.formState.errors.name?.message}
              {...form.register('name', {
                required: 'Name is required',
                minLength: {
                  value: rules.name_min_length,
                  message: `Name must contain at least ${rules.name_min_length} characters`,
                },
                maxLength: {
                  value: rules.name_max_length,
                  message: `Name must contain at most ${rules.name_max_length} characters`,
                },
                validate: (value) =>
                  value.trim().length >= rules.name_min_length ||
                  `Name must contain at least ${rules.name_min_length} non-whitespace characters`,
              })}
            />
            <div>
              <label htmlFor="description" className="mb-1 block text-sm font-medium text-foreground">
                Description
              </label>
              <Textarea
                id="description"
                rows={4}
                maxLength={rules.description_max_length}
                {...form.register('description', {
                  maxLength: {
                    value: rules.description_max_length,
                    message: `Description must contain at most ${rules.description_max_length} characters`,
                  },
                })}
              />
              {form.formState.errors.description ? (
                <p className="mt-1 text-sm text-destructive">
                  {form.formState.errors.description.message}
                </p>
              ) : null}
            </div>
            {updateMutation.error ? (
              <p role="alert" className="text-sm text-destructive">
                {updateMutation.error instanceof Error
                  ? updateMutation.error.message
                  : 'Resource update failed.'}
              </p>
            ) : null}
            <div className="flex gap-3">
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending ? 'Saving…' : 'Save changes'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate(ROUTES.DETAIL(resource.data.id))}
              >
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
};
