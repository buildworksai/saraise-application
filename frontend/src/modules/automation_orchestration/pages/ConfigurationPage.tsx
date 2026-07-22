import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, History, RotateCcw, Save, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import type {
  ConfigurationEnvironment,
  ConfigurationWriteRequest,
  OrchestrationConfigurationDTO,
} from "../contracts";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import { LoadError, PageHeader, PageSkeleton, StatusPill, formatDate } from "../components/OrchestrationUI";

const configurationKey = (environment: ConfigurationEnvironment, cohort: string) =>
  ["automation-orchestration", "configuration", environment, cohort] as const;

function toRequest(configuration: OrchestrationConfigurationDTO): ConfigurationWriteRequest {
  return {
    environment: configuration.environment,
    cohort: configuration.cohort,
    document: configuration.document,
    enabled: configuration.enabled,
    rollout_percentage: configuration.rollout_percentage,
    allowed_roles: configuration.allowed_roles,
  };
}

function isConfigurationDocument(value: unknown): value is OrchestrationConfigurationDTO {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Readonly<Record<string, unknown>>;
  return (
    typeof candidate.environment === "string" &&
    typeof candidate.cohort === "string" &&
    typeof candidate.enabled === "boolean" &&
    typeof candidate.rollout_percentage === "number" &&
    Array.isArray(candidate.allowed_roles) &&
    Boolean(candidate.document) &&
    typeof candidate.document === "object"
  );
}

