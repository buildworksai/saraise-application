import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Copy, Eye, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import type { WorkflowListDTO, WorkflowOrdering, WorkflowStatus, WorkflowType } from "../contracts";
import { ROUTES } from "../contracts";
import { workflowService } from "../services/workflow-service";
import { EmptyPanel, PageHeader, PageSkeleton, Pagination, StatusPill, WorkflowProblem } from "../components/WorkflowUI";
import { newTransitionKey } from "../workflow-utils";
import { useWorkflowConfiguration } from "../hooks/use-workflow-configuration";

const selectClass = "rounded-md border border-input bg-background px-3 py-2 text-sm";
// Lifecycle affordances are independently permission-gated for every row.
// eslint-disable-next-line complexity
export function WorkflowListPage() {
  const navigate = useNavigate(); const cache = useQueryClient();
  const configuration = useWorkflowConfiguration();
  const [page, setPage] = useState(1); const [search, setSearch] = useState(""); const deferredSearch = useDeferredValue(search);
  const [status, setStatus] = useState<WorkflowStatus | "">(""); const [type, setType] = useState<WorkflowType | "">(""); const [ordering, setOrdering] = useState<WorkflowOrdering>("-updated_at");
  const [deleting, setDeleting] = useState<WorkflowListDTO | null>(null);
  const pageSize = configuration.data?.document.limits.workflow_page_size;
  const filters = { page, page_size: pageSize, search: deferredSearch || undefined, status: status || undefined, workflow_type: type || undefined, ordering };
  const query = useQuery({ queryKey: ["workflow-definitions", filters], queryFn: () => workflowService.workflows.list(filters), enabled: Boolean(pageSize) });
  const refresh = (): void => { void cache.invalidateQueries({ queryKey: ["workflow-definitions"] }); };
  const publish = useMutation({ mutationFn: (id: string) => workflowService.workflows.publish(id, { transition_key: newTransitionKey("publish") }), onSuccess: refresh });
  const archive = useMutation({ mutationFn: (id: string) => workflowService.workflows.archive(id, { transition_key: newTransitionKey("archive") }), onSuccess: refresh });
  const clone = useMutation({ mutationFn: (id: string) => workflowService.workflows.clone(id), onSuccess: (workflow) => navigate(ROUTES.WORKFLOW_EDIT(workflow.id)) });
  const remove = useMutation({ mutationFn: (id: string) => workflowService.workflows.delete(id), onSuccess: () => { setDeleting(null); refresh(); } });
  const clear = (): void => { setSearch(""); setStatus(""); setType(""); setOrdering("-updated_at"); setPage(1); };
  if (query.isLoading) return <PageSkeleton label="Loading workflow definitions"/>;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()}/>;
  const result = query.data; const filtered = Boolean(search || status || type || ordering !== "-updated_at");
  return <main className="space-y-6"><PageHeader title="Workflows" description="Design immutable, tenant-safe business workflows and publish them when every path validates." actions={<Button onClick={() => navigate(ROUTES.WORKFLOW_CREATE)}><Plus className="mr-2 h-4 w-4"/>Create workflow</Button>}/>
    <Card className="grid gap-3 p-4 md:grid-cols-4"><Input aria-label="Search workflows" placeholder="Search name, description, or key" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}/><select aria-label="Filter status" className={selectClass} value={status} onChange={(event) => { setStatus(event.target.value as WorkflowStatus | ""); setPage(1); }}><option value="">All statuses</option><option value="draft">Draft</option><option value="published">Published</option><option value="archived">Archived</option></select><select aria-label="Filter workflow type" className={selectClass} value={type} onChange={(event) => { setType(event.target.value as WorkflowType | ""); setPage(1); }}><option value="">All types</option>{["approval","state_machine","sequential","parallel","conditional"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Order workflows" className={selectClass} value={ordering} onChange={(event) => setOrdering(event.target.value as WorkflowOrdering)}><option value="-updated_at">Recently updated</option><option value="name">Name</option><option value="-version">Highest version</option><option value="-created_at">Newest</option></select></Card>
    {!result?.items.length ? <EmptyPanel title={filtered ? "No workflows match these filters" : "Create your first governed workflow"} description={filtered ? "Clear the filters to restore the full definition inventory." : "Build, validate, and publish a real approval or business process without scripts or raw JSON."} action={<Button onClick={filtered ? clear : () => navigate(ROUTES.WORKFLOW_CREATE)}>{filtered ? "Clear filters" : "Create workflow"}</Button>}/> : <Card className="overflow-x-auto"><table className="w-full min-w-[900px]"><thead><tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground"><th className="p-4">Definition</th><th>Version</th><th>Type / trigger</th><th>Status</th><th>Updated</th><th className="p-4 text-right">Actions</th></tr></thead><tbody>{result.items.map((workflow) => <tr key={workflow.id} className="border-b last:border-0"><td className="p-4"><button className="font-medium text-primary hover:underline" onClick={() => navigate(ROUTES.WORKFLOW_DETAIL(workflow.id))}>{workflow.name}</button><p className="max-w-md truncate text-xs text-muted-foreground">{workflow.key} · {workflow.description || "No description"}</p></td><td>v{workflow.version}</td><td><StatusPill status={workflow.workflow_type}/><span className="ml-2 text-xs text-muted-foreground">{workflow.trigger_type}</span></td><td><StatusPill status={workflow.status}/></td><td className="text-sm">{new Date(workflow.updated_at).toLocaleDateString()}</td><td className="p-4"><div className="flex justify-end gap-1"><Button size="icon" variant="ghost" aria-label={`View ${workflow.name}`} onClick={() => navigate(ROUTES.WORKFLOW_DETAIL(workflow.id))}><Eye className="h-4 w-4"/></Button>{workflow.allowed_actions.includes("edit") ? <Button size="icon" variant="ghost" aria-label={`Edit ${workflow.name}`} onClick={() => navigate(ROUTES.WORKFLOW_EDIT(workflow.id))}><Pencil className="h-4 w-4"/></Button> : null}{workflow.allowed_actions.includes("publish") ? <Button size="icon" variant="ghost" aria-label={`Publish ${workflow.name}`} disabled={publish.isPending} onClick={() => publish.mutate(workflow.id)}><Send className="h-4 w-4"/></Button> : null}{workflow.allowed_actions.includes("clone") ? <Button size="icon" variant="ghost" aria-label={`Clone ${workflow.name}`} disabled={clone.isPending} onClick={() => clone.mutate(workflow.id)}><Copy className="h-4 w-4"/></Button> : null}{workflow.allowed_actions.includes("archive") ? <Button size="icon" variant="ghost" aria-label={`Archive ${workflow.name}`} disabled={archive.isPending} onClick={() => archive.mutate(workflow.id)}><Archive className="h-4 w-4"/></Button> : null}{workflow.allowed_actions.includes("delete") ? <Button size="icon" variant="ghost" aria-label={`Delete ${workflow.name}`} onClick={() => setDeleting(workflow)}><Trash2 className="h-4 w-4 text-destructive"/></Button> : null}</div></td></tr>)}</tbody></table><div className="px-4 pb-4"><Pagination page={result.pagination.page} totalPages={result.pagination.total_pages} onPage={setPage}/></div></Card>}
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open) setDeleting(null); }} title={`Delete ${deleting?.name ?? "draft"}?`} description="Only an unused draft can be deleted. This keeps published definitions and execution evidence immutable." confirmLabel={remove.isPending ? "Deleting…" : "Delete draft"} variant="danger" onConfirm={() => { if (deleting) remove.mutate(deleting.id); }}/>
  </main>;
}
