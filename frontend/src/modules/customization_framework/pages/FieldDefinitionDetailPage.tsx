/* eslint-disable complexity -- lifecycle, impact, rollback, and evidence states are explicit. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Edit, GitBranch, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { CapabilityNotice, ConfirmAction, Detail, DetailGrid, GovernedError, PageHeader, PageSkeleton, StatusChip, Surface } from "../components/CustomizationUI";
import { formatDate } from "../components/customization-utils";
import { ROUTES, type FieldDefinitionVersion, type FieldStatus } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

export function FieldDefinitionDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [command, setCommand] = useState<"activate" | "deprecate" | "retire" | null>(null);
  const [rollbackVersion, setRollbackVersion] = useState<FieldDefinitionVersion | null>(null);
  const field = useQuery({ queryKey: ["customization", "field", id], queryFn: () => service.getField(id), enabled: Boolean(id) });
  const impact = useQuery({ queryKey: ["customization", "field-impact", id], queryFn: () => service.getFieldImpact(id), enabled: Boolean(id) });
  const versions = useQuery({ queryKey: ["customization", "field-versions", id], queryFn: () => service.listFieldVersions(id), enabled: Boolean(id) });
  const transition = useMutation({ mutationFn: (next: "activate" | "deprecate" | "retire") => service.transitionField(id, next, { transition_key: crypto.randomUUID() }), onSuccess: () => { setCommand(null); void client.invalidateQueries({ queryKey: ["customization", "field", id] }); } });
  const rollback = useMutation({
    mutationFn: (version: FieldDefinitionVersion) => {
      if (!field.data) throw new Error("The current field revision is unavailable.");
      return service.rollbackField(id, { target_version: version.version, expected_lock_version: field.data.data.lock_version });
    },
    onSuccess: () => { setRollbackVersion(null); void client.invalidateQueries({ queryKey: ["customization", "field", id] }); void client.invalidateQueries({ queryKey: ["customization", "field-versions", id] }); },
  });
  if (field.isLoading || impact.isLoading || versions.isLoading) return <PageSkeleton/>;
  const queryError = field.error ?? impact.error ?? versions.error;
  if (queryError) return <GovernedError error={queryError} retry={() => { void field.refetch(); void impact.refetch(); void versions.refetch(); }}/>;
  if (!field.data || !impact.data || !versions.data) return <GovernedError error={new Error("The governed field response is incomplete.")}/>;
  const item = field.data.data;
  const next: Partial<Record<FieldStatus, "activate" | "deprecate" | "retire">> = { draft: "activate", active: "deprecate", deprecated: "retire" };
  return <main className="space-y-6">
    <PageHeader title={item.label} description={`${item.owner_module} · ${item.target_resource} · contract ${item.target_contract_version}`} actions={<><Button variant="outline" onClick={() => navigate(ROUTES.FIELD_IMPACT(item.id))}><GitBranch className="mr-2 h-4 w-4"/>Impact</Button><Button variant="outline" onClick={() => navigate(ROUTES.FIELD_EDIT(item.id))}><Edit className="mr-2 h-4 w-4"/>Edit</Button>{next[item.status] ? <Button disabled={item.capability_state === "capability_unavailable"} onClick={() => setCommand(next[item.status] ?? null)}>{next[item.status]}</Button> : null}</>}/>
    <CapabilityNotice state={item.capability_state}/>
    <Surface><DetailGrid><Detail label="Stable key"><span className="font-mono">{item.key}</span></Detail><Detail label="Data type">{item.data_type}</Detail><Detail label="Status"><StatusChip status={item.status}/></Detail><Detail label="Required">{item.required ? "Yes" : "No"}</Detail><Detail label="Searchable">{item.searchable ? "Yes" : "No"}</Detail><Detail label="Lock revision">{item.lock_version}</Detail></DetailGrid></Surface>
    <div className="grid gap-6 lg:grid-cols-2"><Surface><h2 className="font-semibold">Schema and default</h2><p className="mt-2 text-sm text-muted-foreground">{item.description || "No description"}</p><pre className="mt-4 max-h-72 overflow-auto rounded-lg bg-muted p-3 text-xs">{JSON.stringify({ validation: item.validation_schema, presentation: item.presentation_schema, default: item.default_value }, null, 2)}</pre></Surface><Surface><h2 className="flex items-center gap-2 font-semibold"><Activity className="h-4 w-4"/>Usage and impact</h2><div className="mt-4 grid grid-cols-3 gap-3 text-center"><div><strong className="block text-2xl">{impact.data.data.value_count ?? "—"}</strong><span className="text-xs text-muted-foreground">stored values</span></div><div><strong className="block text-2xl">{impact.data.data.dependency_count}</strong><span className="text-xs text-muted-foreground">dependencies</span></div><div><strong className="block text-2xl">{impact.data.data.blocking ? "Yes" : "No"}</strong><span className="text-xs text-muted-foreground">change blocked</span></div></div></Surface></div>
    <Surface><h2 className="font-semibold">Immutable versions and rollback</h2>{versions.data.data.length ? <ul className="mt-3 divide-y">{versions.data.data.map(version => <li key={version.id} className="flex items-center justify-between gap-3 py-3"><div><p className="font-medium">Version {version.version}</p><p className="font-mono text-xs text-muted-foreground">{version.content_hash} · {version.correlation_id}</p><p className="text-xs text-muted-foreground">{formatDate(version.created_at)}</p></div><Button variant="outline" size="sm" onClick={() => setRollbackVersion(version)}><RotateCcw className="mr-2 h-4 w-4"/>Rollback</Button></li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">No immutable versions were returned.</p>}</Surface>
    <ConfirmAction open={command !== null} title={`${command ?? "Change"} field?`} description="This governed lifecycle change is audited and may affect dependent forms and rules." confirmLabel={command ?? "Confirm"} pending={transition.isPending} onOpenChange={open => { if (!open) setCommand(null); }} onConfirm={() => { if (command) transition.mutate(command); }}/>
    {transition.error ? <GovernedError error={transition.error}/> : null}
    <ConfirmAction open={rollbackVersion !== null} title={`Rollback to version ${rollbackVersion?.version ?? ""}?`} description="Rollback creates a new immutable version and never rewrites historical evidence." confirmLabel="Create rollback version" pending={rollback.isPending} onOpenChange={open => { if (!open) setRollbackVersion(null); }} onConfirm={() => { if (rollbackVersion) rollback.mutate(rollbackVersion); }}/>
    {rollback.error ? <GovernedError error={rollback.error}/> : null}
  </main>;
}
