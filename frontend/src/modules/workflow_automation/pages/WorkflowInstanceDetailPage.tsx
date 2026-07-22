import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Copy } from "lucide-react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { useState } from "react";
import { workflowService } from "../services/workflow-service";
import { PageHeader, PageSkeleton, StatusPill, WorkflowProblem } from "../components/WorkflowUI";
import { formatDate, formatDuration, newTransitionKey } from "../workflow-utils";

const terminal = new Set(["completed", "failed", "cancelled"]);
export function WorkflowInstanceDetailPage() {
  const { id = "" } = useParams(); const cache = useQueryClient(); const [confirmCancel, setConfirmCancel] = useState(false);
  const query = useQuery({ queryKey: ["workflow-instance", id], queryFn: () => workflowService.instances.get(id), enabled: Boolean(id), refetchInterval: (state) => state.state.data && !terminal.has(state.state.data.state) && document.visibilityState === "visible" ? 5000 : false });
  const cancel = useMutation({ mutationFn: () => workflowService.instances.cancel(id, { transition_key: newTransitionKey("cancel"), reason: "Cancelled by user" }), onSuccess: () => void cache.invalidateQueries({ queryKey: ["workflow-instance", id] }) });
  if (query.isLoading) return <PageSkeleton label="Loading workflow execution"/>;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()}/>;
  const instance = query.data; if (!instance) return <WorkflowProblem error={new Error("Execution not found") } retry={() => void query.refetch()}/>;
  return <main className="space-y-6"><PageHeader eyebrow={`Execution · ${instance.workflow_name} v${instance.workflow_version}`} title={instance.subject ?? "Workflow execution"} description={`Started ${formatDate(instance.started_at ?? instance.created_at)} · ${formatDuration(instance.started_at ?? instance.created_at, instance.completed_at)}`} actions={instance.allowed_actions.includes("cancel") && !terminal.has(instance.state) ? <Button variant="danger" onClick={() => setConfirmCancel(true)}><Ban className="mr-2 h-4 w-4"/>Cancel execution</Button> : undefined}/>
    <div className="grid gap-4 md:grid-cols-4"><Card className="p-4"><p className="text-xs text-muted-foreground">State</p><div className="mt-2"><StatusPill status={instance.state}/></div></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Current step</p><p className="mt-2 font-medium">{instance.current_step_name ?? "—"}</p></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Priority</p><p className="mt-2 text-2xl font-semibold">{instance.priority}</p></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Correlation</p><button className="mt-2 flex items-center gap-2 font-mono text-xs" onClick={() => void navigator.clipboard.writeText(instance.correlation_id)}>{instance.correlation_id}<Copy className="h-3 w-3"/></button></Card></div>
    {instance.state === "failed" ? <div role="alert" className="rounded border border-destructive/40 p-4"><h2 className="font-semibold text-destructive">{instance.failure_code}</h2><p className="mt-1 text-sm">{instance.failure_message || "The workflow stopped with a sanitized failure."}</p></div> : null}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]"><Card className="p-5"><h2 className="text-lg font-semibold">Immutable transition timeline</h2><ol className="mt-5 space-y-4 border-l pl-5">{instance.transition_history.map((transition) => <li key={transition.transition_key} className="relative"><span className="absolute -left-[25px] top-1 h-2 w-2 rounded-full bg-primary"/><p className="font-medium">{transition.command}: {transition.from_state} → {transition.to_state}</p><p className="text-xs text-muted-foreground">{formatDate(transition.occurred_at)} · {transition.correlation_id}</p></li>)}</ol></Card><Card className="p-5"><h2 className="text-lg font-semibold">Human tasks</h2><ul className="mt-4 space-y-3">{instance.tasks.length ? instance.tasks.map((task) => <li key={task.id} className="rounded border p-3"><div className="flex justify-between gap-2"><p className="font-medium">{task.step_name}</p><StatusPill status={task.status}/></div><p className="mt-1 text-xs text-muted-foreground">{task.assignment_label} · due {formatDate(task.due_date)}</p></li>) : <li className="text-sm text-muted-foreground">No human tasks were created.</li>}</ul></Card></div>
    <ConfirmDialog open={confirmCancel} onOpenChange={setConfirmCancel} title="Cancel this execution?" description="The durable job and every open task will be cancelled. Immutable history remains available." confirmLabel={cancel.isPending ? "Cancelling…" : "Cancel execution"} variant="danger" onConfirm={() => cancel.mutate()}/>
  </main>;
}
