import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { WorkflowBuilder } from "../components/WorkflowBuilder";
import type { WorkflowCreateDTO } from "../contracts";
import { ROUTES } from "../contracts";
import { WorkflowApiError, workflowService } from "../services/workflow-service";
import { PageHeader, PageSkeleton, WorkflowProblem } from "../components/WorkflowUI";

export function WorkflowEditPage() {
  const { id = "" } = useParams(); const navigate = useNavigate();
  const query = useQuery({ queryKey: ["workflow-definition", id], queryFn: () => workflowService.workflows.get(id), enabled: Boolean(id) });
  const mutation = useMutation({ mutationFn: (payload: WorkflowCreateDTO) => { if (!query.data) throw new Error("Workflow is unavailable"); return workflowService.workflows.update(id, { ...payload, expected_updated_at: query.data.updated_at }); }, onSuccess: (workflow) => navigate(ROUTES.WORKFLOW_DETAIL(workflow.id)) });
  if (query.isLoading) return <PageSkeleton label="Loading workflow draft"/>;
  if (query.error) return <WorkflowProblem error={query.error} retry={() => void query.refetch()}/>;
  const workflow = query.data; if (!workflow) return <WorkflowProblem error={new Error("Workflow not found") } retry={() => void query.refetch()}/>;
  if (workflow.status !== "draft") return <main className="space-y-5"><PageHeader title="This version is immutable" description="Published and archived workflows cannot be edited. Clone a new draft version to preserve execution history."/><Button onClick={() => navigate(ROUTES.WORKFLOW_DETAIL(workflow.id))}>View version and clone</Button></main>;
  const conflict = mutation.error instanceof WorkflowApiError && mutation.error.status === 409;
  if (conflict) return <main className="space-y-5"><PageHeader title="A newer draft revision exists" description="Your changes were not applied because another editor saved a newer revision. Reload before making further changes."/><Button onClick={() => { mutation.reset(); void query.refetch(); }}>Reload latest revision</Button></main>;
  return <main className="space-y-6"><PageHeader title={`Edit ${workflow.name}`} description="Changes remain in this draft until validation and publication succeed."/><WorkflowBuilder initial={workflow} submitting={mutation.isPending} submitLabel="Save changes" serverError={mutation.error} onSubmit={(payload) => mutation.mutateAsync(payload).then(() => undefined)} onCancel={(path) => navigate(path)}/></main>;
}
