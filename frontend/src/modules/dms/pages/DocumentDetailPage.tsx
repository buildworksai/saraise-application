import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Download, Pencil, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DocumentPreview } from '../components/DocumentPreview';
import { PermissionPanel } from '../components/PermissionPanel';
import { SharePanel } from '../components/SharePanel';
import { VersionTimeline } from '../components/VersionTimeline';
import { ApiProblem, PageHeader, PageSkeleton, can, formatBytes, formatDate, saveDownload } from '../components/DmsUI';
import { ROUTES, type Document } from '../contracts';
import { DMS_QUERY_KEYS, dmsService } from '../services/dms-service';

type DetailTab = 'overview' | 'versions' | 'access' | 'shares';
const tabs: readonly { readonly id: DetailTab; readonly label: string }[] = [{ id: 'overview', label: 'Overview' }, { id: 'versions', label: 'Versions' }, { id: 'access', label: 'Access' }, { id: 'shares', label: 'Shares' }];

// eslint-disable-next-line complexity
export function DocumentDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [tab, setTab] = useState<DetailTab>('overview');
  const query = useQuery({ queryKey: DMS_QUERY_KEYS.document(id), queryFn: () => dmsService.getDocument(id), enabled: Boolean(id) });
  const download = useMutation({ mutationFn: () => dmsService.downloadDocument(id), onSuccess: saveDownload });
  const remove = useMutation({ mutationFn: () => dmsService.deleteDocument(id), onSuccess: () => { void client.invalidateQueries({ queryKey: DMS_QUERY_KEYS.root }); toast.success('Document moved to retention'); navigate(ROUTES.DOCUMENTS); } });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <main className="p-4 sm:p-8"><ApiProblem error={query.error} onRetry={() => void query.refetch()}/></main>;
  if (!query.data) return <main className="p-4 sm:p-8"><ApiProblem error={new Error('Document response was empty.')}/></main>;
  const document = query.data;
  const actions = document.allowed_actions;
  const canWrite = can(actions, 'write');
  const canManage = can(actions, 'manage');
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={document.name} description={`${document.folder_name ?? 'Documents'} · ${document.version_count} immutable version${document.version_count === 1 ? '' : 's'}`} actions={<>{can(actions, 'download') || can(actions, 'read') ? <Button variant="outline" disabled={download.isPending} onClick={() => download.mutate()}><Download className="mr-2 h-4 w-4"/>Download</Button> : null}{canWrite ? <Button variant="outline" onClick={() => setTab('versions')}><Upload className="mr-2 h-4 w-4"/>New version</Button> : null}{canWrite ? <Button onClick={() => navigate(ROUTES.DOCUMENT_EDIT(document.id))}><Pencil className="mr-2 h-4 w-4"/>Edit metadata</Button> : null}{can(actions, 'delete') || canManage ? <Button variant="danger" disabled={remove.isPending} onClick={() => { if (window.confirm('Soft-delete this document and revoke its active shares? Immutable versions remain retained.')) remove.mutate(); }}><Trash2 className="mr-2 h-4 w-4"/>Delete</Button> : null}</>}/>{download.error || remove.error ? <ApiProblem error={download.error ?? remove.error ?? new Error('Document operation failed')}/> : null}<nav role="tablist" aria-label="Document details" className="flex overflow-x-auto border-b">{tabs.map((item) => <button role="tab" aria-selected={tab === item.id} key={item.id} className={`border-b-2 px-4 py-3 text-sm font-medium ${tab === item.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`} onClick={() => setTab(item.id)}>{item.label}</button>)}</nav>{tab === 'overview' ? <Overview document={document}/> : null}{tab === 'versions' ? <VersionTimeline documentId={document.id} canCreate={canWrite} canRestore={canWrite} canDownload={can(actions, 'download') || can(actions, 'read')}/> : null}{tab === 'access' ? <PermissionPanel documentId={document.id} canManage={canManage}/> : null}{tab === 'shares' ? <SharePanel documentId={document.id} canShare={canManage || can(actions, 'share')}/> : null}</main>;
}

function Overview({ document }: { readonly document: Document }) {
  return <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]"><DocumentPreview document={document}/><div className="space-y-5"><Card className="p-5"><h2 className="font-semibold">Current version</h2><dl className="mt-4 grid gap-4 sm:grid-cols-2"><Detail label="Version">{document.current_version ? `v${document.current_version.version_number}` : '—'}</Detail><Detail label="File type">{document.current_version?.mime_type ?? '—'}</Detail><Detail label="Size">{formatBytes(document.current_version?.size_bytes)}</Detail><Detail label="Original filename">{document.current_version?.original_filename ?? '—'}</Detail><Detail label="SHA-256"><span className="break-all font-mono text-xs">{document.current_version?.checksum_sha256 ?? '—'}</span></Detail><Detail label="Owner"><span className="font-mono text-xs">{document.created_by}</span></Detail><Detail label="Created">{formatDate(document.created_at)}</Detail><Detail label="Updated">{formatDate(document.updated_at)}</Detail></dl></Card><Card className="p-5"><h2 className="font-semibold">Description and tags</h2><p className="mt-3 text-sm text-muted-foreground">{document.description || 'No description provided.'}</p><div className="mt-4 flex flex-wrap gap-2">{document.tags.length ? document.tags.map((tag) => <span key={tag} className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">{tag}</span>) : <span className="text-sm text-muted-foreground">No tags</span>}</div></Card><Card className="p-5"><h2 className="font-semibold">Metadata</h2>{Object.keys(document.metadata).length ? <dl className="mt-4 grid gap-3 sm:grid-cols-2">{Object.entries(document.metadata).map(([key, value]) => <Detail key={key} label={key}>{value === null ? '—' : String(value)}</Detail>)}</dl> : <p className="mt-3 text-sm text-muted-foreground">No searchable metadata.</p>}</Card></div></div>;
}

function Detail({ label, children }: { readonly label: string; readonly children: ReactNode }) { return <div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
