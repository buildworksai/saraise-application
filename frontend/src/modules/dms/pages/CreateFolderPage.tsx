import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FolderSelector } from '../components/DocumentFields';
import { MutationProblem, PageHeader, useUnsavedChanges } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ROUTES } from '../contracts';

export function CreateFolderPage() {
  const navigate = useNavigate(); const client = useQueryClient(); const [parameters] = useSearchParams();
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [parentId, setParentId] = useState<string | null>(parameters.get('parent')); const [dirty, setDirty] = useState(false);
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: 100 }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: 100 }) });
  const parent = folders.data?.items.find((folder) => folder.id === parentId);
  const depthError = parent && parent.depth >= 10 ? 'The selected parent is already at the maximum folder depth.' : null;
  const duplicate = folders.data?.items.some((folder) => folder.parent_id === parentId && folder.name.localeCompare(name.trim(), undefined, { sensitivity: 'accent' }) === 0) ?? false;
  const create = useMutation({ mutationFn: () => dmsService.createFolder({ name: name.trim(), description, parent_id: parentId }), onSuccess: (folder) => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); setDirty(false); toast.success('Folder created'); navigate(ROUTES.FOLDER_DETAIL(folder.id)); } });
  useUnsavedChanges(dirty);
  const submit = (event: FormEvent) => { event.preventDefault(); if (!name.trim() || duplicate || depthError) return; create.mutate(); };
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create folder" description="Folder path and depth are calculated and tenant-validated by the service."/><form className="mx-auto max-w-2xl space-y-5" onSubmit={submit} onChange={() => setDirty(true)}><Card className="space-y-4 p-5"><Input label="Folder name" required maxLength={255} value={name} error={duplicate ? 'A sibling folder already uses this name.' : undefined} onChange={(event) => setName(event.target.value.normalize('NFC'))}/><Textarea label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/><FolderSelector folders={folders.data?.items ?? []} value={parentId} onChange={(value) => { setParentId(value); setDirty(true); }} label="Parent folder"/>{depthError ? <p role="alert" className="text-sm text-destructive">{depthError}</p> : null}</Card>{create.error ? <MutationProblem error={create.error}/> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => navigate(parentId !== null ? ROUTES.FOLDER_DETAIL(parentId) : ROUTES.DOCUMENTS)}>Cancel</Button><Button type="submit" disabled={create.isPending || !name.trim() || duplicate || Boolean(depthError)}>{create.isPending ? 'Creating…' : 'Create folder'}</Button></div></form></main>;
}
