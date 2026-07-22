import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import type { ComplianceEvidence, ComplianceResult } from '../contracts';
import { ROUTE_PATHS } from '../contracts';
import { ApiProblem, Breadcrumbs, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { MutationForm, formOptional, formString, parseJsonObject } from '../components/ResourcePages';
import { useTraceabilityCapabilities } from '../hooks/use-traceability-configuration';
import { BlockchainTraceabilityApiError, blockchainTraceabilityService } from '../services/blockchain_traceability-service';

const FIELDS = [
  { name: 'superseded_id', label: 'Finalized evidence ID to supersede', required: true, help: 'The server verifies tenant ownership and that the source evidence is finalized.' },
  { name: 'asset_id', label: 'Asset ID', required: true },
  { name: 'event_id', label: 'Related event ID' },
  { name: 'evidence_key', label: 'New evidence key', required: true },
  { name: 'evidence_type', label: 'Evidence type', required: true },
  { name: 'standard', label: 'Standard', required: true },
  { name: 'jurisdiction', label: 'Jurisdiction' },
  { name: 'result', label: 'Result (pass, fail, warning, not_applicable)', required: true },
  { name: 'document_ref', label: 'Document reference UUID' },
  { name: 'observed_at', label: 'Observed at', type: 'datetime-local' as const, required: true },
  { name: 'valid_until', label: 'Valid until', type: 'datetime-local' as const },
  { name: 'details', label: 'Correction details (JSON)', type: 'json' as const, required: true, defaultValue: '{}' },
] as const;

function result(value: string): ComplianceResult {
  if (value === 'pass' || value === 'fail' || value === 'warning' || value === 'not_applicable') return value;
  throw new Error('Result must be pass, fail, warning, or not_applicable.');
}

export function SupersedeComplianceEvidencePage() {
  const navigate = useNavigate();
  const capabilities = useTraceabilityCapabilities();
  const [created, setCreated] = useState<ComplianceEvidence | null>(null);
  if (capabilities.isLoading) return <PageSkeleton label="Loading supersession policy" />;
  if (capabilities.error || !capabilities.data) return <main className="p-4 sm:p-8"><ApiProblem error={capabilities.error} onRetry={() => { void capabilities.refetch(); }} /></main>;
  if (!capabilities.data.can_mutate_resources) return <main className="p-4 sm:p-8"><ApiProblem error={new BlockchainTraceabilityApiError('The governed capability response does not permit compliance supersession.', 403, 'permission_denied', {}, null)} /></main>;
  if (!capabilities.data.document.features.enabled || !capabilities.data.document.features.enable_supersede) return <main className="p-4 sm:p-8"><PageHeader title="Supersession disabled" description="The active tenant feature policy has disabled compliance supersession." /><Card className="p-6"><p className="text-sm text-muted-foreground">An administrator can review the rollout policy in traceability configuration. No mutation was attempted.</p></Card></main>;
  if (created) return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Superseding evidence created" description="The correction was appended without rewriting or deleting the original evidence." /><Card className="p-6" aria-live="polite"><p className="text-sm">Created <strong>{created.evidence_key}</strong> with status {created.status}.</p><Button className="mt-4" onClick={() => navigate(ROUTE_PATHS.COMPLIANCE_DETAIL(created.id))}>Review superseding evidence</Button></Card></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Supersede compliance evidence" description="Create an append-only correction linked to finalized evidence. The original record remains immutable." breadcrumbs={<Breadcrumbs items={[{ label: 'Compliance', to: ROUTE_PATHS.COMPLIANCE }, { label: 'Supersede evidence' }]} />} /><MutationForm fields={FIELDS} submitLabel="Create superseding evidence" caution="Supersession is auditable and cannot erase the prior evidence. Review every identifier and correction detail before continuing." onCancel={() => navigate(ROUTE_PATHS.COMPLIANCE)} onSubmit={async (data) => {
    const supersededId = formString(data, 'superseded_id');
    setCreated(await blockchainTraceabilityService.supersedeComplianceEvidence(supersededId, {
      transition_key: `supersede:${crypto.randomUUID()}`,
      asset_id: formString(data, 'asset_id'),
      event_id: formOptional(data, 'event_id'),
      evidence_key: formString(data, 'evidence_key'),
      evidence_type: formString(data, 'evidence_type'),
      standard: formString(data, 'standard'),
      jurisdiction: formOptional(data, 'jurisdiction'),
      result: result(formString(data, 'result')),
      document_ref: formOptional(data, 'document_ref'),
      observed_at: new Date(formString(data, 'observed_at')).toISOString(),
      valid_until: formOptional(data, 'valid_until') ? new Date(formString(data, 'valid_until')).toISOString() : null,
      details: parseJsonObject(data, 'details'),
      supersedes_id: supersededId,
    }));
  }} /></main>;
}
