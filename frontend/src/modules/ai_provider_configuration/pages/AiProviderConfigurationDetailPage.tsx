import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Box, KeyRound, Server } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { ApiProblem, ConsoleHeader, ConsoleSkeleton, DeploymentStatusPill, EmptyPanel } from '../components/ConsolePrimitives';
import { formatDate } from '../components/formatters';
import { AI_PROVIDER_ROUTES } from '../contracts';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';
import { useAiProviderDocumentTitle } from '../use-ai-provider-document-title';

// Provider detail coordinates four independently cached, read-only projections.
// eslint-disable-next-line complexity
export const AiProviderConfigurationDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  useAiProviderDocumentTitle('AI provider details');
  const navigate = useNavigate();
  const provider = useQuery({ queryKey: ['ai-provider-configuration', 'provider', id], queryFn: () => aiProviderConfigurationService.getProvider(id ?? ''), enabled: Boolean(id) });
  const models = useQuery({ queryKey: ['ai-provider-configuration', 'models', id], queryFn: () => aiProviderConfigurationService.listModels({ provider_id: id }), enabled: Boolean(id) });
  const credentials = useQuery({ queryKey: ['ai-provider-configuration', 'credentials', id], queryFn: () => aiProviderConfigurationService.listCredentials({ provider_id: id }), enabled: Boolean(id) });
  const allDeployments = useQuery({ queryKey: ['ai-provider-configuration', 'deployments', 'provider', id], queryFn: () => aiProviderConfigurationService.listDeployments(), enabled: Boolean(id) });
  const modelIds = new Set((models.data ?? []).map((item) => item.id));
  const deployments = (allDeployments.data ?? []).filter((item) => modelIds.has(item.model));
  const error = provider.error ?? models.error ?? credentials.error ?? allDeployments.error;
  const loading = provider.isLoading || models.isLoading || credentials.isLoading || allDeployments.isLoading;
  const retry = () => { void Promise.all([provider.refetch(), models.refetch(), credentials.refetch(), allDeployments.refetch()]); };

  return (
    <div className="min-h-full bg-muted/20">
      <ConsoleHeader title={provider.data?.name ?? 'Provider details'} description="Review the platform-approved model catalog and this tenant’s provider connection footprint." actions={<><Button variant="outline" onClick={() => navigate(AI_PROVIDER_ROUTES.HOME)}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button><Button onClick={() => navigate(AI_PROVIDER_ROUTES.CONNECT)}><KeyRound className="mr-2 h-4 w-4" />Connect credential</Button></>} />
      {loading ? <ConsoleSkeleton /> : error || !provider.data ? <main className="p-4 sm:p-6 lg:p-8"><ApiProblem error={error ?? new Error('Provider not found')} onRetry={retry} /></main> : (
        <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <DetailMetric label="Provider type" value={provider.data.provider_type.replaceAll('_', ' ')} />
            <DetailMetric label="Catalog models" value={models.data?.length ?? 0} />
            <DetailMetric label="Tenant credentials" value={credentials.data?.length ?? 0} />
            <DetailMetric label="Tenant deployments" value={deployments.length} />
          </section>
          <Card>
            <CardHeader><CardTitle className="text-lg">Model catalog</CardTitle><CardDescription>Approved models available through {provider.data.name}.</CardDescription></CardHeader>
            <CardContent>{models.data?.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{models.data.map((model) => <div key={model.id} className="rounded-lg border p-4"><div className="flex items-center gap-2"><Box className="h-4 w-4 text-primary" /><h3 className="font-medium">{model.display_name}</h3></div><p className="mt-1 font-mono text-xs text-muted-foreground">{model.model_id}</p><p className="mt-3 text-xs text-muted-foreground">{model.max_tokens ? `${model.max_tokens.toLocaleString()} max tokens` : 'Context limit not published'}</p></div>)}</div> : <EmptyPanel icon={<Box className="h-5 w-5" />} title="No active models" description="This provider has no active catalog models." />}</CardContent>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card><CardHeader><CardTitle className="text-lg">Tenant credentials</CardTitle><CardDescription>Secret metadata only.</CardDescription></CardHeader><CardContent>{credentials.data?.length ? <ul className="divide-y">{credentials.data.map((credential) => <li key={credential.id} className="flex items-center justify-between py-3"><div><p className="font-medium">{credential.label}</p><p className="text-xs text-muted-foreground">Updated {formatDate(credential.updated_at)}</p></div><span className="font-mono text-sm text-muted-foreground">•••• {credential.secret_hint}</span></li>)}</ul> : <EmptyPanel icon={<KeyRound className="h-5 w-5" />} title="No credential" description="This tenant is not connected to the provider." />}</CardContent></Card>
            <Card><CardHeader><CardTitle className="text-lg">Deployments</CardTitle><CardDescription>Tenant runtimes backed by this provider.</CardDescription></CardHeader><CardContent>{deployments.length ? <ul className="divide-y">{deployments.map((deployment) => <li key={deployment.id} className="flex items-center justify-between py-3"><div className="flex items-center gap-3"><Server className="h-4 w-4 text-primary" /><div><p className="font-medium">{deployment.deployment_name}</p><p className="text-xs text-muted-foreground">{deployment.model_name}</p></div></div><DeploymentStatusPill status={deployment.status} /></li>)}</ul> : <EmptyPanel icon={<Server className="h-5 w-5" />} title="No deployments" description="No tenant deployment uses this provider." />}</CardContent></Card>
          </div>
        </main>
      )}
    </div>
  );
};

function DetailMetric({ label, value }: { label: string; value: string | number }) {
  return <Card className="p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold capitalize">{value}</p></Card>;
}
