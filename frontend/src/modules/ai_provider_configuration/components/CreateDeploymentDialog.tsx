import { useEffect, useState } from 'react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import type { AIModel, AIModelDeploymentCreate } from '../contracts';

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
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('0.7');
  const [maxTokens, setMaxTokens] = useState('1024');
  const [name, setName] = useState('');
  const [credential, setCredential] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) {
      setModel('');
      setTemperature('0.7');
      setMaxTokens('1024');
      setName('');
      setCredential('');
      setError('');
    }
  }, [open]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsedTemperature = Number(temperature);
    const parsedMaxTokens = Number(maxTokens);
    if (!model) return setError('Choose a model.');
    if (!name.trim()) return setError('Deployment name is required.');
    if (!Number.isFinite(parsedTemperature) || parsedTemperature < 0 || parsedTemperature > 2) return setError('Temperature must be between 0 and 2.');
    if (!Number.isInteger(parsedMaxTokens) || parsedMaxTokens < 1) return setError('Maximum tokens must be a positive whole number.');
    setError('');
    await onSubmit({ model, credential: credential || null, deployment_name: name.trim(), status: 'active', config: { temperature: parsedTemperature, max_tokens: parsedMaxTokens } });
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
          <Input id="deployment-temperature" label="Temperature" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} />
          <Input id="deployment-max-tokens" label="Maximum output tokens" type="number" min="1" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} />
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
