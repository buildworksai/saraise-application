import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FolderSelector, MetadataEditor, TagEditor } from '../components/DocumentFields';
import { ApiProblem, MutationProblem, PageHeader, PageSkeleton, useUnsavedChanges } from '../components/DmsUI';
import { ROUTES, type DocumentMetadata } from '../contracts';
import { DMS_QUERY_KEYS, DmsApiError, dmsService } from '../services/dms-service';
import { useDmsConfiguration } from '../hooks/use-dms-configuration';

export function EditDocumentPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const configuration = useDmsConfiguration();
  const document = useQuery({ queryKey: DMS_QUERY_KEYS.document(id), queryFn: () => dmsService.getDocument(id), enabled: Boolean(id) });
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: configuration.data?.values.folder_page_size }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: configuration.data?.values.folder_page_size }), enabled: configuration.data !== undefined });
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [tags, setTags] = useState<readonly string[]>([]); const [metadata, setMetadata] = useState<DocumentMetadata>({}); const [folderId, setFolderId] = useState<string | null>(null); const [loadedRevision, setLoadedRevision] = useState(''); const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!document.data || dirty) return; setName(document.data.name); setDescription(document.data.description); setTags(document.data.tags); setMetadata(document.data.metadata); setFolderId(document.data.folder_id); setLoadedRevision(document.data.updated_at); }, [document.data, dirty]);
  useUnsavedChanges(dirty);
  const save = useMutation({ mutationFn: async () => { const updated = await dmsService.updateDocument(id, { name, description, tags, metadata, expected_updated_at: loadedRevision }); if (folderId !== updated.folder_id) return dmsService.moveDocument(id, { folder_id: folderId, expected_updated_at: updated.updated_at }); return updated; }, onSuccess: (updated) => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); setDirty(false); toast.success('Document metadata updated'); navigate(ROUTES.DOCUMENT_DETAIL(updated.id)); } });
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };
  if (configuration.isLoading || document.isLoading || folders.isLoading) return <PageSkeleton/>;
  if (configuration.error || document.error || folders.error) return <main className="p-4 sm:p-8"><ApiProblem error={configuration.error ?? document.error ?? folders.error ?? new Error('Document failed to load')} onRetry={() => { void configuration.refetch(); void document.refetch(); void folders.refetch(); }}/></main>;
  if (!configuration.data || !document.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('The document or governed DMS configuration response was empty.')}/></main>;
  const conflict = save.error instanceof DmsApiError && save.error.problem.kind === 'conflict';
  const values = configuration.data.values;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${document.data.name}`} description="Metadata and folder placement only. File content changes through an immutable version." actions={<Button variant="outline" type="button" onClick={() => navigate(`${ROUTES.DOCUMENT_DETAIL(id)}?tab=versions`)}><Upload className="mr-2 h-4 w-4"/>Upload new version</Button>}/><form className="mx-auto max-w-3xl space-y-5" onSubmit={submit} onChange={() => setDirty(true)}><Card className="space-y-4 p-5"><Input label="Document name" required maxLength={values.max_name_length} value={name} onChange={(event) => setName(event.target.value)}/><Textarea label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/><FolderSelector folders={folders.data?.items ?? []} value={folderId} onChange={(value) => { setFolderId(value); setDirty(true); }}/><TagEditor value={tags} onChange={(value) => { setTags(value); setDirty(true); }} maxTags={values.max_document_tags} maxTagLength={values.max_tag_length}/><MetadataEditor value={metadata} onChange={(value) => { setMetadata(value); setDirty(true); }} maxKeyLength={values.max_metadata_key_length}/><p className="text-xs text-muted-foreground">Loaded revision {new Date(loadedRevision).toLocaleString()}. Saving sends an optimistic concurrency condition.</p></Card>{save.error ? <MutationProblem error={save.error}/> : null}{conflict ? <Button type="button" variant="outline" onClick={() => { setDirty(false); save.reset(); void document.refetch(); }}>Reload current values</Button> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={save.isPending} onClick={() => navigate(ROUTES.DOCUMENT_DETAIL(id))}>Cancel</Button><Button type="submit" disabled={save.isPending || !name.trim()}>{save.isPending ? 'Saving…' : 'Save changes'}</Button></div></form></main>;
}
