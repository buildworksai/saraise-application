import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, X } from "lucide-react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TaskDecisionDialog } from "../components/TaskDecisionDialog";
import { WorkflowApiError, workflowService } from "../services/workflow-service";
import { PageHeader, PageSkeleton, StatusPill, WorkflowProblem } from "../components/WorkflowUI";
import { formatDate, newTransitionKey } from "../workflow-utils";

function safeValue(value: string | number | boolean | null): string { return value === null ? "—" : String(value); }
export function WorkflowTaskDetailPage() {
  const { id = "" } = useParams(); const cache = useQueryClient(); const [decision, setDecision] = useState<"complete" | "reject" | null>(null); const [result, setResult] = useState("");
  const query = useQuery({ queryKey: ["workflow-task", id], queryFn: () => workflowService.tasks.get(id), enabled: Boolean(id) });
  const mutation = useMutation({ mutationFn: (reason: string) => decision === "reject" ? workflowService.tasks.reject(id, { reason, meta_data: {}, transition_key: newTransitionKey("reject") }) : workflowService.tasks.complete(id, { meta_data: {}, transition_key: newTransitionKey("complete") }), onSuccess: (task) => { setResult(`Decision recorded once: ${task.status}.`); setDecision(null); void cache.invalidateQueries({ queryKey: ["workflow-task", id] }); } });
  if (query.isLoading) return <PageSkeleton label="Loading workflow task"/>;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()}/>;
  const task = query.data; if (!task) return <WorkflowProblem error={new Error("Task not found") } retry={() => void query.refetch()}/>;
  const stale = mutation.error instanceof WorkflowApiError && mutation.error.status === 409;
  return <main className="space-y-6"><PageHeader eyebrow={`${task.workflow_name} · version ${task.workflow_version}`} title={task.step_name} description={task.subject ?? "Human workflow decision"} actions={<>{task.allowed_actions.includes("reject") ? <Button variant="outline" onClick={() => setDecision("reject")}><X className="mr-2 h-4 w-4"/>Reject</Button> : null}{task.allowed_actions.includes("complete") ? <Button onClick={() => setDecision("complete")}><Check className="mr-2 h-4 w-4"/>Approve / complete</Button> : null}</>}/>{result ? <div role="status" className="rounded border border-emerald-500/40 p-3 text-sm">{result}</div> : null}{stale ? <div role="alert" className="rounded border border-amber-500/40 p-3 text-sm">The task already changed. Your duplicate decision was not applied. Reload to view the recorded evidence.</div> : null}
    <div className="grid gap-4 md:grid-cols-4"><Card className="p-4"><p className="text-xs text-muted-foreground">Status</p><div className="mt-2"><StatusPill status={task.status}/></div></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Assignment</p><p className="mt-2 font-medium">{task.assignment_label}</p></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Due</p><p className="mt-2 font-medium">{formatDate(task.due_date)}</p></Card><Card className="p-4"><p className="text-xs text-muted-foreground">Correlation</p><button className="mt-2 flex items-center gap-2 font-mono text-xs" onClick={() => void navigator.clipboard.writeText(task.correlation_id)}>{task.correlation_id}<Copy className="h-3 w-3"/></button></Card></div>
    <div className="grid gap-5 xl:grid-cols-2"><Card className="p-5"><h2 className="text-lg font-semibold">Permitted business context</h2><p className="mt-1 text-xs text-muted-foreground">Only fields explicitly exposed by the subject resolver are shown.</p><dl className="mt-4 divide-y">{Object.entries(task.safe_context).map(([key, value]) => <div key={key} className="flex justify-between gap-4 py-3"><dt className="text-sm text-muted-foreground">{key}</dt><dd className="max-w-sm break-words text-right text-sm">{typeof value === "object" ? "Structured value hidden" : safeValue(value)}</dd></div>)}</dl></Card><Card className="p-5"><h2 className="text-lg font-semibold">Decision history</h2><ol className="mt-4 space-y-4 border-l pl-5">{task.transition_history.map((transition) => <li key={transition.transition_key}><p className="font-medium">{transition.command}: {transition.from_state} → {transition.to_state}</p><p className="text-xs text-muted-foreground">{formatDate(transition.occurred_at)}</p></li>)}</ol>{task.completed_by_name ? <p className="mt-4 text-sm">Completed by {task.completed_by_name} at {formatDate(task.completed_at)}</p> : null}</Card></div>
    <TaskDecisionDialog open={decision !== null} decision={decision ?? "complete"} taskName={task.step_name} pending={mutation.isPending} error={mutation.error} onOpenChange={(open) => { if (!open) setDecision(null); }} onSubmit={(reason) => mutation.mutate(reason)}/>
  </main>;
}
