import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  Box,
  Boxes,
  CircleDollarSign,
  KeyRound,
  MoreHorizontal,
  Plus,
  Search,
  Server,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { CreateDeploymentDialog } from '../components/CreateDeploymentDialog';
import {
  ApiProblem,
  ConsoleHeader,
  ConsoleSkeleton,
  DeploymentStatusPill,
  EmptyPanel,
} from '../components/ConsolePrimitives';
import { formatCost, formatDate, formatTokens } from '../components/formatters';
import {
  AI_PROVIDER_ROUTES,
  type AIModel,
  type AIModelDeployment,
  type AIModelDeploymentCreate,
  type AIProvider,
  type AIProviderCredential,
  type AIUsageLog,
  type CredentialStatus,
} from '../contracts';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';
import { useAiProviderDocumentTitle } from '../use-ai-provider-document-title';

const QUERY_ROOT = ['ai-provider-configuration'] as const;
type ConsoleSection = 'providers' | 'credentials' | 'models' | 'deployments' | 'usage';

const sections: { id: ConsoleSection; label: string }[] = [
  { id: 'providers', label: 'Providers' },
  { id: 'credentials', label: 'Credentials' },
  { id: 'models', label: 'Model catalog' },
  { id: 'deployments', label: 'Deployments' },
  { id: 'usage', label: 'Usage' },
];

