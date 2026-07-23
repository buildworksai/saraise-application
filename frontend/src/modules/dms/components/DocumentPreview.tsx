import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Download, Eye, FileWarning } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import type { Document } from '../contracts';
import { dmsService } from '../services/dms-service';
import { ApiProblem, MutationProblem, saveDownload } from './DmsUI';
import { useDmsConfiguration } from '../hooks/use-dms-configuration';

const previewable = new Set(['application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'text/plain']);

export function DocumentPreview({ document }: { readonly document: Document }) {
  const configuration = useDmsConfiguration();
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const mime = document.current_version?.mime_type ?? '';
  const allowed = previewable.has(mime);
  const load = useMutation({ mutationFn: () => dmsService.downloadDocument(document.id), onSuccess: (result) => { if (mime === 'text/plain') void result.blob.text().then((value) => setText(value.slice(0, configuration.data?.values.text_preview_max_characters))); else setUrl(URL.createObjectURL(result.blob)); } });
  const download = useMutation({ mutationFn: () => dmsService.downloadDocument(document.id), onSuccess: saveDownload });
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  if (configuration.isLoading) return <Card className="min-h-64 animate-pulse p-8" aria-label="Loading preview policy"/>;
  if (configuration.error) return <ApiProblem error={configuration.error} onRetry={() => void configuration.refetch()}/>;
  if (!configuration.data) return <ApiProblem error={new Error('DMS preview configuration is unavailable; content remains fail-closed.')}/>;
  if (!allowed) return <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center"><FileWarning className="h-10 w-10 text-muted-foreground"/><h2 className="mt-4 font-semibold">Preview unavailable for this file type</h2><p className="mt-2 text-sm text-muted-foreground">For safety, {mime || 'this format'} is download-only. Its bytes are never embedded into the page.</p><Button className="mt-4" variant="outline" disabled={download.isPending} onClick={() => download.mutate()}><Download className="mr-2 h-4 w-4"/>Download safely</Button>{download.error ? <div className="mt-4"><MutationProblem error={download.error}/></div> : null}</Card>;
  if (load.error) return <MutationProblem error={load.error}/>;
  if (!url && text === null) return <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center"><Eye className="h-10 w-10 text-primary"/><h2 className="mt-4 font-semibold">Safe preview available</h2><p className="mt-2 text-sm text-muted-foreground">Content is fetched only when requested and remains protected by the document download policy.</p><Button className="mt-4" disabled={load.isPending} onClick={() => load.mutate()}>{load.isPending ? 'Loading preview…' : 'Load preview'}</Button></Card>;
  if (text !== null) return <Card className="max-h-[520px] overflow-auto p-5"><pre className="whitespace-pre-wrap break-words text-sm">{text}</pre></Card>;
  return mime.startsWith('image/') ? <Card className="flex max-h-[620px] justify-center overflow-auto p-4"><img src={url ?? ''} alt={`Preview of ${document.name}`} className="max-h-[580px] object-contain"/></Card> : <Card className="h-[620px] overflow-hidden"><object data={url ?? ''} type="application/pdf" className="h-full w-full"><p className="p-5">Your browser cannot show this PDF preview.</p></object></Card>;
}
