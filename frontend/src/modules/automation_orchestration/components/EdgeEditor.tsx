import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import type { EdgeCondition, OrchestrationEdgeDTO, OrchestrationNodeDTO } from "../contracts";
import { automationOrchestrationService as service } from "../services/automation-orchestration-service";

export function EdgeEditor({ definitionId, selectedNodeId, nodes, edges, onChanged }: {
  definitionId: string;
  selectedNodeId: string;
  nodes: readonly OrchestrationNodeDTO[];
  edges: readonly OrchestrationEdgeDTO[];
  onChanged: () => void;
}) {
  const [downstreamId, setDownstreamId] = useState("");
  const [condition, setCondition] = useState<EdgeCondition>("on_success");
  const create = useMutation({
    mutationFn: () => service.createEdge(definitionId, { upstream_node_id: selectedNodeId, downstream_node_id: downstreamId, condition }),
    onSuccess: () => { setDownstreamId(""); onChanged(); },
  });
  const remove = useMutation({ mutationFn: (edgeId: string) => service.deleteEdge(edgeId), onSuccess: onChanged });
  const outgoing = edges.filter((edge) => edge.upstream_node_id === selectedNodeId);
  const selected = nodes.find((node) => node.id === selectedNodeId);
  const error = create.error ?? remove.error;

  return <Card><CardHeader><CardTitle className="flex items-center gap-2"><Link2 className="h-5 w-5" />Dependency edges</CardTitle></CardHeader><CardContent className="grid gap-5 lg:grid-cols-2"><div className="space-y-3"><p className="text-sm text-muted-foreground">Create an explicit conditional dependency from the selected node.</p>{!selected ? <p className="rounded border border-amber-500/40 p-3 text-sm text-amber-700">Select an upstream node on the canvas first.</p> : <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto]"><select aria-label="Downstream node" value={downstreamId} onChange={(event) => setDownstreamId(event.target.value)} className="h-10 rounded-md border bg-background px-3 text-sm"><option value="">Choose downstream node</option>{nodes.filter((node) => node.id !== selectedNodeId).map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</select><select aria-label="Edge condition" value={condition} onChange={(event) => setCondition(event.target.value as EdgeCondition)} className="h-10 rounded-md border bg-background px-3 text-sm"><option value="on_success">On success</option><option value="on_failure">On failure</option><option value="always">Always</option></select><Button disabled={!downstreamId || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Connecting…" : "Connect"}</Button></div>}{error ? <p role="alert" className="text-sm text-destructive">{error.message}</p> : null}</div><div><p className="text-sm font-medium">Outgoing from {selected?.name ?? "selected node"}</p>{outgoing.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No outgoing edges.</p> : <ul className="mt-2 divide-y">{outgoing.map((edge) => { const downstream = nodes.find((node) => node.id === edge.downstream_node_id); return <li key={edge.id} className="flex items-center justify-between py-2 text-sm"><span>{downstream?.name ?? edge.downstream_node_id}<small className="ml-2 text-muted-foreground">{edge.condition.replace("_", " ")}</small></span><Button aria-label={`Remove edge to ${downstream?.name ?? "node"}`} size="icon" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(edge.id)}><Trash2 className="h-4 w-4" /></Button></li>; })}</ul>}</div></CardContent></Card>;
}
