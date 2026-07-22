import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, Copy } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TemplateForm, type TemplateFormValue } from '../components/TemplateForm';
import { ApiProblem, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import type { ExtractionTemplateZone, ExtractionTemplateZoneInput } from '../contracts';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';

function zoneInput(zone: ExtractionTemplateZone): ExtractionTemplateZoneInput {
  return { zone_name: zone.zone_name, extraction_key: zone.extraction_key, zone_type: zone.zone_type, x: zone.x, y: zone.y, width: zone.width, height: zone.height, page_number: zone.page_number, expected_data_type: zone.expected_data_type, is_required: zone.is_required };
}

async function saveZones(templateId: string, existing: readonly ExtractionTemplateZone[], next: readonly ExtractionTemplateZoneInput[]): Promise<void> {
  await Promise.all(next.map((zone, index) => {
    const current = existing[index];
    return current
      ? documentIntelligenceService.updateTemplateZone(current.id, zone)
      : documentIntelligenceService.createTemplateZone({ ...zone, template_id: templateId });
  }));
  await Promise.all(existing.slice(next.length).map((zone) => documentIntelligenceService.deleteTemplateZone(zone.id)));
}

// The editor coordinates immutable revision loading, configured defaults, and normalized zone validation.
// eslint-disable-next-line complexity
export function EditTemplatePage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const configuration = useDocumentIntelligenceConfiguration();
  const template = useQuery({ queryKey: ['document-intelligence', 'template', id], queryFn: () => documentIntelligenceService.getTemplate(id), enabled: Boolean(id) });
  const zones = useQuery({ queryKey: ['document-intelligence', 'template-zones', id], queryFn: () => documentIntelligenceService.listTemplateZones(id, configuration.data?.document.ui.template_zone_page_size ?? 0), enabled: Boolean(id) && Boolean(configuration.data) });
  const save = useMutation({ mutationFn: async (value: TemplateFormValue) => { const existing = zones.data?.items ?? []; await documentIntelligenceService.updateTemplate(id, { name: value.name, description: value.description, document_category: value.document_category, engine: value.engine, match_threshold: value.match_threshold }); await saveZones(id, existing, value.zones); }, onSuccess: () => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.DETAIL(id)) });
  const clone = useMutation({ mutationFn: () => documentIntelligenceService.cloneTemplate(id, { name: `${template.data?.name ?? 'Template'} revision ${(template.data?.version ?? 0) + 1}` }), onSuccess: (created) => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.EDIT(created.id)) });
  if (template.isLoading || zones.isLoading || configuration.isLoading) return <PageSkeleton table={false} />;
  if (template.error || zones.error || configuration.error || !template.data || !zones.data || !configuration.data) return <div className="p-4 sm:p-8"><ApiProblem error={template.error ?? zones.error ?? configuration.error} onRetry={() => { void template.refetch(); void zones.refetch(); void configuration.refetch(); }} /></div>;
  if (template.data.status === 'active' || template.data.status === 'retired') return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Immutable template revision" description="Active and retired revisions cannot be edited. Clone the revision to continue safely." actions={<Button variant="ghost" onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.DETAIL(id))}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>} />{clone.error && <ApiProblem error={clone.error} onRetry={() => clone.reset()} inline />}<Card className="p-8 text-center"><h2 className="text-lg font-semibold">Preserve production evidence</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">A cloned draft keeps the activated layout immutable while giving you a complete editable copy.</p><Button className="mt-5" disabled={clone.isPending} onClick={() => clone.mutate()}><Copy className="mr-2 h-4 w-4" />{clone.isPending ? 'Cloning…' : 'Clone draft revision'}</Button></Card></main>;
  const initial: TemplateFormValue = { name: template.data.name, description: template.data.description, document_category: template.data.document_category, engine: template.data.engine, match_threshold: template.data.match_threshold, zones: zones.data.items.map(zoneInput) };
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${template.data.name}`} description="Changes remain draft or inactive until explicit activation validates the layout." actions={<Button variant="ghost" onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TEMPLATES.DETAIL(id))}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>} />{save.error && <ApiProblem error={save.error} onRetry={() => save.reset()} inline />}<Card className="p-6"><TemplateForm initial={initial} configuration={configuration.data.document} pending={save.isPending} submitLabel="Save template" onSubmit={(value) => save.mutateAsync(value)} /></Card></main>;
}
