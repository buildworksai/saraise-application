import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Minus, Plus, Save, ShieldCheck, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useDefinition, useNodeTypes, orchestrationKeys } from "../hooks/use-orchestration";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";
import type { NodeDescriptorDTO } from "../contracts";
import { LoadError, PageHeader, PageSkeleton, PermissionDenied, StatusPill } from "../components/OrchestrationUI";
import { Topology } from "../components/Topology";
import { EdgeEditor } from "../components/EdgeEditor";

// The builder keeps every catalog, graph, permission, and validation state explicit.
// eslint-disable-next-line complexity
export function DefinitionEditPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const definitionQuery = useDefinition(id);
  const catalogQuery = useNodeTypes();
  const [selectedNode, setSelectedNode] = useState("");
  const [zoom, setZoom] = useState(100);
  const [validationOpen, setValidationOpen] = useState(false);
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: orchestrationKeys.definition(id) });
  const addNode = useMutation({ mutationFn: (descriptor: NodeDescriptorDTO) => service.createNode(id, { key: `${descriptor.key.replace(/[^a-z0-9]+/g, "-")}-${Date.now().toString().slice(-5)}`, name: descriptor.display_name, node_type: descriptor.source_module === "automation_orchestration" ? "internal" : "extension", handler_key: descriptor.key, config: {}, input_mapping: {} }), onSuccess: (node) => { setSelectedNode(node.id); invalidate(); } });
  const removeNode = useMutation({ mutationFn: (nodeId: string) => service.deleteNode(nodeId), onSuccess: () => { setSelectedNode(""); invalidate(); } });
  const validate = useMutation({ mutationFn: () => service.validateDefinition(id), onSuccess: () => setValidationOpen(true) });
  const pending = addNode.isPending || removeNode.isPending;

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (pending) event.preventDefault(); };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [pending]);

  const definition = definitionQuery.data;
  const selected = definition?.nodes.find((node) => node.id === selectedNode);
  const grouped = useMemo(() => {
    const groups = new Map<string, NodeDescriptorDTO[]>();
    for (const descriptor of catalogQuery.data ?? []) {
      const items = groups.get(descriptor.category) ?? [];
      items.push(descriptor);
      groups.set(descriptor.category, items);
    }
    return Array.from(groups.entries());
  }, [catalogQuery.data]);

  if (definitionQuery.isLoading) return <PageSkeleton />;
  if (definitionQuery.error) return <LoadError error={definitionQuery.error} retry={() => void definitionQuery.refetch()} />;
  if (!definition) return <LoadError error={new Error("Definition not found.")} retry={() => void definitionQuery.refetch()} />;
  if (definition.status !== "draft") return <PermissionDenied />;

  const localIssues = definition.nodes.length === 0 ? ["Add at least one root node before publication."] : [];
  const mutationError = addNode.error ?? removeNode.error;

  return (
    <main className="space-y-5">
      <PageHeader eyebrow={`${definition.key} · draft v${definition.version}`} title="Graph builder" description="Compose the DAG with the palette or keyboard controls, then validate against the authoritative server contract." actions={<><Button variant="outline" onClick={() => validate.mutate()} disabled={validate.isPending}><ShieldCheck className="mr-2 h-4 w-4" />Server validate</Button><Button onClick={() => navigate(`/automation-orchestration/definitions/${id}`)}><Save className="mr-2 h-4 w-4" />Done</Button></>} />
      {mutationError ? <div role="alert" className="rounded border border-destructive/40 p-3 text-sm text-destructive">{mutationError.message}</div> : null}
      <div className="grid min-h-[620px] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_300px]">
        <aside aria-label="Node palette" className="rounded-xl border bg-card p-4"><h2 className="font-semibold">Node palette</h2><p className="mt-1 text-xs text-muted-foreground">Drag to the canvas or choose Add for keyboard access.</p>{catalogQuery.isLoading ? <p className="mt-5 text-sm">Loading accessible node types…</p> : catalogQuery.error ? <p role="alert" className="mt-5 text-sm text-destructive">Node catalog unavailable.</p> : grouped.length === 0 ? <p className="mt-5 text-sm text-muted-foreground">No entitled node types are currently available.</p> : <div className="mt-5 space-y-5">{grouped.map(([category, descriptors]) => <section key={category}><h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{category}</h3><div className="space-y-2">{descriptors.map((descriptor) => <div key={descriptor.key} draggable={descriptor.availability === "available"} onDragStart={(event) => event.dataTransfer.setData("text/plain", descriptor.key)} className="rounded-lg border p-3"><div className="flex justify-between gap-2"><div><p className="text-sm font-medium">{descriptor.display_name}</p><p className="text-xs text-muted-foreground">{descriptor.description}</p></div><Button aria-label={`Add ${descriptor.display_name}`} size="icon" variant="ghost" disabled={descriptor.availability !== "available" || addNode.isPending} onClick={() => addNode.mutate(descriptor)}><Plus className="h-4 w-4" /></Button></div>{descriptor.availability !== "available" ? <p className="mt-2 text-xs text-amber-600">{descriptor.availability_reason ?? descriptor.availability}</p> : null}</div>)}</div></section>)}</div>}</aside>
        <section aria-label="Graph canvas" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { const key = event.dataTransfer.getData("text/plain"); const descriptor = catalogQuery.data?.find((item) => item.key === key); if (descriptor?.availability === "available") addNode.mutate(descriptor); }} className="space-y-3"><div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2"><span className="text-xs text-muted-foreground">{pending ? "Saving graph change…" : "All server changes saved"}</span><div className="flex items-center gap-1"><Button size="icon" variant="ghost" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(60, value - 10))}><ZoomOut className="h-4 w-4" /></Button><span className="w-12 text-center text-xs">{zoom}%</span><Button size="icon" variant="ghost" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(160, value + 10))}><ZoomIn className="h-4 w-4" /></Button></div></div><div style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top left", width: `${10000 / zoom}%` }}><Topology nodes={definition.nodes} edges={definition.edges} selectedNodeId={selectedNode} onSelect={setSelectedNode} /></div>{localIssues.map((issue) => <p key={issue} role="alert" className="rounded border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700">{issue}</p>)}</section>
        <aside aria-label="Node configuration" className="rounded-xl border bg-card p-4"><h2 className="font-semibold">Configuration</h2>{selected ? <div className="mt-5 space-y-4"><div><p className="font-medium">{selected.name}</p><p className="text-xs text-muted-foreground">{selected.handler_key}</p></div><Input label="Node key" value={selected.key} readOnly /><Input label="Timeout" value={selected.timeout_seconds ?? definition.default_timeout_seconds} readOnly /><Input label="Maximum attempts" value={selected.max_attempts ?? definition.default_max_attempts} readOnly /><p className="text-xs text-muted-foreground">Schema-driven configuration is validated by the registered node descriptor. Secrets are never accepted in graph JSON.</p><Button variant="danger" className="w-full" disabled={removeNode.isPending} onClick={() => { if (window.confirm(`Remove ${selected.name}? Connected edges are protected.`)) removeNode.mutate(selected.id); }}><Trash2 className="mr-2 h-4 w-4" />Remove node</Button></div> : <p className="mt-5 text-sm text-muted-foreground">Select a node to inspect its retry, timeout, mapping, and schema configuration.</p>}</aside>
      </div>
      {validationOpen && validate.data ? <Card className={validate.data.valid ? "border-emerald-500/40" : "border-destructive/40"}><CardHeader className="flex-row items-center justify-between"><CardTitle>{validate.data.valid ? "Graph is publishable" : "Graph needs attention"}</CardTitle><Button variant="ghost" size="icon" aria-label="Close validation" onClick={() => setValidationOpen(false)}><Minus /></Button></CardHeader><CardContent>{validate.data.issues.length === 0 ? <p className="text-sm text-muted-foreground">All handlers, dependencies, schemas, and limits passed validation.</p> : <ul className="space-y-2">{validate.data.issues.map((issue) => <li key={`${issue.code}-${issue.entity_id}`} className="rounded border p-3 text-sm"><StatusPill status={issue.severity} /> <strong className="ml-2">{issue.code}</strong><p className="mt-1">{issue.message}</p>{issue.remediation ? <p className="mt-1 text-muted-foreground">{issue.remediation}</p> : null}</li>)}</ul>}</CardContent></Card> : null}
      <EdgeEditor definitionId={id} selectedNodeId={selectedNode} nodes={definition.nodes} edges={definition.edges} onChanged={invalidate} />
    </main>
  );
}
