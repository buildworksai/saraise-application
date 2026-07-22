import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FolderSelector } from '../components/DocumentFields';
import { ApiProblem, MutationProblem, PageHeader, PageSkeleton, useUnsavedChanges } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ROUTES } from '../contracts';

// eslint-disable-next-line complexity
export function EditFolderPage() {
  const { id = '' } = useParams(); const navigate = useNavigate(); const client = useQueryClient();
  const folder = useQuery({ queryKey: DMS_QUERY_KEYS.folder(id), queryFn: () => dmsService.getFolder(id), enabled: Boolean(id) });
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: 100 }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: 100 }) });
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [sortOrder, setSortOrder] = useState(0); const [parentId, setParentId] = useState<string | null>(null); const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!folder.data || dirty) return; setName(folder.data.name); setDescription(folder.data.description); setSortOrder(folder.data.sort_order); setParentId(folder.data.parent_id); }, [folder.data, dirty]);
  useUnsavedChanges(dirty);
  const candidates = useMemo(() => folders.data?.items.filter((item) => item.id !== id && !(folder.data && (item.path === folder.data.path || item.path.startsWith(`${folder.data.path}/`)))) ?? [], [folder.data, folders.data, id]);
  const target = candidates.find((item) => item.id === parentId);
  const subtreeDepth = folder.data ? Math.max(0, ...((folders.data?.items ?? []).filter((item) => item.path.startsWith(`${folder.data?.path}/`)).map((item) => item.depth - folder.data.depth))) : 0;
  const resultingDepth = (target?.depth ?? -1) + 1;
  const depthError = resultingDepth + subtreeDepth > 10 ? 'This move would place a descendant below the maximum depth of 10.' : null;
  const preview = `${target?.path ?? 'Documents'}/${name.trim() || 'Untitled folder'}`;
  const save = useMutation({ mutationFn: async () => { const updated = await dmsService.updateFolder(id, { name: name.trim(), description, sort_order: sortOrder }); if (parentId !== folder.data?.parent_id) return dmsService.moveFolder(id, { parent_id: parentId }); return updated; }, onSuccess: () => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); setDirty(false); toast.success('Folder updated with descendant paths recalculated'); navigate(ROUTES.FOLDER_DETAIL(id)); } });
  const submit = (event: FormEvent) => { event.preventDefault(); if (!depthError && name.trim()) save.mutate(); };
  if (folder.isLoading || folders.isLoading) return <PageSkeleton/>;
  if (folder.error || folders.error) return <main className="p-4 sm:p-8"><ApiProblem error={folder.error ?? folders.error ?? new Error('Folder failed to load')} onRetry={() => { void folder.refetch(); void folders.refetch(); }}/></main>;
  if (!folder.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('Folder response was empty.')}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${folder.data.name}`} description="Rename, reorder, or move this folder. Cycles and excessive depth are rejected before submit and revalidated by the service."/><form className="mx-auto max-w-2xl space-y-5" onSubmit={submit} onChange={() => setDirty(true)}><Card className="space-y-4 p-5"><Input label="Folder name" required maxLength={255} value={name} onChange={(event) => setName(event.target.value.normalize('NFC'))}/><Textarea label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/><FolderSelector folders={candidates} value={parentId} onChange={(value) => { setParentId(value); setDirty(true); }} label="Parent folder" exclude={id}/><Input label="Sort order" type="number" value={sortOrder} onChange={(event) => setSortOrder(Number(event.target.value))}/><div className="rounded-lg border bg-muted/30 p-4"><p className="text-xs font-medium uppercase text-muted-foreground">Resulting breadcrumb</p><p className="mt-1 break-all text-sm">{preview}</p><p className="mt-1 text-xs text-muted-foreground">New depth {resultingDepth}; deepest descendant {resultingDepth + subtreeDepth}.</p></div>{depthError ? <p role="alert" className="text-sm text-destructive">{depthError}</p> : null}</Card>{save.error ? <MutationProblem error={save.error}/> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => navigate(ROUTES.FOLDER_DETAIL(id))}>Cancel</Button><Button type="submit" disabled={save.isPending || !name.trim() || Boolean(depthError)}>{save.isPending ? 'Saving…' : 'Save folder'}</Button></div></form></main>;
}