// This orchestration component intentionally keeps all resource tabs on one cache-coherent screen.
// eslint-disable-next-line complexity, max-lines-per-function
export const AiProviderConfigurationListPage = () => {
  useAiProviderDocumentTitle('AI provider console');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [section, setSection] = useState<ConsoleSection>('providers');
  const [search, setSearch] = useState('');
  const [deploymentDialogOpen, setDeploymentDialogOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ type: 'credential' | 'deployment'; id: string; name: string } | null>(null);

  const providers = useQuery({ queryKey: [...QUERY_ROOT, 'providers'], queryFn: () => aiProviderConfigurationService.listProviders() });
  const credentials = useQuery({ queryKey: [...QUERY_ROOT, 'credentials'], queryFn: () => aiProviderConfigurationService.listCredentials() });
  const models = useQuery({ queryKey: [...QUERY_ROOT, 'models'], queryFn: () => aiProviderConfigurationService.listModels() });
  const deployments = useQuery({ queryKey: [...QUERY_ROOT, 'deployments'], queryFn: () => aiProviderConfigurationService.listDeployments() });
  const usage = useQuery({ queryKey: [...QUERY_ROOT, 'usage'], queryFn: () => aiProviderConfigurationService.listUsageLogs() });
  const health = useQuery({ queryKey: [...QUERY_ROOT, 'health'], queryFn: aiProviderConfigurationService.getHealth, retry: 1 });

  const invalidateTenantData = () => queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
  const createDeployment = useMutation({
    mutationFn: (request: AIModelDeploymentCreate) => aiProviderConfigurationService.createDeployment(request),
    onSuccess: () => {
      setDeploymentDialogOpen(false);
      setSection('deployments');
      void invalidateTenantData();
      toast.success('Deployment created');
    },
    onError: () => toast.error('Deployment could not be created. Review the configuration and try again.'),
  });
  const deleteCredential = useMutation({
    mutationFn: (id: string) => aiProviderConfigurationService.deleteCredential(id),
    onSuccess: () => { void invalidateTenantData(); toast.success('Credential archived'); },
    onError: () => toast.error('Credential could not be archived. It may be used by an active deployment.'),
  });
  const deleteDeployment = useMutation({
    mutationFn: (id: string) => aiProviderConfigurationService.deleteDeployment(id),
    onSuccess: () => { void invalidateTenantData(); toast.success('Deployment archived'); },
    onError: () => toast.error('Deployment could not be archived.'),
  });
  const updateDeployment = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      active ? aiProviderConfigurationService.activateDeployment(id) : aiProviderConfigurationService.deactivateDeployment(id),
    onSuccess: () => { void invalidateTenantData(); toast.success('Deployment status updated'); },
    onError: () => toast.error('Deployment status could not be updated.'),
  });

  const queryError = providers.error ?? credentials.error ?? models.error ?? deployments.error ?? usage.error;
  const isLoading = providers.isLoading || credentials.isLoading || models.isLoading || deployments.isLoading || usage.isLoading;
  const normalizedSearch = search.trim().toLowerCase();
  const providerItems = (providers.data ?? []).filter((item) => `${item.name} ${item.provider_type}`.toLowerCase().includes(normalizedSearch));
  const credentialItems = (credentials.data ?? []).filter((item) => `${item.label} ${item.provider_name} ${item.status}`.toLowerCase().includes(normalizedSearch));
  const modelItems = (models.data ?? []).filter((item) => `${item.display_name} ${item.model_id} ${item.provider_name} ${item.capabilities.join(' ')}`.toLowerCase().includes(normalizedSearch));
  const deploymentItems = (deployments.data ?? []).filter((item) => `${item.deployment_name} ${item.model_name} ${item.provider_name} ${item.status}`.toLowerCase().includes(normalizedSearch));
  const usageItems = (usage.data ?? []).filter((item) => `${item.deployment_name} ${item.model_name} ${item.provider_request_id}`.toLowerCase().includes(normalizedSearch));

  const totals = useMemo(() => ({
    tokens: (usage.data ?? []).reduce((sum, item) => sum + item.total_tokens, 0),
    cost: (usage.data ?? []).reduce((sum, item) => sum + Number(item.cost || 0), 0),
  }), [usage.data]);

  const retryAll = () => {
    void Promise.all([providers.refetch(), credentials.refetch(), models.refetch(), deployments.refetch(), usage.refetch()]);
  };

  return (
    <div className="min-h-full bg-muted/20">
      <ConsoleHeader
        title="AI provider console"
        description="Connect tenant credentials, choose approved models, deploy safe defaults, and understand usage from one provider-neutral control surface."
        actions={
          <>
            <Button variant="outline" onClick={() => navigate(AI_PROVIDER_ROUTES.CONNECT)}><KeyRound className="mr-2 h-4 w-4" />Connect credential</Button>
            <Button onClick={() => setDeploymentDialogOpen(true)} disabled={!models.data?.length}><Plus className="mr-2 h-4 w-4" />New deployment</Button>
          </>
        }
      />

      {isLoading ? <ConsoleSkeleton /> : queryError ? (
        <main className="p-4 sm:p-6 lg:p-8"><ApiProblem error={queryError} onRetry={retryAll} /></main>
      ) : (
        <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="AI provider metrics">
            <Metric icon={<ShieldCheck className="h-5 w-5" />} label="Connected credentials" value={credentials.data?.length ?? 0} detail={`${credentialItems.filter((item) => item.status === 'valid').length} verified`} />
            <Metric icon={<Server className="h-5 w-5" />} label="Active deployments" value={(deployments.data ?? []).filter((item) => item.status === 'active').length} detail={`${deployments.data?.length ?? 0} configured`} />
            <Metric icon={<Activity className="h-5 w-5" />} label="Tokens recorded" value={formatTokens(totals.tokens)} detail="Tenant usage evidence" />
            <Metric icon={<CircleDollarSign className="h-5 w-5" />} label="Recorded cost" value={formatCost(totals.cost)} detail={health.data?.status === 'healthy' ? 'Service healthy' : health.isError ? 'Health unavailable' : health.data?.status ?? 'Checking health'} />
          </section>

          <Card>
            <CardHeader className="gap-4 border-b lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-lg">Tenant configuration</CardTitle>
                <CardDescription>Provider catalogs remain platform-managed; credentials, deployments, and usage are tenant-isolated.</CardDescription>
              </div>
              <div className="relative w-full lg:w-80">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <Input aria-label={`Search ${section}`} placeholder={`Search ${sections.find((item) => item.id === section)?.label.toLowerCase()}…`} value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" />
              </div>
            </CardHeader>
            <div className="flex gap-1 overflow-x-auto border-b p-2" role="tablist" aria-label="Configuration resources">
              {sections.map((item) => (
                <button key={item.id} role="tab" aria-selected={section === item.id} onClick={() => { setSection(item.id); setSearch(''); }} className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors ${section === item.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>{item.label}</button>
              ))}
            </div>
            <CardContent className="p-0">
              {section === 'providers' && <ProvidersPanel items={providerItems} onOpen={(id) => navigate(AI_PROVIDER_ROUTES.PROVIDER(id))} />}
              {section === 'credentials' && <CredentialsPanel items={credentialItems} onConnect={() => navigate(AI_PROVIDER_ROUTES.CONNECT)} onDelete={(id, name) => setPendingDelete({ type: 'credential', id, name })} />}
              {section === 'models' && <ModelsPanel items={modelItems} onDeploy={() => setDeploymentDialogOpen(true)} />}
              {section === 'deployments' && <DeploymentsPanel items={deploymentItems} isUpdating={updateDeployment.isPending} onToggle={(id, active) => updateDeployment.mutate({ id, active })} onDelete={(id, name) => setPendingDelete({ type: 'deployment', id, name })} onCreate={() => setDeploymentDialogOpen(true)} />}
              {section === 'usage' && <UsagePanel items={usageItems} />}
            </CardContent>
          </Card>
        </main>
      )}

      <CreateDeploymentDialog
        open={deploymentDialogOpen}
        onOpenChange={setDeploymentDialogOpen}
        models={models.data ?? []}
        credentials={(credentials.data ?? []).filter((item) => item.status !== 'invalid')}
        isSubmitting={createDeployment.isPending}
        onSubmit={(request) => createDeployment.mutateAsync(request).then(() => undefined)}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => { if (!open) setPendingDelete(null); }}
        title={`Archive ${pendingDelete?.type ?? 'resource'}?`}
        description={`${pendingDelete?.name ?? 'This resource'} will no longer be available for new work. Existing usage evidence is retained.`}
        confirmLabel="Archive"
        variant="danger"
        onConfirm={() => {
          if (pendingDelete?.type === 'credential') deleteCredential.mutate(pendingDelete.id);
          if (pendingDelete?.type === 'deployment') deleteDeployment.mutate(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
    </div>
  );
};

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return <Card className="p-5"><div className="flex items-center justify-between text-muted-foreground"><p className="text-sm font-medium">{label}</p><span className="rounded-md bg-primary/10 p-2 text-primary">{icon}</span></div><p className="mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></Card>;
}

function ProvidersPanel({ items, onOpen }: { items: AIProvider[]; onOpen: (id: string) => void }) {
  if (!items.length) return <EmptyPanel icon={<Boxes className="h-5 w-5" />} title="No matching providers" description="No active catalog provider matches this search." />;
  return <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">{items.map((provider) => <button key={provider.id} onClick={() => onOpen(provider.id)} className="group rounded-lg border p-5 text-left transition hover:border-primary/50 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-start justify-between"><span className="rounded-lg bg-primary/10 p-3 text-primary"><Box className="h-5 w-5" /></span><MoreHorizontal className="h-5 w-5 text-muted-foreground" /></div><h3 className="mt-4 font-semibold group-hover:text-primary">{provider.name}</h3><p className="mt-1 text-sm capitalize text-muted-foreground">{provider.provider_type.replaceAll('_', ' ')}</p><div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground"><span>{provider.models_count} models</span><span>{provider.is_active ? 'Catalog active' : 'Unavailable'}</span></div></button>)}</div>;
}

