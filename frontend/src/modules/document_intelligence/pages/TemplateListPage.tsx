import { useQuery } from '@tanstack/react-query';
import { LayoutTemplate, Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { ApiProblem, EmptyPanel, PageHeader, PageSkeleton, Pagination, StatusPill } from '../components/ModuleShell';
import { formatConfidence, useCanManageDocumentIntelligence } from '../components/module-utils';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import { parseTemplateStatus, type ExtractionTemplateListItem } from '../contracts';
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';

function TemplateCards({ templates, open }: { templates: readonly ExtractionTemplateListItem[]; open: (id: string) => void }) {
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{templates.map((template) => <Card key={template.id} className="flex flex-col p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{template.name}</h2><p className="mt-1 text-xs text-muted-foreground">Revision {template.version} · {template.engine}</p></div><StatusPill status={template.status} /></div><p className="mt-4 line-clamp-3 flex-1 text-sm text-muted-foreground">{template.description || 'No description supplied.'}</p><div className="mt-5 flex items-center justify-between text-sm"><span>Match ≥ {formatConfidence(template.match_threshold)}</span><Button variant="outline" size="sm" onClick={() => open(template.id)}>Open template</Button></div></Card>)}</div>;
}

export function TemplateListPage() {
  const navigate = useNavigate();
  const canManage = useCanManageDocumentIntelligence();
  const configuration = useDocumentIntelligenceConfiguration();
  const [params, setParams] = useSearchParams();
  const page = Number(params.get('page') ?? '1');
  const status = parseTemplateStatus(params.get('status'));
  const category = params.get('category') ?? undefined;
  const query = useQuery({ queryKey: ['document-intelligence', 'templates', page, status, category], queryFn: () => documentIntelligenceService.listTemplates({ page, page_size: configuration.data?.document.ui.page_size, status, document_category: category, ordering: 'name' }), enabled: Boolean(configuration.data) });
  if (query.isLoading || configuration.isLoading) return <PageSkeleton table={false} />;
  if (query.error || configuration.error || !query.data || !configuration.data) return <div className="p-4 sm:p-8"><ApiProblem error={query.error ?? configuration.error} onRetry={() => { void query.refetch(); void configuration.refetch(); }} /></div>;
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value === 'all' || !value) next.delete(key); else next.set(key, value); if (key !== 'page') next.set('page', '1'); setParams(next); };
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Extraction templates" description="Provider-neutral, versioned layouts with normalized zones and immediate geometric validation." actions={canManage ? <Button onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.CREATE)}><Plus className="mr-2 h-4 w-4" />New template</Button> : undefined} /><Card className="p-4"><div className="grid gap-3 sm:grid-cols-2"><Select value={status ?? 'all'} onValueChange={(value) => update('status', value)}><SelectTrigger aria-label="Template status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{['draft', 'active', 'inactive', 'retired'].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select><Input aria-label="Document category" placeholder="Category slug" value={category ?? ''} onChange={(event) => update('category', event.target.value)} /></div></Card>{query.data.items.length === 0 ? <EmptyPanel title="No extraction templates" description="Create a draft layout and define normalized fields without leaking provider-specific schemas." action={canManage ? <Button onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.CREATE)}><LayoutTemplate className="mr-2 h-4 w-4" />Create template</Button> : undefined} /> : <><TemplateCards templates={query.data.items} open={(id) => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.DETAIL(id))} /><Card><Pagination value={query.data.pagination} onPage={(next) => update('page', String(next))} /></Card></>}</main>;
}
