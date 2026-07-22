import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ErrorState } from '@/components/ui';
import { QUERY_KEYS, ROUTES, type ApiManagementResourceCreate, type JsonObject } from '../contracts';
import { api_managementService } from '../services/api_management-service';

export function CreateApiManagementResourcePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const configuration = useQuery({ queryKey: QUERY_KEYS.CONFIGURATION, queryFn: api_managementService.getConfiguration });
  const policy = configuration.data?.document;
  const [name, setName] = useState('');
  const [description, setDescription] = useState<string | null>(null);
  const [resourceConfig, setResourceConfig] = useState<JsonObject | null>(null);
  const [fieldError, setFieldError] = useState('');

  useEffect(() => { document.title = 'Create API Management resource · SARAISE'; }, []);
  useEffect(() => {
    if (!policy) return;
    setDescription((current) => current ?? policy.resource_description_default);
    setResourceConfig((current) => current ?? policy.resource_config_default);
  }, [policy]);

  const create = useMutation({
    mutationFn: (request: ApiManagementResourceCreate) => api_managementService.createResource(request),
    onSuccess: async (resource) => { await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.RESOURCES() }); toast.success('Resource created'); navigate(ROUTES.RESOURCE_DETAIL(resource.id)); },
    onError: () => toast.error('The resource was rejected by tenant policy.'),
  });

  if (configuration.isLoading) return <div className="p-8" role="status">Loading tenant configuration…</div>;
  if (configuration.error || !configuration.data || !policy || description === null || resourceConfig === null) return <div className="p-8"><ErrorState title="Configuration unavailable" message="Creation is disabled because the tenant policy could not be loaded." onRetry={() => { void configuration.refetch(); }} /></div>;
  if (!policy.feature_enabled) return <div className="p-8"><ErrorState title="API Management is disabled" message="The tenant configuration currently disables resource creation." /></div>;
  const configurationVersion = configuration.data.version;

  const submit = () => {
    const normalized = name.trim();
    if (normalized.length < policy.resource_name_min_length || normalized.length > policy.resource_name_max_length) {
      setFieldError(`Name must contain ${policy.resource_name_min_length}–${policy.resource_name_max_length} characters.`);
      return;
    }
    setFieldError('');
    create.mutate({ name: normalized, description, config: resourceConfig, idempotency_key: crypto.randomUUID() });
  };

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <header><h1 className="text-3xl font-bold text-foreground">Create API Management resource</h1><p className="mt-2 text-sm text-muted-foreground">Defaults and limits come from version {configurationVersion} of the tenant policy.</p></header>
      <Card className="p-6">
        <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <Input id="api-resource-name" label="Name" required minLength={policy.resource_name_min_length} maxLength={policy.resource_name_max_length} value={name} error={fieldError} onInvalid={(event) => { event.preventDefault(); setFieldError(`Name must contain ${policy.resource_name_min_length}–${policy.resource_name_max_length} characters.`); }} onChange={(event) => { setName(event.target.value); setFieldError(''); }} aria-describedby="api-resource-name-guidance" />
          <p id="api-resource-name-guidance" className="text-xs text-muted-foreground">Required; between {policy.resource_name_min_length} and {policy.resource_name_max_length} characters. The same limits are enforced by the API.</p>
          <Textarea id="api-resource-description" label="Description" rows={policy.form_description_rows} value={description} onChange={(event) => setDescription(event.target.value)} />
          <section className="rounded border bg-muted/30 p-4" aria-labelledby="resource-config-heading">
            <h2 id="resource-config-heading" className="font-medium text-foreground">Resource configuration</h2>
            <p className="mt-1 text-sm text-muted-foreground">The validated tenant default is applied. Arbitrary JSON keys cannot be submitted from this form.</p>
            {policy.allowed_resource_config_keys?.length ? <p className="mt-2 text-xs text-muted-foreground">Allowed keys: {policy.allowed_resource_config_keys.join(', ')}</p> : null}
            <pre className="mt-3 overflow-auto rounded bg-background p-3 text-xs text-foreground">{JSON.stringify(resourceConfig, null, 2)}</pre>
          </section>
          {create.error ? <p role="alert" className="text-sm text-destructive">{create.error instanceof Error ? create.error.message : 'Resource creation failed.'}</p> : null}
          <div className="flex justify-end gap-3"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.RESOURCES)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Creating…' : 'Create resource'}</Button></div>
        </form>
      </Card>
    </main>
  );
}
