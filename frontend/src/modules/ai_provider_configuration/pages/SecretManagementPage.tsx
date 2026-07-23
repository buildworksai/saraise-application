import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, Clipboard, KeyRound, LockKeyhole, RefreshCw, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { ApiProblem, ConsoleHeader, ConsoleSkeleton, EmptyPanel } from '../components/ConsolePrimitives';
import { formatDate } from '../components/formatters';
import { aiProviderConfigurationService } from '../services/ai_provider_configuration-service';
import { secretService } from '../services/secret-service';
import { useAiProviderDocumentTitle } from '../use-ai-provider-document-title';

export const SecretManagementPage = () => {
  useAiProviderDocumentTitle('Secret operations');
  const [rotationOpen, setRotationOpen] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [oldKey, setOldKey] = useState('');
  const [replacementKey, setReplacementKey] = useState('');
  const [copied, setCopied] = useState(false);
  const credentials = useQuery({ queryKey: ['ai-provider-configuration', 'credentials'], queryFn: () => aiProviderConfigurationService.listCredentials() });
  const runtimeConfiguration = useQuery({ queryKey: ['ai-provider-configuration', 'runtime-configuration'], queryFn: aiProviderConfigurationService.getRuntimeConfiguration });
  const presentation = typeof runtimeConfiguration.data?.values.presentation === 'object' && runtimeConfiguration.data.values.presentation !== null
    ? runtimeConfiguration.data.values.presentation as Record<string, unknown>
    : {};
  const copiedTimeoutMs = typeof presentation.copied_indicator_timeout_ms === 'number' ? presentation.copied_indicator_timeout_ms : 1000;
  const rotate = useMutation({
    mutationFn: secretService.rotateKey,
    onSuccess: (response) => { setNewKey(response.new_key); toast.success('New encryption key generated'); },
    onError: () => toast.error('A new encryption key could not be generated.'),
  });
  const reEncrypt = useMutation({
    mutationFn: () => secretService.reEncrypt({ old_key: oldKey, new_key: replacementKey }),
    onSuccess: (response) => {
      setOldKey(''); setReplacementKey('');
      toast.success(`${response.re_encrypted_count} credentials re-encrypted`);
    },
    onError: () => toast.error('Re-encryption failed. No success is assumed; verify the supplied keys.'),
  });

  useEffect(() => () => { setNewKey(''); }, []);
  const copyKey = async () => {
    try { await navigator.clipboard.writeText(newKey); setCopied(true); window.setTimeout(() => setCopied(false), copiedTimeoutMs); }
    catch { toast.error('Clipboard access was denied. Select and copy the key manually.'); }
  };
  const submitReEncryption = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!oldKey || !replacementKey) return toast.error('Both the current and replacement key are required.');
    await reEncrypt.mutateAsync();
  };

  return (
    <div className="min-h-full bg-muted/20">
      <ConsoleHeader title="Secret operations" description="Rotate tenant encryption material deliberately, with an explicit handoff between key generation and credential re-encryption." />
      {credentials.isLoading ? <ConsoleSkeleton /> : credentials.error ? <main className="p-4 sm:p-6 lg:p-8"><ApiProblem error={credentials.error} onRetry={() => { void credentials.refetch(); }} /></main> : (
        <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
          <Card className="border-border bg-muted/30 p-5"><div className="flex gap-3"><ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-primary" /><div><h2 className="font-medium">Plan key rotation as a controlled operation</h2><p className="mt-1 text-sm text-muted-foreground">Generate and store the replacement key in your approved secret manager before re-encrypting credentials. Losing either key during the transition can make provider credentials unavailable.</p></div></div></Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><RefreshCw className="h-5 w-5 text-primary" />1. Generate replacement key</CardTitle><CardDescription>The new key is displayed once in this browser session. It is not saved by the console.</CardDescription></CardHeader><CardContent>{newKey ? <div className="space-y-4"><div className="rounded-lg border bg-muted/40 p-4"><p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">New encryption key</p><code className="block break-all text-sm" data-testid="new-encryption-key">{newKey}</code></div><Button variant="outline" onClick={() => { void copyKey(); }}>{copied ? <Check className="mr-2 h-4 w-4" /> : <Clipboard className="mr-2 h-4 w-4" />}{copied ? 'Copied' : 'Copy key'}</Button><p className="text-xs text-destructive">Store this key now. Navigating away clears it from the console.</p></div> : <Button onClick={() => setRotationOpen(true)}><KeyRound className="mr-2 h-4 w-4" />Generate new key</Button>}</CardContent></Card>
            <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><LockKeyhole className="h-5 w-5 text-primary" />2. Re-encrypt credentials</CardTitle><CardDescription>Re-wrap every active credential in this tenant with the stored replacement key.</CardDescription></CardHeader><CardContent><form className="space-y-4" onSubmit={(event) => { void submitReEncryption(event); }}><Input id="current-encryption-key" label="Current encryption key" type="password" autoComplete="off" value={oldKey} onChange={(event) => setOldKey(event.target.value)} /><Input id="replacement-encryption-key" label="Replacement encryption key" type="password" autoComplete="off" value={replacementKey} onChange={(event) => setReplacementKey(event.target.value)} /><Button type="submit" variant="danger" disabled={reEncrypt.isPending}>{reEncrypt.isPending ? 'Re-encrypting…' : 'Re-encrypt all credentials'}</Button></form></CardContent></Card>
          </div>
          <Card><CardHeader><CardTitle className="text-lg">Protected credential inventory</CardTitle><CardDescription>Only non-sensitive metadata is exposed. Secret values are never loaded into this page.</CardDescription></CardHeader><CardContent>{credentials.data?.length ? <div className="overflow-x-auto"><table className="w-full min-w-[640px]"><thead><tr className="border-b"><th className="py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Label</th><th className="py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Provider</th><th className="py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Secret hint</th><th className="py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Updated</th></tr></thead><tbody className="divide-y">{credentials.data.map((credential) => <tr key={credential.id}><td className="py-4 text-sm font-medium">{credential.label}</td><td className="py-4 text-sm">{credential.provider_name}</td><td className="py-4 font-mono text-sm">•••• {credential.secret_hint}</td><td className="py-4 text-sm text-muted-foreground">{formatDate(credential.updated_at)}</td></tr>)}</tbody></table></div> : <EmptyPanel icon={<KeyRound className="h-5 w-5" />} title="No protected credentials" description="There is no credential material to rotate in this tenant." />}</CardContent></Card>
        </main>
      )}
      <ConfirmDialog open={rotationOpen} onOpenChange={setRotationOpen} title="Generate a replacement encryption key?" description="This does not re-encrypt credentials automatically. Store the generated key securely, then complete step 2." confirmLabel="Generate key" onConfirm={() => rotate.mutate()} />
    </div>
  );
};
