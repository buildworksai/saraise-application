import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import type {
  AgentManagementConfigurationDocument,
  ConfigurationEnvironment,
  ConfigurationExportDocument,
} from "../contracts";
import { aiAgentService } from "../services/ai-agent-service";
import { GovernedError, MutationError, PageHeader, PageSkeleton, formatDate } from "../components/AgentUI";

function clone(value: AgentManagementConfigurationDocument): AgentManagementConfigurationDocument {
  return JSON.parse(JSON.stringify(value)) as AgentManagementConfigurationDocument;
}

function validate(document: AgentManagementConfigurationDocument): string | null {
  if (document.provider.max_tokens < 1 || document.provider.max_tokens > 1_000_000) return "Provider token limit must be between 1 and 1,000,000.";
  if (document.provider.temperature < 0 || document.provider.temperature > 2) return "Temperature must be between 0 and 2.";
  if (document.schedule.priority_minimum > document.schedule.default_priority || document.schedule.default_priority > document.schedule.priority_maximum) return "Default priority must be inside the configured priority range.";
  if (document.schedule.dispatch_batch_minimum > document.schedule.dispatch_batch_maximum) return "Dispatch minimum cannot exceed its maximum.";
  if (document.ui.saturation_warning_threshold > document.ui.saturation_critical_threshold) return "Warning saturation cannot exceed critical saturation.";
  if (!document.runner.allowed_roles.length || !document.runner.allowed_task_fields.length) return "Runner allow-lists cannot be empty.";
  return null;
}

