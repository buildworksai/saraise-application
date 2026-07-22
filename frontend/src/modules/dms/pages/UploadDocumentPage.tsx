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
import { MutationProblem, PageHeader, useUnsavedChanges } from '../components/DmsUI';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';
import { ROUTES, type DocumentMetadata } from '../contracts';

const maximumBytes = 100 * 1024 * 1024;
const deniedExtensions = new Set(['exe', 'dll', 'bat', 'cmd', 'com', 'msi', 'scr', 'sh', 'ps1', 'jar']);
function preflight(file: File): string | null { const extension = file.name.split('.').pop()?.toLowerCase() ?? ''; if (file.size <= 0) return 'The selected file is empty.'; if (file.size > maximumBytes) return 'The selected file exceeds the 100 MiB client preflight limit.'; if (deniedExtensions.has(extension)) return 'Executable and script files are not accepted.'; return null; }

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
  const folders = useQuery({ queryKey: DMS_QUERY_KEYS.folders({ ordering: 'sort_order', page_size: 100 }), queryFn: () => dmsService.listFolders({ ordering: 'sort_order', page_size: 100 }) });
  const upload = useMutation({ mutationFn: () => { if (!file) throw new Error('Select a file before uploading.'); return dmsService.uploadDocument({ file, name: name.trim(), folder_id: folderId, description, tags, metadata }, { onProgress: (value) => setProgress(value.percent) }); }, onSuccess: (document) => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); toast.success('Document and version 1 uploaded'); navigate(ROUTES.DOCUMENT_DETAIL(document.id)); } });
  useUnsavedChanges(Boolean(file) && !upload.isSuccess);
  const choose = (next: File | null) => { if (!next) return; const error = preflight(next); setValidation(error); if (error) { setFile(null); return; } setFile(next); if (!name) setName(next.name.replace(/\.[^.]+$/u, '')); };
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); choose(event.dataTransfer.files[0] ?? null); };
  const submit = (event: FormEvent) => { event.preventDefault(); const error = file ? preflight(file) : 'Choose a file to upload.'; if (!name.trim()) { setValidation('Document name is required.'); return; } setValidation(error); if (!error) upload.mutate(); };
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Upload document" description="Create document metadata and immutable version 1 in one transactional operation."/><form className="mx-auto max-w-3xl space-y-5" onSubmit={submit}><Card className="p-5"><div role="button" tabIndex={0} className="flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => input.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') input.current?.click(); }} onDragOver={(event) => event.preventDefault()} onDrop={drop}><FileUp className="h-10 w-10 text-primary"/><p className="mt-3 font-semibold">Drop a file here or browse</p><p className="mt-1 text-sm text-muted-foreground">Up to 100 MiB. Server content inspection and tenant quota remain authoritative.</p><input ref={input} className="sr-only" type="file" aria-label="Choose document file" onChange={(event) => choose(event.target.files?.[0] ?? null)}/></div>{file ? <div className="mt-3 flex items-center justify-between rounded-lg bg-muted p-3 text-sm"><span>{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MiB</span><Button type="button" size="icon" variant="ghost" aria-label="Clear selected file" onClick={() => { setFile(null); setProgress(0); }}><X className="h-4 w-4"/></Button></div> : null}</Card><Card className="space-y-4 p-5"><Input id="upload-name" label="Document name" required maxLength={255} value={name} onChange={(event) => setName(event.target.value)}/><Textarea id="upload-description" label="Description" value={description} onChange={(event) => setDescription(event.target.value)}/><FolderSelector folders={folders.data?.items ?? []} value={folderId} onChange={setFolderId}/><TagEditor value={tags} onChange={setTags}/><MetadataEditor value={metadata} onChange={setMetadata}/></Card>{validation ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{validation}</div> : null}{upload.error ? <MutationProblem error={upload.error}/> : null}{upload.isPending ? <Card className="p-4"><progress className="w-full" max={100} value={progress}/><p role="status" className="mt-2 text-sm text-muted-foreground">Uploading {progress}% — keep this page open until durable storage is confirmed.</p></Card> : null}<div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={upload.isPending} onClick={() => navigate(ROUTES.DOCUMENTS)}>Cancel</Button><Button type="submit" disabled={upload.isPending || !file}>{upload.isPending ? 'Uploading…' : 'Upload document'}</Button></div></form></main>;
}
