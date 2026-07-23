/* eslint-disable max-lines-per-function -- the configuration editor intentionally exposes the complete tenant document. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, History, RotateCcw, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import {
  isEmailMarketingConfigurationDocument,
  type EmailMarketingConfigurationDocument,
} from '../contracts';
import {
  GovernedError,
  Page,
  PageSkeleton,
  Surface,
  formatDate,
  useUnsavedChanges,
} from '../components/EmailMarketingUI';
import {
  EMAIL_MARKETING_QUERY_KEYS,
  emailMarketingService,
} from '../services/email-marketing-service';

const inputClass = 'mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
const split = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean);
const stringify = (value: unknown) => JSON.stringify(value, null, 2);

function NumberField({ label, description, value, min = 0, max, step = 1, onChange }: {
  readonly label: string;
  readonly description: string;
  readonly value: number;
  readonly min?: number;
  readonly max?: number;
  readonly step?: number;
  readonly onChange: (value: number) => void;
}) {
  return <label className="text-sm font-medium" title={description}>{label}<input className={inputClass} type="number" min={min} max={max} step={step} required value={value} onChange={(event) => onChange(event.target.valueAsNumber)}/><span className="mt-1 block text-xs font-normal text-muted-foreground">{description}</span></label>;
}

function TextField({ label, description, value, onChange }: {
  readonly label: string;
  readonly description: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
}) {
  return <label className="text-sm font-medium" title={description}>{label}<input className={inputClass} required value={value} onChange={(event) => onChange(event.target.value)}/><span className="mt-1 block text-xs font-normal text-muted-foreground">{description}</span></label>;
}

function CsvField({ label, description, value, onChange }: {
  readonly label: string;
  readonly description: string;
  readonly value: readonly string[];
  readonly onChange: (value: readonly string[]) => void;
}) {
  return <label className="text-sm font-medium" title={description}>{label}<input className={inputClass} required value={value.join(', ')} onChange={(event) => onChange(split(event.target.value))}/><span className="mt-1 block text-xs font-normal text-muted-foreground">{description}</span></label>;
}

function JsonField({ label, description, value, onChange }: {
  readonly label: string;
  readonly description: string;
  readonly value: unknown;
  readonly onChange: (value: unknown) => void;
}) {
  const [text, setText] = useState(() => stringify(value));
  const [error, setError] = useState('');
  useEffect(() => setText(stringify(value)), [value]);
  return <label className="block text-sm font-medium" title={description}>{label}<textarea className={`${inputClass} font-mono`} rows={8} spellCheck={false} value={text} onChange={(event) => {
    const next = event.target.value;
    setText(next);
    try {
      const parsed: unknown = JSON.parse(next);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setError('Enter a JSON object.');
        return;
      }
      setError('');
      onChange(parsed);
    } catch {
      setError('Enter valid JSON before previewing.');
    }
  }}/><span className="mt-1 block text-xs font-normal text-muted-foreground">{description}</span>{error ? <span role="alert" className="mt-1 block text-xs text-destructive">{error}</span> : null}</label>;
}

function downloadConfiguration(document: EmailMarketingConfigurationDocument, version: number): void {
  const blob = new Blob([stringify(document)], { type: 'application/json' });
  const href = URL.createObjectURL(blob);
  const anchor = window.document.createElement('a');
  anchor.href = href;
  anchor.download = `email-marketing-configuration-v${version}.json`;
  anchor.click();
  URL.revokeObjectURL(href);
}

export function EmailMarketingConfigurationPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const current = useQuery({
    queryKey: EMAIL_MARKETING_QUERY_KEYS.configuration,
    queryFn: () => emailMarketingService.configuration.current(),
  });
  const history = useQuery({
    queryKey: EMAIL_MARKETING_QUERY_KEYS.configurationHistory,
    queryFn: () => emailMarketingService.configuration.history(),
  });
  const [document, setDocument] = useState<EmailMarketingConfigurationDocument | null>(null);
  const [importMode, setImportMode] = useState(false);
  const [importError, setImportError] = useState('');
  const [previewedDocument, setPreviewedDocument] = useState<EmailMarketingConfigurationDocument | null>(null);
  useEffect(() => {
    if (current.data && document === null) setDocument(current.data.data.document);
  }, [current.data, document]);
  const baseline = current.data?.data.document;
  const dirty = document !== null && baseline !== undefined && stringify(document) !== stringify(baseline);
  useUnsavedChanges(dirty);

  const invalidate = async () => {
    setPreviewedDocument(null);
    setDocument(null);
    setImportMode(false);
    await queryClient.invalidateQueries({ queryKey: EMAIL_MARKETING_QUERY_KEYS.all });
  };
  const preview = useMutation({
    mutationFn: (value: EmailMarketingConfigurationDocument) => emailMarketingService.configuration.preview({ document: value }),
    onSuccess: (result) => {
      setDocument(result.data.normalized_document);
      setPreviewedDocument(result.data.normalized_document);
    },
  });
  const save = useMutation({
    mutationFn: (value: EmailMarketingConfigurationDocument) => {
      if (!current.data) throw new Error('Configuration version is unavailable.');
      const input = { document: value, expected_version: current.data.data.version };
      return importMode
        ? emailMarketingService.configuration.importDocument(input)
        : emailMarketingService.configuration.update(input);
    },
    onSuccess: invalidate,
  });
  const rollback = useMutation({
    mutationFn: (targetVersion: number) => {
      if (!current.data) throw new Error('Configuration version is unavailable.');
      return emailMarketingService.configuration.rollback({
        target_version: targetVersion,
        expected_version: current.data.data.version,
      });
    },
    onSuccess: invalidate,
  });
  const exportMutation = useMutation({
    mutationFn: () => emailMarketingService.configuration.exportDocument(),
    onSuccess: (result) => {
      downloadConfiguration(result.data.document, result.data.version);
    },
  });

  const canApply = useMemo(
    () => document !== null && previewedDocument !== null && stringify(document) === stringify(previewedDocument),
    [document, previewedDocument],
  );
  const change = (updater: (value: EmailMarketingConfigurationDocument) => EmailMarketingConfigurationDocument) => {
    setDocument((value) => value ? updater(value) : value);
    setPreviewedDocument(null);
  };

  if (current.isLoading) return <PageSkeleton label="Loading email marketing configuration"/>;
  if (current.error) return <Page title="Email marketing configuration" description="Tenant-scoped runtime policy and safe operational limits."><GovernedError error={current.error} retry={() => void current.refetch()}/></Page>;
  if (!current.data || !document) return <Page title="Email marketing configuration" description="Tenant-scoped runtime policy and safe operational limits."><GovernedError error={new Error('No governed configuration response was received.')} retry={() => void current.refetch()}/></Page>;

  const configuration = current.data.data;
  const limits = document.limits;
  const updateLimits = (key: keyof typeof limits, value: number) => change((currentDocument) => ({ ...currentDocument, limits: { ...currentDocument.limits, [key]: value } }));
  const pagination = document.pagination;
  const updatePagination = (key: 'default_page_size' | 'max_page_size', value: number) => change((currentDocument) => ({ ...currentDocument, pagination: { ...currentDocument.pagination, [key]: value } }));
  const resilience = document.resilience;
  const updateResilience = (key: keyof typeof resilience, value: number) => change((currentDocument) => ({ ...currentDocument, resilience: { ...currentDocument.resilience, [key]: value } }));
  const tokens = document.tokens;
  const updateTokens = (key: keyof typeof tokens, value: number) => change((currentDocument) => ({ ...currentDocument, tokens: { ...currentDocument.tokens, [key]: value } }));
  const health = document.health;
  const updateHealth = (key: keyof typeof health, value: number) => change((currentDocument) => ({ ...currentDocument, health: { ...currentDocument.health, [key]: value } }));
  const rateLimits = document.rate_limits;
  const updateRateLimit = (key: keyof typeof rateLimits, value: number) => change((currentDocument) => ({ ...currentDocument, rate_limits: { ...currentDocument.rate_limits, [key]: value } }));
  const quotas = document.quotas;
  const updateQuota = (key: keyof typeof quotas, value: number) => change((currentDocument) => ({ ...currentDocument, quotas: { ...currentDocument.quotas, [key]: value } }));

  return <Page title="Email marketing configuration" description="Versioned tenant policy. Every change is previewed, validated server-side, correlated, and reversible." actions={<>
    <Button variant="outline" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}><Download className="mr-2 h-4 w-4"/>Export</Button>
    <Button variant="outline" onClick={() => fileInput.current?.click()}><Upload className="mr-2 h-4 w-4"/>Import</Button>
    <input ref={fileInput} className="sr-only" type="file" accept="application/json,.json" onChange={(event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed: unknown = JSON.parse(String(reader.result));
          if (!isEmailMarketingConfigurationDocument(parsed)) throw new Error('The file is not a complete email marketing configuration document.');
          setDocument(parsed);
          setPreviewedDocument(null);
          setImportMode(true);
          setImportError('');
        } catch (error) {
          setImportError(error instanceof Error ? error.message : 'The configuration file is invalid.');
        }
      };
      reader.readAsText(file);
      event.target.value = '';
    }}/>
  </>}>
    <Surface title={`Environment ${configuration.environment} · version ${configuration.version}`} description={`Last updated ${formatDate(configuration.updated_at)} by ${configuration.updated_by ?? 'system'}. Changes apply without a frontend redeploy.`}>
      {importMode ? <p role="status" className="rounded-lg border border-primary/20 bg-primary/10 p-3 text-sm text-primary">Imported document staged. Preview the normalized diff before applying it.</p> : null}
      {importError ? <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{importError}</p> : null}
    </Surface>

    <Surface title="Defaults" description="New records inherit these values. Existing evidence is never rewritten."><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <NumberField label="Configuration schema version" description="Versioned configuration document contract." min={1} value={document.schema_version} onChange={(value) => change((currentDocument) => ({ ...currentDocument, schema_version: value }))}/>
      {([
        ['template_category', 'Template category', 'Default classification for new reusable templates.'],
        ['campaign_type', 'Campaign type', 'Default campaign workflow selected by authoring forms.'],
        ['audience_resolver', 'Audience resolver', 'Default resolver key embedded in new audience definitions.'],
        ['delivery_gateway', 'Delivery gateway', 'Configured gateway key; secrets are never stored here.'],
        ['timezone', 'Timezone', 'IANA timezone used by new campaign schedules.'],
        ['consent_purpose', 'Consent purpose', 'Default consent purpose checked before submission.'],
      ] as const).map(([key, label, description]) => <TextField key={key} label={label} description={description} value={document.defaults[key]} onChange={(value) => change((currentDocument) => ({ ...currentDocument, defaults: { ...currentDocument.defaults, [key]: value } }))}/>)}
      <NumberField label="Audience schema version" description="Version emitted into new audience definitions." min={1} value={document.defaults.audience_schema_version} onChange={(value) => change((currentDocument) => ({ ...currentDocument, defaults: { ...currentDocument.defaults, audience_schema_version: value } }))}/>
    </div></Surface>

    <Surface title="Pagination" description="List pages consume these values directly from this API."><div className="grid gap-4 md:grid-cols-3">
      <NumberField label="Default page size" description="Initial records per page; must be one of the allowed options." min={1} max={pagination.max_page_size} value={pagination.default_page_size} onChange={(value) => updatePagination('default_page_size', value)}/>
      <NumberField label="Maximum page size" description="Server-enforced tenant page ceiling." min={pagination.default_page_size} value={pagination.max_page_size} onChange={(value) => updatePagination('max_page_size', value)}/>
      <CsvField label="Page-size options" description="Allowed positive integer choices shown on list pages." value={pagination.page_size_options.map(String)} onChange={(value) => change((currentDocument) => ({ ...currentDocument, pagination: { ...currentDocument.pagination, page_size_options: value.map(Number).filter(Number.isInteger) } }))}/>
    </div></Surface>

    <Surface title="Safe data limits" description="The server applies stricter absolute ceilings; values beyond them are unsavable."><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {(Object.keys(limits) as (keyof typeof limits)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Tenant limit for ${key.replaceAll('_', ' ')}.`} min={1} value={limits[key]} onChange={(value) => updateLimits(key, value)}/>)}
    </div></Surface>

    <Surface title="Workflow allow-lists" description="Only configured values can be selected by authoring and compliance screens."><div className="grid gap-4 md:grid-cols-2">
      <CsvField label="Campaign types" description="Campaign types offered to authors." value={document.workflows.campaign_types} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, campaign_types: value } }))}/>
      <CsvField label="Audience resolvers" description="Resolver keys allowed in audience definitions." value={document.workflows.audience_resolver_keys} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, audience_resolver_keys: value } }))}/>
      <CsvField label="Editable campaign states" description="States in which campaign authoring is permitted." value={document.workflows.campaign_editable_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, campaign_editable_states: value as typeof currentDocument.workflows.campaign_editable_states } }))}/>
      <CsvField label="Editable template states" description="States in which reusable content may change." value={document.workflows.template_editable_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, template_editable_states: value as typeof currentDocument.workflows.template_editable_states } }))}/>
      <CsvField label="Archivable campaign states" description="States eligible for audited archive." value={document.workflows.campaign_archivable_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, campaign_archivable_states: value as typeof currentDocument.workflows.campaign_archivable_states } }))}/>
      <CsvField label="Physical-delete protected campaign states" description="Evidence states that can never be physically deleted; mandatory terminal protections are server-enforced." value={document.workflows.campaign_physical_delete_protected_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, campaign_physical_delete_protected_states: value as typeof currentDocument.workflows.campaign_physical_delete_protected_states } }))}/>
      <CsvField label="Archive-blocking recipient states" description="Recipient states that prevent campaign archive." value={document.workflows.campaign_archive_blocking_recipient_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, campaign_archive_blocking_recipient_states: value as typeof currentDocument.workflows.campaign_archive_blocking_recipient_states } }))}/>
      <CsvField label="Initial recipient states" description="Only these states may be assigned during audience resolution." value={document.workflows.recipient_initial_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, recipient_initial_states: value as typeof currentDocument.workflows.recipient_initial_states } }))}/>
      <CsvField label="Terminal recipient states" description="States protected from lifecycle regression." value={document.workflows.terminal_recipient_states} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, terminal_recipient_states: value as typeof currentDocument.workflows.terminal_recipient_states } }))}/>
      <CsvField label="Preflight blocking codes" description="Preflight failures that block scheduling." value={document.workflows.preflight_blocking_codes} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, preflight_blocking_codes: value } }))}/>
      <CsvField label="Audience schema versions" description="Accepted versioned audience contracts." value={document.workflows.audience_schema_versions.map(String)} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, audience_schema_versions: value.map(Number).filter(Number.isInteger) } }))}/>
    </div><div className="mt-5 grid gap-4 xl:grid-cols-2">
      <JsonField label="Provider acknowledgement mapping" description="Exhaustive provider acknowledgement-to-recipient state contract." value={document.workflows.provider_acknowledgement_mapping} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, provider_acknowledgement_mapping: value as typeof currentDocument.workflows.provider_acknowledgement_mapping } }))}/>
      <JsonField label="Provider event mapping" description="Verified event-to-recipient state contract." value={document.workflows.provider_event_recipient_mapping} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, provider_event_recipient_mapping: value as typeof currentDocument.workflows.provider_event_recipient_mapping } }))}/>
      <JsonField label="Provider event command mapping" description="Verified provider events mapped to controlled lifecycle commands." value={document.workflows.provider_event_command_mapping} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, provider_event_command_mapping: value as typeof currentDocument.workflows.provider_event_command_mapping } }))}/>
      <JsonField label="Transition graphs" description="Versioned campaign, template, and recipient transitions. Core non-regression guards remain immutable." value={document.workflows.transitions} onChange={(value) => change((currentDocument) => ({ ...currentDocument, workflows: { ...currentDocument.workflows, transitions: value as typeof currentDocument.workflows.transitions } }))}/>
    </div></Surface>

    <Surface title="Compliance policy" description="Legal guardrails remain server-enforced even when tenant policy changes."><div className="grid gap-4 md:grid-cols-2">
      <CsvField label="Suppression scopes" description="Scopes available to operators." value={document.compliance.suppression_scopes} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, suppression_scopes: value as typeof currentDocument.compliance.suppression_scopes } }))}/>
      <CsvField label="Suppression reasons" description="Allow-listed compliance reasons." value={document.compliance.suppression_reasons} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, suppression_reasons: value as typeof currentDocument.compliance.suppression_reasons } }))}/>
      <CsvField label="Suppression sources" description="Allow-listed evidence sources." value={document.compliance.suppression_sources} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, suppression_sources: value as typeof currentDocument.compliance.suppression_sources } }))}/>
      <CsvField label="Permanent reasons" description="Reasons for which the expiry control is disabled." value={document.compliance.permanent_suppression_reasons} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, permanent_suppression_reasons: value as typeof currentDocument.compliance.permanent_suppression_reasons } }))}/>
      <CsvField label="Protected overwrite reasons" description="Provider-enforced reasons that operators cannot silently replace." value={document.compliance.protected_overwrite_reasons} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, protected_overwrite_reasons: value as typeof currentDocument.compliance.protected_overwrite_reasons } }))}/>
      <CsvField label="Automatic suppression events" description="Verified events that append suppression evidence." value={document.compliance.automatic_suppression_events} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, automatic_suppression_events: value as typeof currentDocument.compliance.automatic_suppression_events } }))}/>
      <JsonField label="Automatic suppression reasons" description="Verified provider events mapped to configured suppression reasons." value={document.compliance.automatic_suppression_reasons} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, automatic_suppression_reasons: value as typeof currentDocument.compliance.automatic_suppression_reasons } }))}/>
      <CsvField label="Consent sources" description="Allow-listed sources accepted when recording consent evidence." value={document.compliance.consent_sources} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, consent_sources: value as typeof currentDocument.compliance.consent_sources } }))}/>
      <CsvField label="Consent lawful bases" description="Allow-listed lawful bases accepted for consent evidence." value={document.compliance.consent_lawful_bases} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, consent_lawful_bases: value as typeof currentDocument.compliance.consent_lawful_bases } }))}/>
      <TextField label="Required consent status" description="Latest consent state required for eligibility." value={document.compliance.consent_required_status} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, consent_required_status: value as typeof currentDocument.compliance.consent_required_status } }))}/>
      <JsonField label="Scopes by consent purpose" description="Suppression scopes evaluated for each consent purpose." value={document.compliance.suppression_scopes_by_purpose} onChange={(value) => change((currentDocument) => ({ ...currentDocument, compliance: { ...currentDocument.compliance, suppression_scopes_by_purpose: value as typeof currentDocument.compliance.suppression_scopes_by_purpose } }))}/>
    </div></Surface>

    <Surface title="Delivery resilience" description="Bounded retries apply only where submission is provably retry-safe."><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {(Object.keys(resilience) as (keyof typeof resilience)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Runtime resilience control for ${key.replaceAll('_', ' ')}.`} min={key.includes('jitter') || key.includes('delay') ? 0 : 1} step={key.includes('delay') || key.includes('jitter') ? 0.01 : 1} value={resilience[key]} onChange={(value) => updateResilience(key, value)}/>)}
    </div></Surface>

    <Surface title="Tokens, health, rate limits, and quotas"><div className="grid gap-6 xl:grid-cols-4"><div className="grid gap-4">
      {(Object.keys(tokens) as (keyof typeof tokens)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Bounded token validity for ${key.replaceAll('_', ' ')}.`} min={1} value={tokens[key]} onChange={(value) => updateTokens(key, value)}/>)}
    </div><div className="grid gap-4">
      {(Object.keys(health) as (keyof typeof health)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Health threshold for ${key.replaceAll('_', ' ')}.`} min={1} value={health[key]} onChange={(value) => updateHealth(key, value)}/>)}
    </div><div className="grid gap-4">
      {(Object.keys(rateLimits) as (keyof typeof rateLimits)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Public endpoint rate limit for ${key.replaceAll('_', ' ')}.`} min={1} max={300} value={rateLimits[key]} onChange={(value) => updateRateLimit(key, value)}/>)}
    </div><div className="grid gap-4">
      {(Object.keys(quotas) as (keyof typeof quotas)[]).map((key) => <NumberField key={key} label={key.replaceAll('_', ' ')} description={`Tenant quota for ${key.replaceAll('_', ' ')}.`} min={1} value={quotas[key]} onChange={(value) => updateQuota(key, value)}/>)}
    </div></div></Surface>

    <Surface title="Integrations and filters" description="Gateway secrets stay in the secret manager; this document contains allow-listed identifiers only."><div className="grid gap-4 md:grid-cols-2">
      <CsvField label="Allowed delivery backends" description="Production-capable backends allowed by policy." value={document.integrations.allowed_delivery_backends} onChange={(value) => change((currentDocument) => ({ ...currentDocument, integrations: { ...currentDocument.integrations, allowed_delivery_backends: value } }))}/>
      <CsvField label="Simulated delivery backends" description="Non-production backends explicitly allowed by policy." value={document.integrations.simulated_delivery_backends} onChange={(value) => change((currentDocument) => ({ ...currentDocument, integrations: { ...currentDocument.integrations, simulated_delivery_backends: value } }))}/>
      <CsvField label="Gateway keys" description="Gateway identifiers available to campaigns." value={document.integrations.gateway_keys} onChange={(value) => change((currentDocument) => ({ ...currentDocument, integrations: { ...currentDocument.integrations, gateway_keys: value } }))}/>
      <JsonField label="Default ordering by resource" description="Default list ordering applied by the API." value={document.filters.default_ordering_by_resource} onChange={(value) => change((currentDocument) => ({ ...currentDocument, filters: { ...currentDocument.filters, default_ordering_by_resource: value as typeof currentDocument.filters.default_ordering_by_resource } }))}/>
      <JsonField label="Search fields by resource" description="Truthful allow-list of fields searched by each collection." value={document.filters.search_fields_by_resource} onChange={(value) => change((currentDocument) => ({ ...currentDocument, filters: { ...currentDocument.filters, search_fields_by_resource: value as typeof currentDocument.filters.search_fields_by_resource } }))}/>
    </div></Surface>

    <Surface title="Feature rollout and display semantics"><div className="grid gap-4 md:grid-cols-2">
      <label className="flex items-center gap-3 rounded-lg border p-3 text-sm font-medium"><input type="checkbox" checked={document.feature_flags.enabled} onChange={(event) => change((currentDocument) => ({ ...currentDocument, feature_flags: { ...currentDocument.feature_flags, enabled: event.target.checked } }))}/>Module capability enabled</label>
      <NumberField label="Rollout percentage" description="Tenant cohort rollout from 0 to 100 percent." min={0} max={100} value={document.feature_flags.rollout_percentage} onChange={(value) => change((currentDocument) => ({ ...currentDocument, feature_flags: { ...currentDocument.feature_flags, rollout_percentage: value } }))}/>
      <CsvField label="Allowed roles" description="Empty means server RBAC permissions alone determine access." value={document.feature_flags.roles} onChange={(value) => change((currentDocument) => ({ ...currentDocument, feature_flags: { ...currentDocument.feature_flags, roles: value } }))}/>
      <CsvField label="Cohorts" description="Optional tenant cohort identifiers for phased rollout." value={document.feature_flags.cohorts} onChange={(value) => change((currentDocument) => ({ ...currentDocument, feature_flags: { ...currentDocument.feature_flags, cohorts: value } }))}/>
      <JsonField label="Status semantics" description="Maps statuses to semantic success, error, warning, or neutral design tokens." value={document.display.status_semantics} onChange={(value) => change((currentDocument) => ({ ...currentDocument, display: { status_semantics: value as typeof currentDocument.display.status_semantics } }))}/>
    </div></Surface>

    {preview.error || save.error || rollback.error || exportMutation.error ? <GovernedError error={preview.error ?? save.error ?? rollback.error ?? exportMutation.error}/> : null}
    {preview.data ? <Surface title="Server preview" description="This normalized diff is the exact document that can be applied.">
      {preview.data.data.warnings.length ? <ul className="mb-4 list-disc pl-5 text-sm text-muted-foreground">{preview.data.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
      {preview.data.data.changes.length ? <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead><tr className="border-b text-left"><th className="p-2">Path</th><th className="p-2">Before</th><th className="p-2">After</th></tr></thead><tbody>{preview.data.data.changes.map((item) => <tr className="border-b" key={item.path}><td className="p-2 font-mono">{item.path}</td><td className="p-2 font-mono text-xs">{stringify(item.before)}</td><td className="p-2 font-mono text-xs">{stringify(item.after)}</td></tr>)}</tbody></table></div> : <p className="text-sm text-muted-foreground">No effective changes.</p>}
    </Surface> : null}
    <div className="sticky bottom-4 flex flex-wrap justify-end gap-2 rounded-xl border bg-card/95 p-4 shadow-lg backdrop-blur">
      <Button variant="outline" disabled={!dirty || preview.isPending} onClick={() => document && preview.mutate(document)}>{preview.isPending ? 'Validating…' : 'Preview server diff'}</Button>
      <Button disabled={!dirty || !canApply || save.isPending} onClick={() => document && save.mutate(document)}>{save.isPending ? 'Applying…' : importMode ? 'Import reviewed document' : 'Apply reviewed configuration'}</Button>
    </div>

    <Surface title="Immutable version history" description="Every entry records actor, correlation, prior value, new value, and rollback ancestry.">
      {history.isLoading ? <p role="status" className="text-sm text-muted-foreground">Loading version history…</p> : history.error ? <GovernedError error={history.error} retry={() => void history.refetch()}/> : history.data?.data.length ? <ol className="space-y-3">{history.data.data.map((version) => <li key={version.id} className="rounded-lg border p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><strong>Version {version.version} · {version.change_type}</strong><p className="text-xs text-muted-foreground">{formatDate(version.created_at)} · actor {version.actor_id ?? 'system'}</p><p className="font-mono text-xs">correlation {version.correlation_id}{version.rollback_source_version ? ` · rollback of v${version.rollback_source_version}` : ''}</p></div><Button variant="outline" disabled={version.version === configuration.version || rollback.isPending} onClick={() => {
        if (window.confirm(`Rollback current configuration to version ${version.version}? A new immutable version will be appended.`)) rollback.mutate(version.version);
      }}><RotateCcw className="mr-2 h-4 w-4"/>Rollback to v{version.version}</Button></div><details className="mt-3"><summary className="cursor-pointer text-sm text-primary"><History className="mr-1 inline h-4 w-4"/>View version document</summary><pre className="mt-2 max-h-96 overflow-auto rounded bg-muted p-3 text-xs">{stringify(version.document)}</pre></details></li>)}</ol> : <p className="text-sm text-muted-foreground">No immutable version records were returned.</p>}
    </Surface>
  </Page>;
}
