import { useEffect, useState } from 'react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import type { AIModel, AIModelDeploymentCreate } from '../contracts';
import { useQuery } from '@tanstack/react-query';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';

export function CreateDeploymentDialog({
  open,
  onOpenChange,
  models,
  credentials,
  isSubmitting,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  models: AIModel[];
  credentials: { id: string; provider: string; label: string }[];
  isSubmitting: boolean;
  onSubmit: (request: AIModelDeploymentCreate) => Promise<void>;
}) {
  const runtimeConfiguration = useQuery({ queryKey: ['ai-provider-configuration', 'runtime-configuration'], queryFn: aiProviderConfigurationService.getRuntimeConfiguration });
  const values = runtimeConfiguration.data?.values;
  const deploymentPolicy = typeof values?.deployment_policy === 'object' && values.deployment_policy !== null ? values.deployment_policy as Record<string, unknown> : {};
  const defaults = typeof deploymentPolicy.defaults === 'object' && deploymentPolicy.defaults !== null ? deploymentPolicy.defaults as Record<string, unknown> : {};
  const limits = typeof deploymentPolicy.limits === 'object' && deploymentPolicy.limits !== null ? deploymentPolicy.limits as Record<string, unknown> : {};
  const defaultTemperature = typeof defaults.temperature === 'number' ? defaults.temperature : 0;
  const defaultMaxTokens = typeof defaults.max_tokens === 'number' ? defaults.max_tokens : 1;
  const temperatureMin = typeof limits.temperature_min === 'number' ? limits.temperature_min : 0;
  const temperatureMax = typeof limits.temperature_max === 'number' ? limits.temperature_max : 2;
  const maxTokensMin = typeof limits.max_tokens_min === 'number' ? limits.max_tokens_min : 1;
  const maxTokensMax = typeof limits.max_tokens_max === 'number' ? limits.max_tokens_max : undefined;
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('');
  const [maxTokens, setMaxTokens] = useState('');
  const [name, setName] = useState('');
  const [credential, setCredential] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) {
      setModel('');
      setTemperature('');
      setMaxTokens('');
      setName('');
      setCredential('');
      setError('');
    } else {
      setTemperature(String(defaultTemperature));
      setMaxTokens(String(defaultMaxTokens));
    }
  }, [defaultMaxTokens, defaultTemperature, open]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsedTemperature = Number(temperature);
    const parsedMaxTokens = Number(maxTokens);
    if (!model) return setError('Choose a model.');
    if (!name.trim()) return setError('Deployment name is required.');
    if (!Number.isFinite(parsedTemperature) || parsedTemperature < temperatureMin || parsedTemperature > temperatureMax) return setError(`Temperature must be between ${temperatureMin} and ${temperatureMax}.`);
    if (!Number.isInteger(parsedMaxTokens) || parsedMaxTokens < maxTokensMin || (maxTokensMax !== undefined && parsedMaxTokens > maxTokensMax)) return setError('Maximum tokens violates the tenant runtime limits.');
    setError('');
    await onSubmit({ model, credential: credential || null, deployment_name: name.trim(), config: { temperature: parsedTemperature, max_tokens: parsedMaxTokens } });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Create model deployment" description="Deploy a catalog model with tenant-specific inference defaults." size="lg">
      <form className="space-y-4" onSubmit={(event) => { void submit(event); }}>
        <Input id="deployment-name" label="Deployment name" placeholder="Customer support primary" value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
        <div>
          <label htmlFor="deployment-model" className="mb-1 block text-sm font-medium">Model</label>
          <select id="deployment-model" value={model} onChange={(event) => setModel(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">Select a model</option>
            {models.map((item) => <option key={item.id} value={item.id}>{item.provider_name} · {item.display_name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="deployment-credential" className="mb-1 block text-sm font-medium">Credential</label>
          <select id="deployment-credential" value={credential} onChange={(event) => setCredential(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">Use provider default</option>
            {credentials
              .filter((item) => !model || item.provider === models.find((catalogModel) => catalogModel.id === model)?.provider)
              .map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">Only credentials for the selected model provider are available.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input id="deployment-temperature" label="Temperature" type="number" min={temperatureMin} max={temperatureMax} step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} />
          <Input id="deployment-max-tokens" label="Maximum output tokens" type="number" min={maxTokensMin} max={maxTokensMax} step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} />
        </div>
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" disabled={isSubmitting || models.length === 0}>{isSubmitting ? 'Creating…' : 'Create deployment'}</Button>
        </div>
      </form>
    </Dialog>
  );
}
