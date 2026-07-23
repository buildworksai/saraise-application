import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, RotateCcw, Save, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { ConfirmAction, Detail, DetailGrid, GovernedError, PageHeader, PageSkeleton, Surface } from "../components/CustomizationUI";
import { formatDate, parseJSON } from "../components/customization-utils";
import type { ConfigurationExportDocument, RuntimeConfigurationDocument, RuntimeConfigurationVersion } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

function portableConfiguration(value: unknown): ConfigurationExportDocument {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("The import must be a configuration object.");
  const object = value as Record<string, unknown>;
  if (typeof object.schema !== "string" || typeof object.tenant_id !== "string" || typeof object.version !== "number" || typeof object.environment !== "string" || !object.document || typeof object.document !== "object" || Array.isArray(object.document)) throw new Error("The import must contain the governed export schema, tenant, version, environment, and document.");
  return { schema: object.schema, tenant_id: object.tenant_id, version: object.version, environment: object.environment, document: object.document as RuntimeConfigurationDocument };
}

export function RuntimeConfigurationPage() {
  const client = useQueryClient();
  const current = useQuery({ queryKey: ["customization", "runtime-configuration"], queryFn: service.getConfiguration });
  const versions = useQuery({ queryKey: ["customization", "configuration-versions"], queryFn: service.listConfigurationVersions });
  const audit = useQuery({ queryKey: ["customization", "configuration-audit"], queryFn: service.listConfigurationAudit });
  const [environment, setEnvironment] = useState("");
  const [draft, setDraft] = useState("");
  const [previewedDraft, setPreviewedDraft] = useState("");
  const [imported, setImported] = useState<ConfigurationExportDocument | null>(null);
  const [rollbackVersion, setRollbackVersion] = useState<RuntimeConfigurationVersion | null>(null);
  const [localError, setLocalError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (current.data && !draft) {
      setEnvironment(current.data.environment);
      setDraft(JSON.stringify(current.data.document, null, 2));
    }
  }, [current.data, draft]);
  function document(): RuntimeConfigurationDocument {
    return parseJSON(draft) as unknown as RuntimeConfigurationDocument;
  }
  const preview = useMutation({
    mutationFn: () => service.previewConfiguration({ document: document() }),
    onSuccess: result => {
      if (result.valid) { setPreviewedDraft(draft); setLocalError(""); }
      else setLocalError("The server rejected this configuration preview.");
    },
    onError: error => setLocalError(error instanceof Error ? error.message : "Preview failed."),
  });
  const save = useMutation({
    mutationFn: () => {
      if (!current.data) throw new Error("Current configuration is unavailable.");
      const expected_version = current.data.version;
      return imported
        ? service.importConfiguration({ payload: { ...imported, environment, document: document() }, expected_version })
        : service.updateConfiguration({ environment, document: document(), expected_version });
    },
    onSuccess: () => { setImported(null); setPreviewedDraft(""); void client.invalidateQueries({ queryKey: ["customization"] }); },
  });
  const rollback = useMutation({
    mutationFn: (version: RuntimeConfigurationVersion) => {
      if (!current.data) throw new Error("Current configuration is unavailable.");
      return service.rollbackConfiguration({ target_version: version.version, expected_version: current.data.version });
    },
    onSuccess: () => { setRollbackVersion(null); setDraft(""); void client.invalidateQueries({ queryKey: ["customization"] }); },
  });
  async function exportDocument() {
    try {
      const result = await service.exportConfiguration();
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const link = window.document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `customization-configuration-v${result.version}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : "Export failed.");
    }
  }
  async function importFile(file: File) {
    try {
      const portable = portableConfiguration(JSON.parse(await file.text()) as unknown);
      setEnvironment(portable.environment);
      setDraft(JSON.stringify(portable.document, null, 2));
      setImported(portable);
      setPreviewedDraft("");
      setLocalError("");
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : "Import failed.");
    }
  }
  if (current.isLoading || versions.isLoading || audit.isLoading) return <PageSkeleton rows={8}/>;
  const queryError = current.error ?? versions.error ?? audit.error;
  if (queryError) return <GovernedError error={queryError} retry={() => { void current.refetch(); void versions.refetch(); void audit.refetch(); }}/>;
  if (!current.data || !versions.data || !audit.data) return <GovernedError error={new Error("The governed configuration response is incomplete.")}/>;
  let previewDocument = true;
  try { document(); } catch { previewDocument = false; }
  const previewCurrent = previewedDraft === draft && preview.data?.valid === true;
  return <main className="space-y-6">
    <PageHeader title="Customization configuration" description="Tenant-scoped, versioned runtime policy. Every change is previewed, audited with its correlation ID, and reversible." actions={<><input ref={fileInput} className="hidden" type="file" accept="application/json" onChange={event => { const file = event.target.files?.[0]; if (file) void importFile(file); }}/><Button variant="outline" onClick={() => fileInput.current?.click()}><Upload className="mr-2 h-4 w-4"/>Import</Button><Button variant="outline" onClick={() => void exportDocument()}><Download className="mr-2 h-4 w-4"/>Export</Button></>}/>
    <Surface><DetailGrid><Detail label="Tenant">{current.data.tenant_id}</Detail><Detail label="Version">{current.data.version}</Detail><Detail label="Environment">{current.data.environment}</Detail><Detail label="Updated">{formatDate(current.data.updated_at)}</Detail><Detail label="Updated by">{current.data.updated_by ?? "—"}</Detail><Detail label="Rollout">{current.data.document.rollout.enabled ? "Enabled" : "Disabled"}</Detail></DetailGrid></Surface>
    <Surface><div className="space-y-4"><Input id="configuration-environment" label="Environment" required value={environment} onChange={event => { setEnvironment(event.target.value); setPreviewedDraft(""); }}/><Textarea id="configuration-document" aria-label="Configuration document" rows={28} value={draft} onChange={event => { setDraft(event.target.value); setPreviewedDraft(""); }}/><p className="text-xs text-muted-foreground">Limits, allow-lists, lifecycle transitions, list preferences, navigation, rollout, and RBAC are validated server-side. Save remains unavailable until this exact document passes preview.</p>{localError ? <p role="alert" className="text-sm text-destructive">{localError}</p> : null}<div className="flex justify-end gap-3"><Button variant="outline" disabled={!previewDocument || preview.isPending} onClick={() => preview.mutate()}><Eye className="mr-2 h-4 w-4"/>{preview.isPending ? "Simulating…" : "Preview changes"}</Button><Button disabled={!previewCurrent || save.isPending} onClick={() => save.mutate()}><Save className="mr-2 h-4 w-4"/>{save.isPending ? "Applying…" : imported ? "Import configuration" : "Apply configuration"}</Button></div></div></Surface>
    {preview.data ? <Surface><h2 className="font-semibold">Server preview</h2><pre className="mt-3 max-h-80 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(preview.data.changes, null, 2)}</pre><p className="mt-2 text-xs text-muted-foreground">{preview.data.requires_restart ? "Applying this change requires a restart." : "This change applies without a restart."}</p></Surface> : null}
    {save.error ? <GovernedError error={save.error}/> : null}
    <div className="grid gap-6 xl:grid-cols-2">
      <Surface><h2 className="font-semibold">Version history and rollback</h2>{versions.data.data.length ? <ul className="mt-3 divide-y">{versions.data.data.map(version => <li key={version.id} className="flex items-center justify-between gap-3 py-3"><div><p className="font-medium">Version {version.version} · {version.environment}</p><p className="font-mono text-xs text-muted-foreground">{version.correlation_id} · {formatDate(version.created_at)}</p></div><Button variant="outline" size="sm" disabled={version.version === current.data.version} onClick={() => setRollbackVersion(version)}><RotateCcw className="mr-2 h-4 w-4"/>Rollback</Button></li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No immutable versions were returned.</p>}</Surface>
      <Surface><h2 className="font-semibold">Immutable audit history</h2>{audit.data.data.length ? <ul className="mt-3 divide-y">{audit.data.data.map(record => <li key={record.id} className="py-3"><p className="font-medium">{record.action} · version {record.version}</p><p className="font-mono text-xs text-muted-foreground">{record.correlation_id}</p><p className="text-xs text-muted-foreground">{record.actor_id} · {formatDate(record.created_at)}</p></li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No audit records were returned.</p>}</Surface>
    </div>
    <ConfirmAction open={rollbackVersion !== null} title={`Rollback to version ${rollbackVersion?.version ?? ""}?`} description="Rollback creates a new immutable version; it never rewrites history." confirmLabel="Create rollback version" pending={rollback.isPending} onOpenChange={open => { if (!open) setRollbackVersion(null); }} onConfirm={() => { if (rollbackVersion) rollback.mutate(rollbackVersion); }}/>
    {rollback.error ? <GovernedError error={rollback.error}/> : null}
  </main>;
}
