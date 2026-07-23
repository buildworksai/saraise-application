import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, History, RotateCcw, Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { MasterDataConfigurationDocument } from "../contracts";
import { masterDataService } from "../services/master-data-service";
import { GovernedError, MutationNotice, PageHeader, PageSkeleton, QUERY_KEYS, Surface, formatDate, useStableIdempotencyKey } from "../components/MdmUI";
import { useMasterDataConfiguration } from "../hooks/useMasterDataConfiguration";

function numberValue(value: string): number {
  return Number(value);
}

export function MasterDataConfigurationPage() {
  const cache = useQueryClient();
  const current = useMasterDataConfiguration();
  const history = useQuery({ queryKey: QUERY_KEYS.configurationHistory(), queryFn: () => masterDataService.configuration.history() });
  const [draft, setDraft] = useState<MasterDataConfigurationDocument>();
  const [reason, setReason] = useState("");
  const [importText, setImportText] = useState("");
  const [clientError, setClientError] = useState("");
  const saveKey = useStableIdempotencyKey("configuration-save");
  const importKey = useStableIdempotencyKey("configuration-import");
  const rollbackKey = useStableIdempotencyKey("configuration-rollback");

  useEffect(() => {
    if (current.data?.data.document) setDraft(current.data.data.document);
  }, [current.data]);

  const refresh = async () => {
    await cache.invalidateQueries({ queryKey: QUERY_KEYS.configuration() });
    await cache.invalidateQueries({ queryKey: QUERY_KEYS.configurationHistory() });
  };
  const preview = useMutation({ mutationFn: (document: MasterDataConfigurationDocument) => masterDataService.configuration.preview({ document }) });
  const save = useMutation({
    mutationFn: async () => {
      if (!draft || !current.data) throw new Error("Authoritative tenant configuration is unavailable.");
      return masterDataService.configuration.update(current.data.data.id, { document: draft, reason, idempotency_key: saveKey });
    },
    onSuccess: async (response) => { setDraft(response.data.document); await refresh(); },
  });
  const imported = useMutation({
    mutationFn: async () => {
      let document: MasterDataConfigurationDocument;
      try {
        document = JSON.parse(importText) as MasterDataConfigurationDocument;
      } catch {
        throw new Error("The import document is not valid JSON.");
      }
      return masterDataService.configuration.importDocument({ document, reason, idempotency_key: importKey });
    },
    onSuccess: async (response) => { setDraft(response.data.document); setImportText(""); await refresh(); },
  });
  const rollback = useMutation({
    mutationFn: (version: number) => masterDataService.configuration.rollback({ version, reason, idempotency_key: rollbackKey }),
    onSuccess: async (response) => { setDraft(response.data.document); await refresh(); },
  });
  const exportDocument = useMutation({
    mutationFn: () => masterDataService.configuration.exportDocument(),
    onSuccess: (response) => {
      const blob = new Blob([JSON.stringify(response.data.document, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `master-data-configuration-v${current.data?.data.version ?? "current"}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
  });

  if (current.isLoading) return <PageSkeleton label="Loading master-data configuration"/>;
  if (current.error) return <GovernedError error={current.error} retry={() => void current.refetch()}/>;
  if (!current.data || !draft) return <GovernedError error={new Error("Tenant configuration was not returned. Editing is disabled.")}/>;
  const configuration = current.data.data;
  const invalidThresholds = draft.matching.defaults.review_threshold > draft.matching.defaults.auto_confirm_threshold;
  const invalidRollout = draft.feature_rollout.percentage < 0 || draft.feature_rollout.percentage > 100;
  const canSubmit = Boolean(reason.trim()) && !invalidThresholds && !invalidRollout;

  const updateFeature = <K extends keyof MasterDataConfigurationDocument["feature_rollout"]>(key: K, value: MasterDataConfigurationDocument["feature_rollout"][K]) =>
    setDraft((valueDraft) => valueDraft ? { ...valueDraft, feature_rollout: { ...valueDraft.feature_rollout, [key]: value } } : valueDraft);
  const updateUi = <K extends keyof MasterDataConfigurationDocument["ui"]>(key: K, value: MasterDataConfigurationDocument["ui"][K]) =>
    setDraft((valueDraft) => valueDraft ? { ...valueDraft, ui: { ...valueDraft.ui, [key]: value } } : valueDraft);
  const updateLimit = <K extends keyof MasterDataConfigurationDocument["limits"]>(key: K, value: MasterDataConfigurationDocument["limits"][K]) =>
    setDraft((valueDraft) => valueDraft ? { ...valueDraft, limits: { ...valueDraft.limits, [key]: value } } : valueDraft);
  const updateStatusToken = (key: keyof MasterDataConfigurationDocument["ui"]["status_tokens"], value: "destructive" | "success" | "warning") =>
    setDraft((valueDraft) => valueDraft ? { ...valueDraft, ui: { ...valueDraft.ui, status_tokens: { ...valueDraft.ui.status_tokens, [key]: value } } } : valueDraft);

  return <main className="space-y-6">
    <PageHeader title="Master-data configuration" description={`Tenant-scoped version ${configuration.version}. Every save is validated server-side, audited, and reversible.`} actions={<Button variant="outline" disabled={exportDocument.isPending} onClick={() => exportDocument.mutate()}><Download className="mr-2 h-4 w-4"/>Export</Button>}/>
    <MutationNotice error={preview.error ?? save.error ?? imported.error ?? rollback.error ?? exportDocument.error} success={save.isSuccess ? "Configuration saved as a new immutable version." : imported.isSuccess ? "Configuration imported and versioned." : rollback.isSuccess ? "Configuration rollback created a new version." : undefined}/>
    <Surface title="Feature rollout">
      <p className="mb-4 text-sm text-muted-foreground">Disable without a deploy, then phase availability by runtime, role, cohort, and tenant percentage. Server authorization remains authoritative.</p>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={draft.feature_rollout.enabled} onChange={(event) => updateFeature("enabled", event.target.checked)}/>Module enabled</label>
        <Input label="Rollout percentage" type="number" min={0} max={100} value={draft.feature_rollout.percentage} onChange={(event) => updateFeature("percentage", numberValue(event.target.value))} error={invalidRollout ? "Percentage must be between 0 and 100." : undefined}/>
        <Input label="Runtime modes (comma-separated)" value={draft.feature_rollout.modes.join(", ")} onChange={(event) => updateFeature("modes", event.target.value.split(",").map((item) => item.trim()).filter(Boolean) as MasterDataConfigurationDocument["feature_rollout"]["modes"])}/>
        <Input label="Roles (comma-separated)" value={draft.feature_rollout.roles.join(", ")} onChange={(event) => updateFeature("roles", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))}/>
        <Input label="Cohorts (comma-separated)" value={draft.feature_rollout.cohorts.join(", ")} onChange={(event) => updateFeature("cohorts", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))}/>
      </div>
    </Surface>
    <Surface title="User experience and safe list limits">
      <p className="mb-4 text-sm text-muted-foreground">These values drive module forms, queues, navigation, loading states, and dashboard visuals after the saved version becomes active.</p>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <Input label="Sidebar order" type="number" min={0} max={10_000} value={draft.ui.sidebar_order} onChange={(event) => updateUi("sidebar_order", numberValue(event.target.value))}/>
        <Input label="Loading skeleton cards" type="number" min={1} max={100} value={draft.ui.skeleton_cards} onChange={(event) => updateUi("skeleton_cards", numberValue(event.target.value))}/>
        <Input label="List page size" type="number" min={1} max={1_000} value={draft.ui.list_page_size} onChange={(event) => updateUi("list_page_size", numberValue(event.target.value))}/>
        <Input label="Entity selector size" type="number" min={1} max={1_000_000} value={draft.limits.selector_page_size} onChange={(event) => updateLimit("selector_page_size", numberValue(event.target.value))}/>
        <Input label="Dashboard minimum bar %" type="number" min={0} max={100} value={draft.dashboard.minimum_bar_percent} onChange={(event) => setDraft({ ...draft, dashboard: { ...draft.dashboard, minimum_bar_percent: numberValue(event.target.value) } })}/>
        <label className="text-sm font-medium">Default issue queue state<select className="mt-1 block w-full rounded-md border bg-background p-2" value={draft.ui.quality_issue_default_status} onChange={(event) => updateUi("quality_issue_default_status", event.target.value as MasterDataConfigurationDocument["ui"]["quality_issue_default_status"])}>{["open", "in_review", "resolved", "waived"].map((value) => <option key={value}>{value}</option>)}</select></label>
        {(["danger", "success", "warning"] as const).map((key) => <label key={key} className="text-sm font-medium">{key} status token<select className="mt-1 block w-full rounded-md border bg-background p-2" value={draft.ui.status_tokens[key]} onChange={(event) => updateStatusToken(key, event.target.value as "destructive" | "success" | "warning")}>{["destructive", "success", "warning"].map((value) => <option key={value}>{value}</option>)}</select></label>)}
      </div>
    </Surface>
    <Surface title="Entity, quality, matching, and job defaults">
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <Input label="Default source system" value={draft.entity_defaults.source_system} onChange={(event) => setDraft({ ...draft, entity_defaults: { source_system: event.target.value } })}/>
        <label className="text-sm font-medium">Default quality rule<select className="mt-1 block w-full rounded-md border bg-background p-2" value={draft.quality.defaults.rule_type} onChange={(event) => setDraft({ ...draft, quality: { ...draft.quality, defaults: { ...draft.quality.defaults, rule_type: event.target.value as MasterDataConfigurationDocument["quality"]["defaults"]["rule_type"] } } })}>{Object.keys(draft.quality.rule_schemas).map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="text-sm font-medium">Default matching algorithm<select className="mt-1 block w-full rounded-md border bg-background p-2" value={draft.matching.defaults.algorithm} onChange={(event) => setDraft({ ...draft, matching: { ...draft.matching, defaults: { ...draft.matching.defaults, algorithm: event.target.value as MasterDataConfigurationDocument["matching"]["defaults"]["algorithm"] } } })}>{draft.matching.algorithms.map((value) => <option key={value}>{value}</option>)}</select></label>
        <Input label="Review threshold" type="number" min={draft.matching.threshold_min} max={draft.matching.threshold_max} step={draft.matching.weight_tolerance} value={draft.matching.defaults.review_threshold} onChange={(event) => setDraft({ ...draft, matching: { ...draft.matching, defaults: { ...draft.matching.defaults, review_threshold: event.target.value } } })}/>
        <Input label="Auto-confirm threshold" type="number" min={draft.matching.threshold_min} max={draft.matching.threshold_max} step={draft.matching.weight_tolerance} value={draft.matching.defaults.auto_confirm_threshold} onChange={(event) => setDraft({ ...draft, matching: { ...draft.matching, defaults: { ...draft.matching.defaults, auto_confirm_threshold: event.target.value } } })} error={invalidThresholds ? "Auto-confirm must be at least the review threshold." : undefined}/>
        <Input label="Job poll interval (ms)" type="number" min={250} max={60_000} value={draft.operational.job_poll_interval_ms} onChange={(event) => setDraft({ ...draft, operational: { ...draft.operational, job_poll_interval_ms: numberValue(event.target.value) } })}/>
      </div>
    </Surface>
    <Surface title="Preview and apply">
      <label className="block text-sm font-medium" htmlFor="configuration-reason">Change reason<textarea id="configuration-reason" required className="mt-1 block min-h-20 w-full rounded-md border bg-background p-3" value={reason} onChange={(event) => setReason(event.target.value)}/></label>
      <div className="mt-4 flex flex-wrap gap-3"><Button variant="outline" disabled={!canSubmit || preview.isPending} onClick={() => preview.mutate(draft)}>{preview.isPending ? "Validating…" : "Preview changes"}</Button><Button disabled={!canSubmit || !preview.data?.data.valid || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Apply validated version"}</Button></div>
      {preview.data ? <div className="mt-4 rounded-lg border p-4"><p className="font-medium">{preview.data.data.valid ? "Server validation passed" : "Server validation failed"}</p><p className="mt-2 text-sm text-muted-foreground">{preview.data.data.changes.length} governed values will change.</p></div> : null}
    </Surface>
    <Surface title="Portable import">
      <p className="mb-3 text-sm text-muted-foreground">Paste a complete exported document. Import uses the same server validator and creates an immutable version.</p>
      <textarea aria-label="Configuration import document" className="min-h-44 w-full rounded-md border bg-background p-3 font-mono text-xs" value={importText} onChange={(event) => { setImportText(event.target.value); setClientError(""); }}/>
      {clientError ? <p className="mt-2 text-sm text-destructive">{clientError}</p> : null}
      <Button className="mt-3" variant="outline" disabled={!importText || !reason.trim() || imported.isPending} onClick={() => { try { JSON.parse(importText); imported.mutate(); } catch { setClientError("The import document is not valid JSON."); } }}><Upload className="mr-2 h-4 w-4"/>Import validated document</Button>
    </Surface>
    <Surface title="Immutable history">
      <p className="mb-4 text-sm text-muted-foreground"><History className="mr-2 inline h-4 w-4"/>Rollback never rewrites evidence; it creates a new version from the selected snapshot.</p>
      {history.isLoading ? <p role="status">Loading history…</p> : history.error ? <GovernedError error={history.error} retry={() => void history.refetch()}/> : history.data?.items.length ? <ol className="divide-y">{history.data.items.map((entry) => <li key={entry.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium">Version {entry.version} · {entry.change_type}</p><p className="text-xs text-muted-foreground">{entry.reason} · {formatDate(entry.created_at)}</p><p className="font-mono text-xs text-muted-foreground">{entry.correlation_id}</p></div><Button variant="outline" disabled={!reason.trim() || rollback.isPending || entry.version === configuration.version} onClick={() => rollback.mutate(entry.version)}><RotateCcw className="mr-2 h-4 w-4"/>Rollback to v{entry.version}</Button></li>)}</ol> : <p className="text-sm text-muted-foreground">No configuration history was returned.</p>}
    </Surface>
  </main>;
}