// The configuration editor intentionally keeps all guided, raw-document,
// preview, history, rollback, and portability controls in one governed page.
// eslint-disable-next-line max-lines-per-function
export function ConfigurationPage() {
  const queryClient = useQueryClient();
  const importRef = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] = useState<ConfigurationEnvironment>("development");
  const [cohort, setCohort] = useState("all");
  const [draft, setDraft] = useState<OrchestrationConfigurationDTO | null>(null);
  const [roles, setRoles] = useState("");
  const [documentText, setDocumentText] = useState("");
  const [importError, setImportError] = useState("");
  const query = useQuery({
    queryKey: configurationKey(environment, cohort),
    queryFn: () => service.getConfiguration(environment, cohort),
  });
  const versions = useQuery({
    queryKey: [...configurationKey(environment, cohort), "versions"],
    queryFn: () => service.listConfigurationVersions(environment, cohort),
  });
  const audits = useQuery({
    queryKey: [...configurationKey(environment, cohort), "audits"],
    queryFn: () => service.listConfigurationAudits(environment, cohort),
  });

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data);
    setRoles(query.data.allowed_roles.join(", "));
    setDocumentText(JSON.stringify(query.data.document, null, 2));
  }, [query.data]);

  const request = useMemo(() => (draft ? toRequest({
    ...draft,
    environment,
    cohort,
    allowed_roles: roles.split(",").map((role) => role.trim()).filter(Boolean),
  }) : null), [cohort, draft, environment, roles]);
  const errors = useMemo(() => {
    if (!draft) return [];
    const { limits } = draft.document;
    const messages: string[] = [];
    if (limits.parallel_tasks_min > limits.parallel_tasks_max) messages.push("Parallel minimum exceeds maximum.");
    if (limits.timeout_seconds_min > limits.timeout_seconds_max) messages.push("Timeout minimum exceeds maximum.");
    if (limits.attempts_min > limits.attempts_max) messages.push("Attempt minimum exceeds maximum.");
    if (draft.document.defaults.max_parallel_tasks < limits.parallel_tasks_min || draft.document.defaults.max_parallel_tasks > limits.parallel_tasks_max) messages.push("Default parallel tasks is outside its safe limits.");
    if (draft.rollout_percentage < 0 || draft.rollout_percentage > 100) messages.push("Rollout must be between 0 and 100.");
    return messages;
  }, [draft]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["automation-orchestration", "configuration"] });
  };
  const save = useMutation({ mutationFn: () => {
    if (!request) throw new Error("Configuration is unavailable.");
    return service.updateConfiguration(request);
  }, onSuccess: invalidate });
  const preview = useMutation({ mutationFn: () => {
    if (!request) throw new Error("Configuration is unavailable.");
    return service.previewConfiguration(request);
  }});
  const rollback = useMutation({ mutationFn: (version: number) => service.rollbackConfiguration(environment, cohort, version), onSuccess: invalidate });
  const imported = useMutation({ mutationFn: (value: ConfigurationWriteRequest) => service.importConfiguration(value), onSuccess: invalidate });

  if (query.isLoading || !draft) return <PageSkeleton />;
  if (query.error) return <LoadError error={query.error} retry={() => void query.refetch()} />;

  const updateLimits = (field: keyof typeof draft.document.limits, value: number) => setDraft({
    ...draft,
    document: { ...draft.document, limits: { ...draft.document.limits, [field]: value } },
  });
  const updateDefaults = (field: keyof typeof draft.document.defaults, value: number) => setDraft({
    ...draft,
    document: { ...draft.document, defaults: { ...draft.document.defaults, [field]: value } },
  });

  async function exportDocument() {
    const value = await service.exportConfiguration(environment, cohort);
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `automation-orchestration-${environment}-${cohort}-v${value.version}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importDocument(file: File) {
    setImportError("");
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isConfigurationDocument(parsed)) throw new Error("The selected file is not an orchestration configuration document.");
      setDraft(parsed);
      setEnvironment(parsed.environment);
      setCohort(parsed.cohort);
      setRoles(parsed.allowed_roles.join(", "));
      setDocumentText(JSON.stringify(parsed.document, null, 2));
      await imported.mutateAsync(toRequest(parsed));
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Configuration import failed.");
    }
  }

  function applyDocumentText() {
    setImportError("");
    if (!draft) return;
    try {
      const parsed: unknown = JSON.parse(documentText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("The configuration document must be a JSON object.");
      }
      setDraft({ ...draft, document: parsed as OrchestrationConfigurationDTO["document"] });
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Configuration JSON is invalid.");
    }
  }

  return <main className="space-y-6">
    <PageHeader title="Orchestration configuration" description="Versioned tenant policy for execution, retries, schedules, health, rollout, and operator presentation." actions={<><Button variant="outline" onClick={() => preview.mutate()} disabled={!request || errors.length > 0 || preview.isPending}><Eye className="mr-2 h-4 w-4" />Preview</Button><Button onClick={() => save.mutate()} disabled={!request || errors.length > 0 || save.isPending}><Save className="mr-2 h-4 w-4" />Apply version</Button></>} />
    <Card><CardHeader><CardTitle>Scope and phased rollout</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><label className="text-sm font-medium">Environment<select aria-label="Environment" value={environment} onChange={(event) => setEnvironment(event.target.value as ConfigurationEnvironment)} className="mt-1 block h-10 w-full rounded-md border bg-background px-3"><option value="development">Development</option><option value="self-hosted">Self-hosted</option><option value="saas">SaaS</option></select></label><Input label="Cohort" title="Use all for the tenant default, or a named rollout cohort." value={cohort} maxLength={64} onChange={(event) => setCohort(event.target.value)} /><label className="flex items-center gap-3 rounded border p-3 text-sm"><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />Capability enabled</label><Input label="Rollout percentage" title="Percentage of the selected cohort that receives this policy." type="number" min="0" max="100" disabled={!draft.enabled} value={draft.rollout_percentage} onChange={(event) => setDraft({ ...draft, rollout_percentage: Number(event.target.value) })} /><Input label="Allowed roles" title="Comma-separated role allow-list. Empty applies to all governed roles." disabled={!draft.enabled || draft.rollout_percentage === 0} value={roles} onChange={(event) => setRoles(event.target.value)} /></CardContent></Card>
    <div className="grid gap-6 xl:grid-cols-2"><Card><CardHeader><CardTitle>Safe limits</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2"><Input label="Parallel minimum" type="number" min="1" max={draft.document.limits.parallel_tasks_max} value={draft.document.limits.parallel_tasks_min} onChange={(event) => updateLimits("parallel_tasks_min", Number(event.target.value))} /><Input label="Parallel maximum" type="number" min={draft.document.limits.parallel_tasks_min} max="100" value={draft.document.limits.parallel_tasks_max} onChange={(event) => updateLimits("parallel_tasks_max", Number(event.target.value))} /><Input label="Timeout minimum (seconds)" type="number" min="1" max={draft.document.limits.timeout_seconds_max} value={draft.document.limits.timeout_seconds_min} onChange={(event) => updateLimits("timeout_seconds_min", Number(event.target.value))} /><Input label="Timeout maximum (seconds)" type="number" min={draft.document.limits.timeout_seconds_min} max="86400" value={draft.document.limits.timeout_seconds_max} onChange={(event) => updateLimits("timeout_seconds_max", Number(event.target.value))} /><Input label="Attempt minimum" type="number" min="1" max={draft.document.limits.attempts_max} value={draft.document.limits.attempts_min} onChange={(event) => updateLimits("attempts_min", Number(event.target.value))} /><Input label="Attempt maximum" type="number" min={draft.document.limits.attempts_min} max="20" value={draft.document.limits.attempts_max} onChange={(event) => updateLimits("attempts_max", Number(event.target.value))} /></CardContent></Card><Card><CardHeader><CardTitle>Execution defaults</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2"><Input label="Parallel tasks" type="number" min={draft.document.limits.parallel_tasks_min} max={draft.document.limits.parallel_tasks_max} value={draft.document.defaults.max_parallel_tasks} onChange={(event) => updateDefaults("max_parallel_tasks", Number(event.target.value))} /><Input label="Timeout (seconds)" type="number" min={draft.document.limits.timeout_seconds_min} max={draft.document.limits.timeout_seconds_max} value={draft.document.defaults.timeout_seconds} onChange={(event) => updateDefaults("timeout_seconds", Number(event.target.value))} /><Input label="Maximum attempts" type="number" min={draft.document.limits.attempts_min} max={draft.document.limits.attempts_max} value={draft.document.defaults.max_attempts} onChange={(event) => updateDefaults("max_attempts", Number(event.target.value))} /><Input label="Retry jitter ratio" title="Adds bounded random delay to prevent synchronized retry storms." type="number" min="0" max="1" step="0.05" value={draft.document.defaults.retry_jitter_ratio} onChange={(event) => updateDefaults("retry_jitter_ratio", Number(event.target.value))} /></CardContent></Card></div>
    <Card><CardHeader><CardTitle>Advanced policy document</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">Edit every workflow, integration, scheduler, health, and UI setting. The server enforces the same allow-lists, dependencies, and platform ceilings used by the guided fields.</p><Textarea aria-label="Complete configuration document" rows={20} value={documentText} onChange={(event) => setDocumentText(event.target.value)} /><Button type="button" variant="outline" onClick={applyDocumentText}>Validate JSON locally</Button></CardContent></Card>
    {errors.length ? <div role="alert" className="rounded border border-destructive/40 p-4 text-sm text-destructive">{errors.map((error) => <p key={error}>{error}</p>)}</div> : null}
    {preview.data ? <Card><CardHeader><CardTitle>Dry-run diff</CardTitle></CardHeader><CardContent><p className="text-sm">Changed sections: {preview.data.changed_sections.join(", ") || "none"}</p><pre className="mt-3 max-h-80 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(preview.data.after, null, 2)}</pre></CardContent></Card> : null}
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="h-5 w-5" />Version history and immutable audit</CardTitle></CardHeader><CardContent className="grid gap-6 lg:grid-cols-2"><div>{versions.data?.items.length ? <ul className="divide-y">{versions.data.items.map((version) => <li key={version.id} className="flex items-center justify-between py-3 text-sm"><span>Version {version.version}<small className="block text-muted-foreground">{formatDate(version.created_at)} · {version.correlation_id}</small></span><Button size="sm" variant="outline" disabled={version.version === draft.version || rollback.isPending} onClick={() => rollback.mutate(version.version)}><RotateCcw className="mr-2 h-3 w-3" />Rollback</Button></li>)}</ul> : <p className="text-sm text-muted-foreground">No persisted versions yet; the defensible bootstrap policy is active.</p>}</div><div>{audits.data?.items.length ? <ul className="divide-y">{audits.data.items.map((audit) => <li key={audit.id} className="py-3 text-sm"><StatusPill status={audit.action} /> <span className="ml-2">Version {audit.version}</span><small className="block text-muted-foreground">{formatDate(audit.changed_at)} · actor {audit.actor_id} · {audit.correlation_id}</small></li>)}</ul> : <p className="text-sm text-muted-foreground">Audit evidence appears after the first applied version.</p>}</div></CardContent></Card>
    <Card><CardHeader><CardTitle>Configuration document portability</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-3"><Button variant="outline" onClick={() => void exportDocument()}><Download className="mr-2 h-4 w-4" />Export JSON</Button><input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importDocument(file); }} /><Button variant="outline" onClick={() => importRef.current?.click()} disabled={imported.isPending}><Upload className="mr-2 h-4 w-4" />Import and validate</Button>{importError ? <p role="alert" className="w-full text-sm text-destructive">{importError}</p> : null}</CardContent></Card>
  </main>;
}
