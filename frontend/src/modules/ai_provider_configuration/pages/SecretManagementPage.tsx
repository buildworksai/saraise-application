/**
 * Secret Management Page
 *
 * Manages encryption keys and secret re-encryption for AI Provider credentials.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Key, RefreshCw, Shield, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { secretService, type SecretMetadata } from '../services/secret-service';

export const SecretManagementPage = () => {
  const queryClient = useQueryClient();
  const [showRotateDialog, setShowRotateDialog] = useState(false);
  const [newKey, setNewKey] = useState<string>('');

  const { data: secrets, isLoading, error, refetch } = useQuery({
    queryKey: ['ai-provider-secrets'],
    queryFn: secretService.listSecrets,
  });

  const rotateKeyMutation = useMutation({
    mutationFn: secretService.rotateKey,
    onSuccess: (data) => {
      setNewKey(data.new_key);
      setShowRotateDialog(true);
      toast.success('New encryption key generated. Save it securely!');
    },
    onError: () => {
      toast.error('Failed to rotate encryption key');
    },
  });

  const reEncryptMutation = useMutation({
    mutationFn: ({ oldKey, newKey }: { oldKey: string; newKey: string }) =>
      secretService.reEncrypt(oldKey, newKey),
    onSuccess: (data) => {
      toast.success(`Re-encrypted ${data.re_encrypted_count} secrets successfully`);
      setShowRotateDialog(false);
      setNewKey('');
      void queryClient.invalidateQueries({ queryKey: ['ai-provider-secrets'] });
    },
    onError: () => {
      toast.error('Failed to re-encrypt secrets');
    },
  });

  const maskSecret = (id: string): string => {
    // Show first 4 and last 4 characters, mask the rest
    if (id.length <= 8) return '****';
    return `${id.substring(0, 4)}${'*'.repeat(id.length - 8)}${id.substring(id.length - 4)}`;
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString();
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={4} />
      </div>
    );
  }

  if (error) {
    return <ErrorState message="Failed to load secrets" onRetry={() => void refetch()} />;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Secret Management</h1>
          <p className="text-muted-foreground mt-2">
            Manage encryption keys and view encrypted secret metadata
          </p>
        </div>
        <Button
          onClick={() => rotateKeyMutation.mutate()}
          disabled={rotateKeyMutation.isPending}
          variant="outline"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Rotate Encryption Key
        </Button>
      </div>

      {/* Security Notice */}
      <Card className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mt-0.5" />
          <div>
            <h3 className="font-semibold text-yellow-900 dark:text-yellow-100">
              Security Notice
            </h3>
            <p className="text-sm text-yellow-800 dark:text-yellow-200 mt-1">
              Secret values are encrypted at rest using Fernet symmetric encryption.
              Only metadata is displayed here. Never share encryption keys or expose
              decrypted secrets.
            </p>
          </div>
        </div>
      </Card>

      {/* Secrets List */}
      <Card>
        <div className="p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Encrypted Secrets
          </h2>

          {!secrets || secrets.length === 0 ? (
            <EmptyState
              title="No secrets found"
              description="No encrypted secrets are currently stored."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-semibold">Provider</th>
                    <th className="text-left p-3 font-semibold">Type</th>
                    <th className="text-left p-3 font-semibold">Secret ID (Masked)</th>
                    <th className="text-left p-3 font-semibold">Created</th>
                    <th className="text-left p-3 font-semibold">Last Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {secrets.map((secret: SecretMetadata) => (
                    <tr key={secret.id} className="border-b hover:bg-muted/50">
                      <td className="p-3">{secret.provider_name}</td>
                      <td className="p-3">
                        <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 rounded text-sm">
                          {secret.provider_type}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-sm">{maskSecret(secret.id)}</td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {formatDate(secret.created_at)}
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">
                        {formatDate(secret.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* Key Rotation Dialog */}
      {showRotateDialog && (
        <Card className="p-6 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">
                New Encryption Key Generated
              </h3>
              <p className="text-sm text-blue-800 dark:text-blue-200 mb-4">
                Save this key securely. You will need it to re-encrypt existing secrets.
              </p>
              <div className="bg-white dark:bg-gray-800 p-3 rounded border font-mono text-sm break-all mb-4">
                {newKey}
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={() => {
                    navigator.clipboard.writeText(newKey);
                    toast.success('Key copied to clipboard');
                  }}
                  variant="outline"
                  size="sm"
                >
                  Copy Key
                </Button>
                <Button
                  onClick={() => {
                    setShowRotateDialog(false);
                    setNewKey('');
                  }}
                  variant="outline"
                  size="sm"
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};
