import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FolderSelector } from '../components/DocumentFields';
import { ApiProblem, MutationProblem, PageHeader, PageSkeleton, useUnsavedChanges } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ROUTES } from '../contracts';
import { useDmsConfiguration } from '../hooks/use-dms-configuration';

export function CreateFolderPage() {
  const navigate = useNavigate(); const client = useQueryClient(); const [parameters] = useSearchParams();
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [parentId, setParentId] = useState<string | null>(parameters.get('parent')); const [dirty, setDirty] = useState(false);
  const configuration = useDmsConfiguration();
  const folderPageSize = configuration.data?.values.folder_page_size;
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: folderPageSize }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: folderPageSize }), enabled: folderPageSize !== undefined });
  const parent = folders.data?.items.find((folder) => folder.id === parentId);
  const depthError = parent && configuration.data && parent.depth >= configuration.data.values.max_folder_depth ? 'The selected parent is already at the maximum folder depth.' : null;
  const duplicate = folders.data?.items.some((folder) => folder.parent_id === parentId && folder.name.localeCompare(name.trim(), undefined, { sensitivity: 'accent' }) === 0) ?? false;
  const create = useMutation({ mutationFn: () => dmsService.createFolder({ name: name.trim(), description, parent_id: parentId }), onSuccess: (folder) => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); setDirty(false); toast.success('Folder created'); navigate(ROUTES.FOLDER_DETAIL(folder.id)); } });
  useUnsavedChanges(dirty);
  const submit = (event: FormEvent) => { event.preventDefault(); if (!name.trim() || duplicate || depthError) return; create.mutate(); };
  if (configuration.isLoading || folders.isLoading) return <PageSkeleton/>;
  if (configuration.error || folders.error) return <main className="p-4 sm:p-8"><ApiProblem error={(configuration.error ?? folders.error)!} onRetry={() => { void configuration.refetch(); void folders.refetch(); }}/></main>;
  if (!configuration.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('DMS configuration is unavailable; folder creation remains fail-closed.')}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create folder" description="Folder path and depth are calculated and tenant-validated by the service."/><form className="mx-auto max-w-2xl space-y-5" onSubmit={submit} onChange={() => setDirty(true)}><Card className="space-y-4 p-5"><Input label="Folder name" required maxLength={configuration.data.values.max_name_length} value={name} error={duplicate ? 'A sibling folder already uses this name.' : undefined} onChange={(event) => setName(event.target.value.normalize('NFC'))}/><Textarea label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/>{folders.data?.items.length ? <FolderSelector folders={folders.data.items} value={parentId} onChange={(value) => { setParentId(value); setDirty(true); }} label="Parent folder"/> : <div role="status" className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">No parent folders exist. This folder will be created under Documents (root).</div>}{depthError ? <p role="alert" className="text-sm text-destructive">{depthError}</p> : null}</Card>{create.error ? <MutationProblem error={create.error}/> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => navigate(parentId !== null ? ROUTES.FOLDER_DETAIL(parentId) : ROUTES.DOCUMENTS)}>Cancel</Button><Button type="submit" disabled={create.isPending || !name.trim() || duplicate || Boolean(depthError)}>{create.isPending ? 'Creating…' : 'Create folder'}</Button></div></form></main>;
}
