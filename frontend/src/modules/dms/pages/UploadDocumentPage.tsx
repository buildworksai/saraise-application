import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FileUp, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FolderSelector, MetadataEditor, TagEditor } from '../components/DocumentFields';
import { ApiProblem, MutationProblem, PageHeader, PageSkeleton, formatBytes, useUnsavedChanges } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ROUTES, type DmsConfigurationValues, type DocumentMetadata } from '../contracts';
import { uploadTransportPolicy, useDmsConfiguration } from '../hooks/use-dms-configuration';

function preflight(file: File, configuration: DmsConfigurationValues): string | null { const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`; if (file.size <= 0) return 'The selected file is empty.'; if (file.size > configuration.max_upload_bytes) return `The selected file exceeds the configured ${formatBytes(configuration.max_upload_bytes)} client preflight limit.`; if (configuration.executable_extensions.includes(extension)) return 'This extension is blocked by the tenant content policy.'; return null; }

export function UploadDocumentPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [parameters] = useSearchParams();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [folderId, setFolderId] = useState<string | null>(parameters.get('folder'));
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState<readonly string[]>([]);
  const [metadata, setMetadata] = useState<DocumentMetadata>({});
  const [validation, setValidation] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const configuration = useDmsConfiguration();
  const folderPageSize = configuration.data?.values.folder_page_size;
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: folderPageSize }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: folderPageSize }), enabled: folderPageSize !== undefined });
  const upload = useMutation({ mutationFn: () => { if (!file) throw new Error('Select a file before uploading.'); if (!configuration.data) throw new Error('DMS configuration is unavailable; upload remains fail-closed.'); return dmsService.uploadDocument({ file, name: name.trim(), folder_id: folderId, description, tags, metadata }, { transport: uploadTransportPolicy(configuration.data.values), onProgress: (value) => setProgress(value.percent) }); }, onSuccess: (document) => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); toast.success('Document and version 1 uploaded'); navigate(ROUTES.DOCUMENT_DETAIL(document.id)); } });
  useUnsavedChanges(Boolean(file) && !upload.isSuccess);
  const choose = (next: File | null) => { if (!next || !configuration.data) return; const error = preflight(next, configuration.data.values); setValidation(error); if (error) { setFile(null); return; } setFile(next); if (!name) setName(next.name.replace(/\.[^.]+$/u, '')); };
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); choose(event.dataTransfer.files[0] ?? null); };
  const submit = (event: FormEvent) => { event.preventDefault(); if (!configuration.data) return; const error = file ? preflight(file, configuration.data.values) : 'Choose a file to upload.'; if (!name.trim()) { setValidation('Document name is required.'); return; } setValidation(error); if (!error) upload.mutate(); };
  if (configuration.isLoading || folders.isLoading) return <PageSkeleton/>;
  if (configuration.error || folders.error) return <main className="p-4 sm:p-8"><ApiProblem error={(configuration.error ?? folders.error)!} onRetry={() => { void configuration.refetch(); void folders.refetch(); }}/></main>;
  if (!configuration.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('DMS configuration is unavailable; upload remains fail-closed.')}/></main>;
  const values = configuration.data.values;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Upload document" description="Create document metadata and immutable version 1 in one transactional operation."/><form className="mx-auto max-w-3xl space-y-5" onSubmit={submit}><Card className="p-5"><div role="button" tabIndex={0} className="flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => input.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') input.current?.click(); }} onDragOver={(event) => event.preventDefault()} onDrop={drop}><FileUp className="h-10 w-10 text-primary"/><p className="mt-3 font-semibold">Drop a file here or browse</p><p className="mt-1 text-sm text-muted-foreground">Up to {formatBytes(values.max_upload_bytes)}. Server content inspection and tenant quota remain authoritative.</p><input ref={input} className="sr-only" type="file" aria-label="Choose document file" onChange={(event) => choose(event.target.files?.[0] ?? null)}/></div>{file ? <div className="mt-3 flex items-center justify-between rounded-lg bg-muted p-3 text-sm"><span>{file.name} · {formatBytes(file.size)}</span><Button type="button" size="icon" variant="ghost" aria-label="Clear selected file" onClick={() => { setFile(null); setProgress(0); }}><X className="h-4 w-4"/></Button></div> : null}</Card><Card className="space-y-4 p-5"><Input id="upload-name" label="Document name" required maxLength={values.max_name_length} value={name} onChange={(event) => setName(event.target.value)}/><Textarea id="upload-description" label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/>{folders.data?.items.length ? <FolderSelector folders={folders.data.items} value={folderId} onChange={setFolderId}/> : <div role="status" className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">No folders exist yet. The document will be uploaded to Documents (root).</div>}<TagEditor value={tags} onChange={setTags} maxTags={values.max_document_tags} maxTagLength={values.max_tag_length}/><MetadataEditor value={metadata} onChange={setMetadata} maxKeyLength={values.max_metadata_key_length}/></Card>{validation ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{validation}</div> : null}{upload.error ? <MutationProblem error={upload.error}/> : null}{upload.isPending ? <Card className="p-4"><progress className="w-full" max={100} value={progress}/><p role="status" className="mt-2 text-sm text-muted-foreground">Uploading {progress}% — keep this page open until durable storage is confirmed.</p></Card> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={upload.isPending} onClick={() => navigate(ROUTES.DOCUMENTS)}>Cancel</Button><Button type="submit" disabled={upload.isPending || !file}>{upload.isPending ? 'Uploading…' : 'Upload document'}</Button></div></form></main>;
}
