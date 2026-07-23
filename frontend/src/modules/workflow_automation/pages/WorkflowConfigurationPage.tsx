import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, History, RotateCcw, Save, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import type {
  WorkflowConfigurationDocument,
  WorkflowConfigurationDTO,
  WorkflowConfigurationExportDTO,
} from "../contracts";
import { workflowService } from "../services/workflow-service";
import { PageHeader, PageSkeleton, WorkflowProblem } from "../components/WorkflowUI";

type Environment = WorkflowConfigurationDTO["environment"];

function isExportDocument(value: unknown): value is WorkflowConfigurationExportDTO {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Readonly<Record<string, unknown>>;
  return candidate.schema === "saraise.workflow-automation.configuration/v1"
    && typeof candidate.environment === "string"
    && typeof candidate.version === "number"
    && Boolean(candidate.document)
    && typeof candidate.document === "object";
}

export function WorkflowConfigurationPage() {
  const cache = useQueryClient();
  const importRef = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] = useState<Environment>("production");
  const [draft, setDraft] = useState<WorkflowConfigurationDocument | null>(null);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("operator-policy-change");
  const [problem, setProblem] = useState("");
  const query = useQuery({
    queryKey: ["workflow-automation", "configuration", environment],
    queryFn: () => workflowService.configuration.get(environment),
  });
  const history = useQuery({
    queryKey: ["workflow-automation", "configuration", environment, "history"],
    queryFn: () => workflowService.configuration.history(environment),
  });

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data.document);
    setText(JSON.stringify(query.data.document, null, 2));
  }, [query.data]);

  const invalidate = async () => {
    await cache.invalidateQueries({ queryKey: ["workflow-automation", "configuration"] });
  };
  const save = useMutation({
    mutationFn: () => {
      if (!query.data || !draft) throw new Error("Configuration is unavailable.");
      return workflowService.configuration.update({
        environment,
        expected_version: query.data.version,
        change_reason: reason,
        document: draft,
      });
    },
    onSuccess: invalidate,
  });
  const preview = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error("Configuration is unavailable.");
      return workflowService.configuration.preview({ environment, document: draft });
    },
  });
  const rollback = useMutation({
    mutationFn: (target: number) => {
      if (!query.data) throw new Error("Configuration is unavailable.");
      return workflowService.configuration.rollback(environment, query.data.version, target);
    },
    onSuccess: invalidate,
  });

  if (query.isLoading || !draft) return <PageSkeleton label="Loading workflow configuration" />;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()} />;
  const current = query.data;
  if (!current) return <WorkflowProblem error={new Error("Configuration response is empty.")} retry={() => void query.refetch()} />;

  const setLimit = (key: keyof WorkflowConfigurationDocument["limits"], value: number) => {
    const next = { ...draft, limits: { ...draft.limits, [key]: value } };
    setDraft(next);
    setText(JSON.stringify(next, null, 2));
  };
  const setFlag = (key: string, enabled: boolean) => {
    const current = draft.feature_flags[key];
    if (!current) return;
    const next = {
      ...draft,
      feature_flags: { ...draft.feature_flags, [key]: { ...current, enabled } },
    };
    setDraft(next);
    setText(JSON.stringify(next, null, 2));
  };
  const setRolloutList = (key: string, field: "roles" | "cohorts", value: string) => {
    const current = draft.feature_flags[key];
    if (!current) return;
    const values = value.split(",").map((item) => item.trim()).filter(Boolean);
    const next = {
      ...draft,
      feature_flags: { ...draft.feature_flags, [key]: { ...current, [field]: values } },
    };
    setDraft(next);
    setText(JSON.stringify(next, null, 2));
  };
  const flagHasAdapter = (key: string): boolean => {
    if (key === "event_triggers") return draft.allowed_values.trigger_types.includes("event");
    if (key === "scheduled_triggers") return draft.allowed_values.trigger_types.includes("scheduled");
    if (key === "parallel_workflows") return draft.allowed_values.workflow_types.includes("parallel");
    if (key === "timeout_notifications") return draft.allowed_values.timeout_actions.includes("notify");
    return false;
  };
  const applyText = () => {
    setProblem("");
    try {
      const value: unknown = JSON.parse(text);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Document must be an object.");
      setDraft(value as WorkflowConfigurationDocument);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "Invalid JSON.");
    }
  };
  const exportDocument = async () => {
    const value = await workflowService.configuration.exportDocument(environment);
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `workflow-automation-${environment}-v${value.version}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const importDocument = async (file: File) => {
    setProblem("");
    try {
      const value: unknown = JSON.parse(await file.text());
      if (!isExportDocument(value)) throw new Error("This is not a workflow automation configuration export.");
      await workflowService.configuration.importDocument({
        environment: value.environment,
        expected_version: current.version,
        change_reason: "configuration-import",
        document: value.document,
      });
      setEnvironment(value.environment);
      await invalidate();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "Import failed.");
    }
  };

  return <main className="space-y-6">
    <PageHeader title="Workflow configuration" description="Versioned tenant policy for workflow defaults, safe limits, retries, health, rollout, and operator presentation." />
    <Card><CardHeader><CardTitle>Scope and guarded defaults</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-3"><label className="text-sm font-medium">Environment<select className="mt-1 block h-10 w-full rounded-md border bg-background px-3" value={environment} onChange={(event) => setEnvironment(event.target.value as Environment)}><option value="development">Development</option><option value="test">Test</option><option value="staging">Staging</option><option value="production">Production</option></select></label><Input label="Change reason" title="Recorded with actor, before/after values, and correlation ID." value={reason} onChange={(event) => setReason(event.target.value)} /><Input label="Default priority" type="number" min={draft.limits.execution_priority_min} max={draft.limits.execution_priority_max} value={draft.defaults.execution_priority} readOnly title="Change defaults in the full policy document; limits below constrain all saves." /></CardContent></Card>
    <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle>Safe limits</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2"><Input label="Priority minimum" type="number" min="1" max={draft.limits.execution_priority_max} value={draft.limits.execution_priority_min} onChange={(event) => setLimit("execution_priority_min", Number(event.target.value))}/><Input label="Priority maximum" type="number" min={draft.limits.execution_priority_min} max="9" value={draft.limits.execution_priority_max} onChange={(event) => setLimit("execution_priority_max", Number(event.target.value))}/><Input label="Catalog default limit" type="number" min="1" max={draft.limits.catalog_max_limit} value={draft.limits.catalog_default_limit} onChange={(event) => setLimit("catalog_default_limit", Number(event.target.value))}/><Input label="Catalog maximum" type="number" min={draft.limits.catalog_default_limit} max="500" value={draft.limits.catalog_max_limit} onChange={(event) => setLimit("catalog_max_limit", Number(event.target.value))}/></CardContent></Card><Card><CardHeader><CardTitle>Feature flags and phased rollout</CardTitle></CardHeader><CardContent className="space-y-3">{Object.entries(draft.feature_flags).map(([key, rollout]) => { const available = flagHasAdapter(key); return <div key={key} className="space-y-2 rounded border p-3 text-sm"><label className="flex items-center justify-between"><span><strong>{key.replaceAll("_", " ")}</strong><small className="block text-muted-foreground">{available ? "Available for phased rollout." : "Unavailable until a complete backend adapter is installed."}</small></span><input type="checkbox" checked={rollout.enabled} disabled={!available} title={available ? "Enable this capability for the selected rollout." : "No end-to-end adapter is installed."} onChange={(event) => setFlag(key, event.target.checked)} /></label><div className="grid gap-2 sm:grid-cols-2"><Input label="Role IDs" value={rollout.roles.join(", ")} title="Comma-separated role identifiers; blank targets every role." onChange={(event) => setRolloutList(key, "roles", event.target.value)} /><Input label="Cohorts" value={rollout.cohorts.join(", ")} title="Comma-separated tenant cohort keys; blank targets every cohort." onChange={(event) => setRolloutList(key, "cohorts", event.target.value)} /></div></div>; })}</CardContent></Card></div>
    <Card><CardHeader><CardTitle>Complete configuration document</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">Every audited default, threshold, allow-list, handler mapping, lifecycle policy, operational value, and visual setting is portable here. The server rejects unknown sections and unsafe combinations.</p><Textarea aria-label="Complete workflow configuration document" rows={24} className="font-mono text-xs" value={text} onChange={(event) => setText(event.target.value)} /><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={applyText}>Validate JSON locally</Button><Button variant="outline" disabled={preview.isPending} onClick={() => preview.mutate()}><Eye className="mr-2 h-4 w-4"/>Preview</Button><Button disabled={!reason.trim() || save.isPending} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4"/>Apply version</Button></div>{problem ? <p role="alert" className="text-sm text-destructive">{problem}</p> : null}{save.error ? <WorkflowProblem error={save.error} retry={() => save.mutate()}/> : null}{preview.data ? <p role="status" className="rounded border p-3 text-sm">Changed sections: {preview.data.changed_sections.join(", ") || "none"}. Restart required: {preview.data.restart_required ? "yes" : "no"}.</p> : null}</CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="h-5 w-5"/>Immutable version history</CardTitle></CardHeader><CardContent>{history.data?.length ? <ul className="divide-y">{history.data.map((revision) => <li key={revision.id} className="flex items-center justify-between gap-3 py-3 text-sm"><span>Version {revision.version}<small className="block text-muted-foreground">{revision.change_reason} · actor {revision.actor_id ?? "bootstrap"} · {revision.correlation_id}</small></span><Button size="sm" variant="outline" disabled={revision.version === current.version || rollback.isPending} onClick={() => rollback.mutate(revision.version)}><RotateCcw className="mr-2 h-3 w-3"/>Rollback</Button></li>)}</ul> : <p className="text-sm text-muted-foreground">No history is available.</p>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Import and export</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-3"><Button variant="outline" onClick={() => void exportDocument()}><Download className="mr-2 h-4 w-4"/>Export JSON</Button><input ref={importRef} className="hidden" type="file" accept="application/json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importDocument(file); }}/><Button variant="outline" onClick={() => importRef.current?.click()}><Upload className="mr-2 h-4 w-4"/>Import and apply</Button></CardContent></Card>
  </main>;
}
