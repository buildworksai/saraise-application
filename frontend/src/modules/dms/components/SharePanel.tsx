import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Link2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import type { DocumentShare, DocumentShareCreate, UUID } from '../contracts';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ApiProblem, EmptyPanel, MutationProblem, formatDate } from './DmsUI';

function shareStatus(share: DocumentShare): DocumentShare['state'] { return share.state; }

export function CreateShareDialog({ open, onOpenChange, documentId, pending, onCreate }: { readonly open: boolean; readonly onOpenChange: (open: boolean) => void; readonly documentId: UUID; readonly pending: boolean; readonly onCreate: (request: DocumentShareCreate) => void }) {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
  const [expiresAt, setExpiresAt] = useState(tomorrow);
  const [limited, setLimited] = useState(true);
  const [limit, setLimit] = useState(10);
  return <Dialog open={open} onOpenChange={onOpenChange} title="Create secure share" description="The bearer URL is displayed once. Expiry and access policy cannot be omitted." size="md"><div className="space-y-4"><Input id="share-expiry" label="Expires at" type="datetime-local" required min={new Date().toISOString().slice(0, 16)} value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)}/><label className="block text-sm font-medium">Access policy<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={limited ? 'limited' : 'unlimited'} onChange={(event) => setLimited(event.target.value === 'limited')}><option value="limited">Limit number of downloads</option><option value="unlimited">Unlimited until expiry</option></select></label>{limited ? <Input id="share-limit" label="Maximum downloads" type="number" min={1} max={10000} value={limit} onChange={(event) => setLimit(Number(event.target.value))}/> : null}<div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">Anyone holding the URL can download this document until the selected boundary is reached. Send it only through a trusted channel.</div><div className="flex justify-end gap-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={pending || !expiresAt || (limited && (limit < 1 || limit > 10000))} onClick={() => onCreate({ document_id: documentId, expires_at: new Date(expiresAt).toISOString(), max_access_count: limited ? limit : null })}>{pending ? 'Creating…' : 'Create share'}</Button></div></div></Dialog>;
}

export function SharePanel({ documentId, canShare }: { readonly documentId: UUID; readonly canShare: boolean }) {
  const client = useQueryClient();
  const [dialog, setDialog] = useState(false);
  const [oneTimeUrl, setOneTimeUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const query = useQuery({ queryKey: DMS_QUERY_KEYS.shares(documentId), queryFn: () => dmsService.listShares(documentId) });
  const refresh = () => client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.shares(documentId) });
  const create = useMutation({ mutationFn: dmsService.createShare, onSuccess: (created) => { setOneTimeUrl(created.share_url); setDialog(false); void refresh(); toast.success('Secure share created'); } });
  const revoke = useMutation({ mutationFn: dmsService.revokeShare, onSuccess: () => { void refresh(); toast.success('Share revoked'); } });
  if (query.isLoading) return <Card className="space-y-3 p-5"><Skeleton className="h-10"/><Skeleton className="h-20"/></Card>;
  if (query.error) return <ApiProblem error={query.error} onRetry={() => void query.refetch()}/>;
  const shares = query.data?.items ?? [];
  return <section className="space-y-4"><div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold">Secure shares</h2><p className="text-sm text-muted-foreground">Tokens are stored as digests and can never be displayed again.</p></div>{canShare ? <Button onClick={() => setDialog(true)}><Plus className="mr-2 h-4 w-4"/>Create share</Button> : null}</div>{create.error ? <MutationProblem error={create.error}/> : null}{oneTimeUrl ? <Card className="border-emerald-300 p-5" role="status"><div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300"><Check className="h-5 w-5"/><h3 className="font-semibold">Copy this URL now</h3></div><p className="mt-2 text-sm text-muted-foreground">For security, refreshing or closing this notice permanently hides the bearer token.</p><div className="mt-3 flex gap-2"><Input readOnly aria-label="One-time share URL" value={oneTimeUrl}/><Button variant="outline" onClick={() => void navigator.clipboard.writeText(oneTimeUrl).then(() => setCopied(true))}><Copy className="mr-2 h-4 w-4"/>{copied ? 'Copied' : 'Copy'}</Button></div><Button className="mt-3" size="sm" variant="ghost" onClick={() => { setOneTimeUrl(null); setCopied(false); }}>I have saved it</Button></Card> : null}{shares.length === 0 ? <EmptyPanel filtered={false} folder={false} action={canShare ? <Button onClick={() => setDialog(true)}>Create first share</Button> : undefined}/> : <Card className="overflow-hidden"><ul className="divide-y">{shares.map((share) => { const status = shareStatus(share); return <li key={share.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><Link2 className="mt-1 h-4 w-4 text-primary"/><div><p className="font-medium">Token prefix {share.token_prefix}</p><p className="text-xs text-muted-foreground">Expires {formatDate(share.expires_at)} · {share.access_count}{share.max_access_count === null ? '' : ` / ${share.max_access_count}`} downloads</p></div></div><div className="flex items-center gap-2"><span className="rounded-full bg-muted px-3 py-1 text-xs">{status}</span>{canShare && status === 'active' ? <Button size="sm" variant="danger" disabled={revoke.isPending} onClick={() => revoke.mutate(share.id)}>Revoke</Button> : null}</div></li>; })}</ul></Card>}<CreateShareDialog open={dialog} onOpenChange={setDialog} documentId={documentId} pending={create.isPending} onCreate={(request) => create.mutate(request)}/></section>;
}
