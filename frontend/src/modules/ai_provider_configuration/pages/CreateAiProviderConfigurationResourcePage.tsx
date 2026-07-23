import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, EyeOff, KeyRound, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiProblem, ConsoleHeader, ConsoleSkeleton } from '../components/ConsolePrimitives';
import { AI_PROVIDER_ROUTES } from '../contracts';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';
import { useAiProviderDocumentTitle } from '../use-ai-provider-document-title';

export const CreateAiProviderConfigurationResourcePage = () => {
  useAiProviderDocumentTitle('Connect provider credential');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState('');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [validationError, setValidationError] = useState('');
  const providers = useQuery({ queryKey: ['ai-provider-configuration', 'providers'], queryFn: () => aiProviderConfigurationService.listProviders() });
  const runtimeConfiguration = useQuery({ queryKey: ['ai-provider-configuration', 'runtime-configuration'], queryFn: aiProviderConfigurationService.getRuntimeConfiguration });
  const values = runtimeConfiguration.data?.values;
  const credentialPolicy = typeof values?.credential_policy === 'object' && values.credential_policy !== null ? values.credential_policy as Record<string, unknown> : {};
  const fieldLimits = typeof values?.field_limits === 'object' && values.field_limits !== null ? values.field_limits as Record<string, unknown> : {};
  const defaultLabel = typeof credentialPolicy.default_label === 'string' ? credentialPolicy.default_label : '';
  const labelMax = typeof fieldLimits.credential_label_max === 'number' ? fieldLimits.credential_label_max : undefined;
  const keyMinimum = typeof fieldLimits.credential_secret_hint_length === 'number' ? fieldLimits.credential_secret_hint_length * 2 : 1;
  const createCredential = useMutation({
    mutationFn: () => aiProviderConfigurationService.createCredential({ provider, label: (label || defaultLabel).trim(), api_key: apiKey }),
    onSuccess: (credential) => {
      void queryClient.invalidateQueries({ queryKey: ['ai-provider-configuration'] });
      toast.success(`${credential.provider_name} credential connected`);
      navigate(AI_PROVIDER_ROUTES.HOME);
    },
    onError: () => toast.error('The credential could not be saved. Check that the label is unique for this provider.'),
  });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!provider) return setValidationError('Select a provider.');
    if (!(label || defaultLabel).trim()) return setValidationError('Credential label is required.');
    if (apiKey.trim().length < keyMinimum) return setValidationError('Enter the complete provider API key.');
    setValidationError('');
    await createCredential.mutateAsync();
  };

  return (
    <div className="min-h-full bg-muted/20">
      <ConsoleHeader title="Connect provider credential" description="Authorize this tenant to use an approved provider. Secret material is encrypted at rest and is never returned by the API." />
      {providers.isLoading ? <ConsoleSkeleton /> : providers.error ? (
        <main className="p-4 sm:p-6 lg:p-8"><ApiProblem error={providers.error} onRetry={() => { void providers.refetch(); }} /></main>
      ) : providers.data?.length === 0 ? (
        <main className="mx-auto max-w-3xl p-4 sm:p-6 lg:p-8">
          <Card className="p-6 text-center">
            <CardTitle>No active providers</CardTitle>
            <CardDescription className="mt-2">The provider catalog has no active entries available for credential creation.</CardDescription>
            <Button className="mt-5" variant="outline" onClick={() => navigate(AI_PROVIDER_ROUTES.HOME)}><ArrowLeft className="mr-2 h-4 w-4" />Return to console</Button>
          </Card>
        </main>
      ) : (
        <main className="mx-auto grid max-w-5xl gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:p-8">
          <Card>
            <CardHeader>
              <CardTitle>Credential details</CardTitle>
              <CardDescription>Use a descriptive label when a provider has separate keys for teams or workloads.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-5" onSubmit={(event) => { void submit(event); }}>
                <div>
                  <label htmlFor="credential-provider" className="mb-1 block text-sm font-medium">Provider</label>
                  <select id="credential-provider" value={provider} onChange={(event) => setProvider(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <option value="">Choose an active provider</option>
                    {(providers.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </div>
                <Input id="credential-label" label="Credential label" value={label} maxLength={labelMax} autoComplete="off" onChange={(event) => setLabel(event.target.value)} placeholder={defaultLabel} />
                <div className="relative">
                  <Input id="credential-api-key" label="Provider API key" type={showKey ? 'text' : 'password'} value={apiKey} autoComplete="new-password" spellCheck={false} onChange={(event) => setApiKey(event.target.value)} className="pr-11 font-mono" placeholder="Paste the key supplied by your provider" />
                  <button type="button" className="absolute right-2 top-7 rounded p-2 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setShowKey((current) => !current)} aria-label={showKey ? 'Hide API key' : 'Show API key'}>{showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button>
                </div>
                {validationError && <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive" role="alert">{validationError}</p>}
                <div className="flex flex-col-reverse gap-2 border-t pt-5 sm:flex-row sm:justify-end">
                  <Button type="button" variant="outline" onClick={() => navigate(AI_PROVIDER_ROUTES.HOME)}><ArrowLeft className="mr-2 h-4 w-4" />Cancel</Button>
                  <Button type="submit" disabled={createCredential.isPending || providers.data?.length === 0}><KeyRound className="mr-2 h-4 w-4" />{createCredential.isPending ? 'Encrypting…' : 'Connect credential'}</Button>
                </div>
              </form>
            </CardContent>
          </Card>
          <aside className="space-y-4" aria-label="Credential security information">
            <Card className="p-5"><LockKeyhole className="h-5 w-5 text-primary" /><h2 className="mt-3 font-medium">Write-only secret</h2><p className="mt-1 text-sm text-muted-foreground">After saving, the console shows only a short hint. The complete key cannot be read back.</p></Card>
            <Card className="p-5"><ShieldCheck className="h-5 w-5 text-primary" /><h2 className="mt-3 font-medium">Tenant isolated</h2><p className="mt-1 text-sm text-muted-foreground">Only deployments in this tenant can reference this credential, and only for a model from the same provider.</p></Card>
          </aside>
        </main>
      )}
    </div>
  );
};