function CredentialsPanel({ items, onConnect, onDelete }: { items: AIProviderCredential[]; onConnect: () => void; onDelete: (id: string, name: string) => void }) {
  if (!items.length) return <div className="p-4"><EmptyPanel icon={<KeyRound className="h-5 w-5" />} title="No credentials connected" description="Add a tenant credential to authorize provider requests. Secret values are encrypted and never returned by the API." action={<Button onClick={onConnect}><Plus className="mr-2 h-4 w-4" />Connect credential</Button>} /></div>;
  return <ResponsiveTable headings={['Credential', 'Provider', 'Secret', 'Status', 'Last verified', '']} rows={items.map((credential) => [<div key="name"><p className="font-medium">{credential.label}</p><p className="font-mono text-xs text-muted-foreground">{credential.id.slice(0, 8)}</p></div>, credential.provider_name, <span key="secret" className="font-mono text-sm">•••• {credential.secret_hint || '—'}</span>, <CredentialStatus key="status" status={credential.status} />, formatDate(credential.last_verified_at), <Button key="delete" size="icon" variant="ghost" aria-label={`Archive ${credential.label}`} onClick={() => onDelete(credential.id, credential.label)}><Trash2 className="h-4 w-4 text-destructive" /></Button>])} />;
}

function CredentialStatus({ status }: { status: CredentialStatus }) {
  const style = status === 'valid' ? 'bg-primary/10 text-primary' : status === 'invalid' ? 'bg-destructive/15 text-destructive' : 'bg-muted text-foreground';
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${style}`}>{status}</span>;
}

function ModelsPanel({ items, onDeploy }: { items: AIModel[]; onDeploy: () => void }) {
  if (!items.length) return <div className="p-4"><EmptyPanel icon={<Box className="h-5 w-5" />} title="No models found" description="The active provider catalog does not contain a matching model." /></div>;
  return <div className="divide-y">{items.map((model) => <div key={model.id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{model.display_name}</h3><span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{model.provider_name}</span></div><p className="mt-1 font-mono text-xs text-muted-foreground">{model.model_id}</p><div className="mt-2 flex flex-wrap gap-1">{model.capabilities.map((capability) => <span key={capability} className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">{capability.replaceAll('_', ' ')}</span>)}</div></div><div className="flex items-center gap-4"><div className="text-right text-xs text-muted-foreground"><p>{model.max_tokens ? `${formatTokens(model.max_tokens)} token context` : 'Context not published'}</p><p>{model.deployments_count} deployments</p></div><Button size="sm" variant="outline" onClick={onDeploy}>Deploy</Button></div></div>)}</div>;
}

function DeploymentsPanel({ items, isUpdating, onToggle, onDelete, onCreate }: { items: AIModelDeployment[]; isUpdating: boolean; onToggle: (id: string, active: boolean) => void; onDelete: (id: string, name: string) => void; onCreate: () => void }) {
  if (!items.length) return <div className="p-4"><EmptyPanel icon={<Server className="h-5 w-5" />} title="No deployments configured" description="Deploy an approved model with tenant-specific inference settings." action={<Button onClick={onCreate}><Plus className="mr-2 h-4 w-4" />New deployment</Button>} /></div>;
  return <ResponsiveTable headings={['Deployment', 'Model', 'Configuration', 'Status', 'Updated', 'Actions']} rows={items.map((deployment) => [<div key="name"><p className="font-medium">{deployment.deployment_name}</p><p className="text-xs text-muted-foreground">{deployment.provider_name}</p></div>, <div key="model"><p>{deployment.model_name}</p><p className="font-mono text-xs text-muted-foreground">{deployment.model_id}</p></div>, <div key="config" className="text-xs text-muted-foreground"><p>Temp {String(deployment.config.temperature ?? '—')}</p><p>{formatTokens(Number(deployment.config.max_tokens ?? 0))} max tokens</p></div>, <DeploymentStatusPill key="status" status={deployment.status} />, formatDate(deployment.updated_at), <div key="actions" className="flex gap-1"><Button size="sm" variant="outline" disabled={isUpdating || deployment.status === 'error'} onClick={() => onToggle(deployment.id, deployment.status !== 'active')}>{deployment.status === 'active' ? 'Pause' : 'Activate'}</Button><Button size="icon" variant="ghost" aria-label={`Archive ${deployment.deployment_name}`} onClick={() => onDelete(deployment.id, deployment.deployment_name)}><Trash2 className="h-4 w-4 text-destructive" /></Button></div>])} />;
}

function UsagePanel({ items }: { items: AIUsageLog[] }) {
  if (!items.length) return <div className="p-4"><EmptyPanel icon={<Activity className="h-5 w-5" />} title="No usage recorded" description="Verified request-level token and cost evidence will appear after a deployed model is used." /></div>;
  return <ResponsiveTable headings={['Request', 'Deployment', 'Prompt', 'Completion', 'Total', 'Cost', 'Recorded']} rows={items.map((entry) => [<span key="request" className="font-mono text-xs">{entry.provider_request_id || entry.id.slice(0, 8)}</span>, <div key="deployment"><p>{entry.deployment_name}</p><p className="text-xs text-muted-foreground">{entry.model_name}</p></div>, formatTokens(entry.prompt_tokens), formatTokens(entry.completion_tokens), <strong key="total">{formatTokens(entry.total_tokens)}</strong>, formatCost(entry.cost), formatDate(entry.created_at)])} />;
}

function ResponsiveTable({ headings, rows }: { headings: string[]; rows: React.ReactNode[][] }) {
  return <div className="overflow-x-auto"><table className="w-full min-w-[760px]"><thead><tr className="border-b bg-muted/30">{headings.map((heading) => <th key={heading} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{heading}</th>)}</tr></thead><tbody className="divide-y">{rows.map((row, rowIndex) => <tr key={rowIndex} className="hover:bg-muted/20">{row.map((cell, cellIndex) => <td key={cellIndex} className="px-4 py-4 text-sm">{cell}</td>)}</tr>)}</tbody></table></div>;
}
