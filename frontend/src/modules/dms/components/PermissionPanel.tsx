import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Plus, Search } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import type { DocumentPermissionCreate, DocumentPermissionLevel, PrincipalSummary, PrincipalType, UUID } from '../contracts';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ApiProblem, EmptyPanel, MutationProblem, formatDate } from './DmsUI';

export interface PrincipalDirectoryPort { search(query: string, type: PrincipalType): Promise<readonly PrincipalSummary[]> }
const dmsPrincipalDirectory: PrincipalDirectoryPort = { search: (query, type) => dmsService.searchPrincipals(query, type) };

const explanations: Readonly<Record<DocumentPermissionLevel, string>> = {
  read: 'View metadata, versions, and content.',
  write: 'Read plus edit metadata and add versions.',
  delete: 'Write plus soft-delete the document.',
  share: 'Read plus create governed share links.',
  manage: 'All document and access-administration capabilities.',
};
const principalTypes: readonly PrincipalType[] = ['user', 'role', 'group'];
const permissionLevels: readonly DocumentPermissionLevel[] = ['read', 'write', 'delete', 'share', 'manage'];
function principalType(value: string): PrincipalType { return principalTypes.find((item) => item === value) ?? 'user'; }
function permissionLevel(value: string): DocumentPermissionLevel { return permissionLevels.find((item) => item === value) ?? 'read'; }

export function PermissionDialog({ open, onOpenChange, documentId, directory, onGrant }: { readonly open: boolean; readonly onOpenChange: (open: boolean) => void; readonly documentId: UUID; readonly directory?: PrincipalDirectoryPort; readonly onGrant: (request: DocumentPermissionCreate) => void }) {
  const [type, setType] = useState<PrincipalType>('user');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<PrincipalSummary | null>(null);
  const [permission, setPermission] = useState<DocumentPermissionLevel>('read');
  const activeDirectory = directory ?? dmsPrincipalDirectory;
  const results = useQuery({ queryKey: DMS_QUERY_KEYS.principals(search, type), queryFn: () => activeDirectory.search(search, type), enabled: open && search.trim().length >= 2 });
  const submit = () => { if (!selected) return; onGrant({ document_id: documentId, principal_type: selected.type, principal_id: selected.id, permission }); };
  return <Dialog open={open} onOpenChange={onOpenChange} title="Grant document access" description="Select a verified tenant principal. Owner access is implicit and cannot be duplicated." size="lg"><div className="space-y-4"><label className="block text-sm font-medium">Principal type<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={type} onChange={(event) => { setType(principalType(event.target.value)); setSelected(null); }}><option value="user">User</option><option value="role">Role</option><option value="group">Group</option></select></label>{directory ? <div><Input label="Search tenant directory" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Enter at least two characters"/><div className="mt-2 max-h-44 overflow-auto rounded border">{results.isFetching ? <p className="p-3 text-sm text-muted-foreground">Searching verified principals…</p> : results.data?.length ? results.data.map((principal) => <button type="button" key={`${principal.type}:${principal.id}`} className={`block w-full border-b px-3 py-2 text-left text-sm last:border-0 ${selected?.id === principal.id ? 'bg-primary/10' : 'hover:bg-muted'}`} onClick={() => setSelected(principal)}><span className="font-medium">{principal.display_name}</span>{principal.secondary_text ? <span className="ml-2 text-muted-foreground">{principal.secondary_text}</span> : null}</button>) : search.length >= 2 ? <p className="p-3 text-sm text-muted-foreground">No verified principals match.</p> : null}</div></div> : <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100"><Search className="mr-2 inline h-4 w-4"/>Tenant directory search is unavailable. Access remains fail-closed; configure an identity-directory adapter to grant new principals.</div>}<label className="block text-sm font-medium">Permission<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={permission} onChange={(event) => setPermission(permissionLevel(event.target.value))}>{Object.entries(explanations).map(([level, text]) => <option key={level} value={level}>{level} — {text}</option>)}</select></label><p className="rounded bg-muted p-3 text-sm">{explanations[permission]}</p><div className="flex justify-end gap-2"><Button variant="outline" type="button" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="button" disabled={!selected} onClick={submit}>Grant access</Button></div></div></Dialog>;
}

export function PermissionPanel({ documentId, canManage, directory }: { readonly documentId: UUID; readonly canManage: boolean; readonly directory?: PrincipalDirectoryPort }) {
  const client = useQueryClient();
  const [dialog, setDialog] = useState(false);
  const query = useQuery({ queryKey: DMS_QUERY_KEYS.permissions(documentId), queryFn: () => dmsService.listPermissions(documentId) });
  const refresh = () => client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.permissions(documentId) });
  const grant = useMutation({ mutationFn: dmsService.createPermission, onSuccess: () => { void refresh(); setDialog(false); toast.success('Document access granted'); } });
  const change = useMutation({ mutationFn: ({ id, permission }: { readonly id: UUID; readonly permission: DocumentPermissionLevel }) => dmsService.updatePermission(id, { permission }), onSuccess: () => { void refresh(); toast.success('Document access updated'); } });
  const revoke = useMutation({ mutationFn: dmsService.revokePermission, onSuccess: () => { void refresh(); toast.success('Document access revoked'); } });
  if (query.isLoading) return <Card className="space-y-3 p-5"><Skeleton className="h-10"/><Skeleton className="h-20"/></Card>;
  if (query.error) return <ApiProblem error={query.error} onRetry={() => void query.refetch()}/>;
  const permissions = query.data?.items ?? [];
  return <section className="space-y-4"><div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold">Document access</h2><p className="text-sm text-muted-foreground">Owner access is implicit. Higher permissions include the capabilities described below.</p></div>{canManage ? <Button onClick={() => setDialog(true)}><Plus className="mr-2 h-4 w-4"/>Grant access</Button> : null}</div>{grant.error ? <MutationProblem error={grant.error}/> : null}{permissions.length === 0 ? <EmptyPanel filtered={false} folder={false} action={canManage ? <Button onClick={() => setDialog(true)}>Grant first access</Button> : undefined}/> : <Card className="overflow-hidden"><ul className="divide-y">{permissions.map((item) => <li key={item.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-start gap-3"><KeyRound className="mt-1 h-4 w-4 text-primary"/><div><p className="font-medium">{item.principal_display ?? `${item.principal_type} · ${item.principal_id}`}</p><p className="text-xs text-muted-foreground">Granted {formatDate(item.created_at)}</p></div></div>{canManage ? <div className="flex gap-2"><select aria-label={`Permission for ${item.principal_display ?? item.principal_id}`} className="rounded-md border bg-background px-2 py-1 text-sm" value={item.permission} disabled={change.isPending || revoke.isPending} onChange={(event) => change.mutate({ id: item.id, permission: permissionLevel(event.target.value) })}>{Object.keys(explanations).map((level) => <option key={level} value={level}>{level}</option>)}</select><Button size="sm" variant="danger" disabled={revoke.isPending} onClick={() => { if (window.confirm('Revoke this audited grant?')) revoke.mutate(item.id); }}>Revoke</Button></div> : <span className="rounded-full bg-muted px-3 py-1 text-xs">{item.permission}</span>}</li>)}</ul></Card>}<PermissionDialog open={dialog} onOpenChange={setDialog} documentId={documentId} directory={directory ?? dmsPrincipalDirectory} onGrant={(request) => grant.mutate(request)}/></section>;
}
