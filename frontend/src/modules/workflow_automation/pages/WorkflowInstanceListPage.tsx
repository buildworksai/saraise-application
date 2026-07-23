import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import type { InstanceOrdering, InstanceState } from "../contracts";
import { ROUTES } from "../contracts";
import { workflowService } from "../services/workflow-service";
import { EmptyPanel, PageHeader, PageSkeleton, Pagination, StatusPill, WorkflowProblem } from "../components/WorkflowUI";
import { formatDuration } from "../workflow-utils";
import { useWorkflowConfiguration } from "../hooks/use-workflow-configuration";

const selectClass = "rounded-md border border-input bg-background px-3 py-2 text-sm";
export function WorkflowInstanceListPage() {
  const navigate = useNavigate(); const [page, setPage] = useState(1); const [search, setSearch] = useState(""); const deferredSearch = useDeferredValue(search); const [state, setState] = useState<InstanceState | "">(""); const [entityType, setEntityType] = useState(""); const [ordering, setOrdering] = useState<InstanceOrdering>("-created_at");
  const configuration = useWorkflowConfiguration();
  const policy = configuration.data?.document;
  const filters = { page, page_size: policy?.limits.workflow_page_size, search: deferredSearch || undefined, state: state || undefined, entity_type: entityType || undefined, ordering };
  const query = useQuery({ queryKey: ["workflow-instances", filters], queryFn: () => workflowService.instances.list(filters), enabled: Boolean(policy), refetchInterval: document.visibilityState === "visible" ? policy?.operational.execution_poll_interval_ms : false });
  if (query.isLoading) return <PageSkeleton label="Loading workflow executions"/>;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()}/>;
  return <main className="space-y-6"><PageHeader title="Executions" description="Monitor durable workflow progress, waiting tasks, failures, and immutable evidence."/><Card className="grid gap-3 p-4 md:grid-cols-4"><Input aria-label="Search executions" placeholder="Workflow, entity, correlation ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}/><select aria-label="Filter state" className={selectClass} value={state} onChange={(event) => setState(event.target.value as InstanceState | "")}><option value="">All states</option>{["pending","running","waiting","completed","failed","cancelled"].map((value) => <option key={value}>{value}</option>)}</select><Input aria-label="Filter entity type" placeholder="Entity type" value={entityType} onChange={(event) => setEntityType(event.target.value)}/><select aria-label="Order executions" className={selectClass} value={ordering} onChange={(event) => setOrdering(event.target.value as InstanceOrdering)}><option value="-created_at">Newest</option><option value="-priority">Highest priority</option><option value="completed_at">Completion time</option></select></Card>
    {!query.data?.items.length ? <EmptyPanel title="No executions found" description="Published manual workflows appear here after a real durable start is accepted."/> : <Card className="overflow-x-auto"><table className="w-full min-w-[880px]"><thead><tr className="border-b text-left text-xs uppercase text-muted-foreground"><th className="p-4">Workflow / subject</th><th>State</th><th>Current step</th><th>Priority</th><th>Elapsed</th><th>Failure</th><th className="p-4 text-right">View</th></tr></thead><tbody>{query.data.items.map((instance) => <tr key={instance.id} className="border-b last:border-0"><td className="p-4"><button className="font-medium text-primary hover:underline" onClick={() => navigate(ROUTES.INSTANCE_DETAIL(instance.id))}>{instance.workflow_name} · v{instance.workflow_version}</button><p className="text-xs text-muted-foreground">{instance.subject ?? (instance.entity_type || "Manual execution")}</p></td><td><StatusPill status={instance.state}/></td><td>{instance.current_step_name ?? "—"}</td><td>{instance.priority}</td><td>{policy ? formatDuration(instance.started_at ?? instance.created_at, instance.completed_at, policy.ui.duration_display_threshold_ms) : "—"}</td><td className="max-w-48 truncate text-sm text-destructive">{instance.failure_code || "—"}</td><td className="p-4 text-right"><Button size="icon" variant="ghost" aria-label={`View ${instance.workflow_name} execution`} onClick={() => navigate(ROUTES.INSTANCE_DETAIL(instance.id))}><Eye className="h-4 w-4"/></Button></td></tr>)}</tbody></table><div className="px-4 pb-4"><Pagination page={query.data.pagination.page} totalPages={query.data.pagination.total_pages} onPage={setPage}/></div></Card>}
  </main>;
}
