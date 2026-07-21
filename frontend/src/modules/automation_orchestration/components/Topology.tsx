import type { OrchestrationEdgeDTO, OrchestrationNodeDTO, TaskRunListDTO } from "../contracts";
import { StatusPill } from "./OrchestrationUI";

export function Topology({
  nodes,
  edges,
  taskRuns = [],
  selectedNodeId,
  onSelect,
}: {
  nodes: readonly OrchestrationNodeDTO[];
  edges: readonly OrchestrationEdgeDTO[];
  taskRuns?: readonly TaskRunListDTO[];
  selectedNodeId?: string;
  onSelect?: (nodeId: string) => void;
}) {
  const taskByNode = new Map(taskRuns.map((task) => [task.node_id, task]));
  return (
    <div className="relative min-h-72 overflow-auto rounded-xl border bg-[radial-gradient(circle_at_1px_1px,hsl(var(--border))_1px,transparent_0)] bg-[size:24px_24px] p-6">
      <div className="grid min-w-[520px] grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" role="list" aria-label="Orchestration graph nodes">
        {nodes.map((node) => {
          const task = taskByNode.get(node.id);
          const incoming = edges.filter((edge) => edge.downstream_node_id === node.id);
          return (
            <button
              type="button"
              role="listitem"
              key={node.id}
              aria-pressed={selectedNodeId === node.id}
              onClick={() => onSelect?.(node.id)}
              className={`rounded-lg border bg-card p-4 text-left shadow-sm transition hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedNodeId === node.id ? "border-primary ring-2 ring-primary/20" : ""}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div><p className="font-medium">{node.name}</p><p className="text-xs text-muted-foreground">{node.handler_key}</p></div>
                {task ? <StatusPill status={task.status} /> : null}
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                {incoming.length === 0 ? "Root node" : `${incoming.length} dependenc${incoming.length === 1 ? "y" : "ies"}`}
              </p>
            </button>
          );
        })}
      </div>
      <div className="absolute bottom-3 right-3 rounded border bg-background/90 px-2 py-1 text-[11px] text-muted-foreground">Minimap · {nodes.length} nodes · {edges.length} edges</div>
    </div>
  );
}