export function ConfigurationPage() {
  const client = useQueryClient();
  const [environment, setEnvironment] = useState<ConfigurationEnvironment>("production");
  const current = useQuery({ queryKey: ["ai-agent-management", "configuration", environment], queryFn: () => aiAgentService.getConfiguration(environment) });
  const versions = useQuery({ queryKey: ["ai-agent-management", "configuration-versions", environment], queryFn: () => aiAgentService.listConfigurationVersions(environment) });
  const [draft, setDraft] = useState<AgentManagementConfigurationDocument | null>(null);
  const [importText, setImportText] = useState("");
  useEffect(() => { if (current.data) setDraft(clone(current.data.document)); }, [current.data]);
  const problem = draft ? validate(draft) : null;
  const changed = useMemo(() => Boolean(draft && current.data && JSON.stringify(draft) !== JSON.stringify(current.data.document)), [draft, current.data]);
  const draftFingerprint = useMemo(() => JSON.stringify(draft), [draft]);
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["ai-agent-management", "configuration"] }),
      client.invalidateQueries({ queryKey: ["ai-agent-management", "configuration-versions"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => {
      if (!draft || !current.data || problem || preview.data?.fingerprint !== draftFingerprint) throw new Error(problem ?? "Preview the current draft before applying it.");
      return aiAgentService.updateConfiguration({ environment, expected_version: current.data.version, document: draft });
    },
    onSuccess: refresh,
  });
  const preview = useMutation({
    mutationFn: async () => {
      if (!draft || !current.data || problem) throw new Error(problem ?? "Configuration is unavailable.");
      const result = await aiAgentService.previewConfiguration({ environment, expected_version: current.data.version, document: draft });
      return { fingerprint: draftFingerprint, result };
    },
  });
  const rollback = useMutation({ mutationFn: (target_version: number) => aiAgentService.rollbackConfiguration({ environment, target_version }), onSuccess: refresh });
  const importMutation = useMutation({
    mutationFn: () => aiAgentService.importConfiguration(JSON.parse(importText) as ConfigurationExportDocument),
    onSuccess: async () => { setImportText(""); await refresh(); },
  });
  const exportMutation = useMutation({
    mutationFn: () => aiAgentService.exportConfiguration(environment),
    onSuccess: (document) => {
      const blob = new Blob([JSON.stringify(document, null, 2)], { type: "application/json" });
      const link = window.document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `ai-agent-management-${environment}-v${document.version}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    },
  });
  const numberField = (
    label: string,
    value: number,
    minimum: number,
    maximum: number,
    update: (value: number) => void,
    guidance: string,
  ) => <label className="space-y-2"><span className="text-sm font-medium" title={guidance}>{label}</span><Input type="number" min={minimum} max={maximum} value={value} onChange={(event) => update(Number(event.target.value))}/><span className="block text-xs text-muted-foreground">{guidance}</span></label>;
  if (current.isLoading || !draft) return <PageSkeleton/>;
  if (current.error) return <GovernedError error={current.error} retry={() => void current.refetch()}/>;
  return <main className="space-y-6">
    <PageHeader title="Runtime configuration" description="Tenant-owned policy for provider resilience, execution, governance, evaluation, health, rollout, and presentation. Changes apply without a service restart." actions={<select aria-label="Environment" className="rounded-md border bg-background px-3 py-2 text-sm" value={environment} onChange={(event) => setEnvironment(event.target.value as ConfigurationEnvironment)}><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option></select>}/>
    <Card><CardHeader><CardTitle>Preview</CardTitle></CardHeader><CardContent><p className="text-sm">{changed ? `Validate the proposed replacement for version ${current.data.version} before applying it.` : "No unapplied differences."}</p>{problem ? <p role="alert" className="mt-2 text-sm text-destructive">{problem}</p> : null}{preview.data?.fingerprint === draftFingerprint ? <div className="mt-3 rounded-lg border bg-muted/30 p-3 text-sm"><p>Server validation passed. Proposed version: {preview.data.result.proposed_version}.</p><ul className="mt-2 list-disc pl-5">{preview.data.result.changes.map((change) => <li key={change.path}>{change.path}</li>)}</ul></div> : null}<div className="mt-4 flex gap-2"><Button variant="outline" disabled={!changed || Boolean(problem) || preview.isPending} onClick={() => preview.mutate()}>Validate preview</Button><Button disabled={!changed || Boolean(problem) || save.isPending || preview.data?.fingerprint !== draftFingerprint} onClick={() => save.mutate()}>Apply configuration</Button><Button variant="outline" disabled={!changed} onClick={() => setDraft(clone(current.data.document))}>Discard</Button></div>{preview.error ? <MutationError error={preview.error}/> : null}{save.error ? <MutationError error={save.error}/> : null}</CardContent></Card>
    <section className="grid gap-6 xl:grid-cols-2">
      <Card><CardHeader><CardTitle>Provider resilience</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">
        {numberField("Maximum output tokens", draft.provider.max_tokens, 1, 1_000_000, (value) => setDraft({ ...draft, provider: { ...draft.provider, max_tokens: value } }), "Hard upper bound sent to provider adapters.")}
        {numberField("Temperature", draft.provider.temperature, 0, 2, (value) => setDraft({ ...draft, provider: { ...draft.provider, temperature: value } }), "Sampling variability accepted by provider adapters.")}
        {numberField("Timeout (seconds)", draft.provider.timeout_seconds, 1, 600, (value) => setDraft({ ...draft, provider: { ...draft.provider, timeout_seconds: value } }), "Each external provider attempt is cancelled at this boundary.")}
        {numberField("Maximum retries", draft.provider.max_retries, 0, 20, (value) => setDraft({ ...draft, provider: { ...draft.provider, max_retries: value } }), "Retries use exponential backoff with jitter.")}
      </Card>
      <Card><CardHeader><CardTitle>Execution and scheduling</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">
        {numberField("Maximum messages", draft.runner.maximum_messages, 1, 10_000, (value) => setDraft({ ...draft, runner: { ...draft.runner, maximum_messages: value } }), "Maximum messages accepted by the published runner.")}
        {numberField("Default priority", draft.schedule.default_priority, draft.schedule.priority_minimum, draft.schedule.priority_maximum, (value) => setDraft({ ...draft, schedule: { ...draft.schedule, default_priority: value } }), "Priority assigned when a caller omits it.")}
        {numberField("Default retries", draft.schedule.default_maximum_retries, 0, draft.schedule.maximum_retries_limit, (value) => setDraft({ ...draft, schedule: { ...draft.schedule, default_maximum_retries: value } }), "Retry budget assigned to new schedules.")}
        {numberField("Dispatch batch maximum", draft.schedule.dispatch_batch_maximum, draft.schedule.dispatch_batch_minimum, 1000, (value) => setDraft({ ...draft, schedule: { ...draft.schedule, dispatch_batch_maximum: value } }), "Maximum work claimed by one dispatcher transaction.")}
      </Card>
    </section>
    <Card><CardHeader><CardTitle>Complete configuration document</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">Every module setting is portable here. The API validates exact fields, safe bounds, allow-lists, and dependent thresholds before any version can be saved.</p><Textarea className="min-h-[28rem] font-mono text-xs" aria-label="Complete configuration JSON" value={JSON.stringify(draft, null, 2)} onChange={(event) => { try { setDraft(JSON.parse(event.target.value) as AgentManagementConfigurationDocument); } catch { /* Keep the last structurally valid document unsaved. */ } }}/></CardContent></Card>
    <section className="grid gap-6 xl:grid-cols-2">
      <Card><CardHeader><CardTitle>Import / export</CardTitle></CardHeader><CardContent className="space-y-3"><Textarea aria-label="Configuration import document" className="min-h-40 font-mono text-xs" placeholder="Paste an exported configuration document" value={importText} onChange={(event) => setImportText(event.target.value)}/><div className="flex gap-2"><Button variant="outline" disabled={!importText || importMutation.isPending} onClick={() => importMutation.mutate()}>Validate and import</Button><Button variant="outline" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>Export current version</Button></div>{importMutation.error ? <MutationError error={importMutation.error}/> : null}</CardContent></Card>
      <Card><CardHeader><CardTitle>Immutable history and rollback</CardTitle></CardHeader><CardContent>{versions.isLoading ? <PageSkeleton rows={2}/> : versions.error ? <GovernedError error={versions.error} retry={() => void versions.refetch()}/> : <ul className="divide-y">{versions.data?.map((version) => <li key={version.id} className="flex items-center justify-between gap-4 py-3"><div><p className="font-medium">Version {version.version} · {version.change_type}</p><p className="text-xs text-muted-foreground">{formatDate(version.created_at)} · correlation {version.correlation_id}</p></div><Button size="sm" variant="outline" disabled={version.version === current.data.version || rollback.isPending} onClick={() => rollback.mutate(version.version)}>Rollback</Button></li>)}</ul>}{rollback.error ? <MutationError error={rollback.error}/> : null}</CardContent></Card>
    </section>
  </main>;
}
