import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { WorkflowBuilder } from "../components/WorkflowBuilder";
import type { WorkflowCreateDTO } from "../contracts";
import { ROUTES } from "../contracts";
import { workflowService } from "../services/workflow-service";
import { PageHeader } from "../components/WorkflowUI";

export function WorkflowCreatePage() {
  const navigate = useNavigate();
  const mutation = useMutation({ mutationFn: (payload: WorkflowCreateDTO) => workflowService.workflows.create(payload), onSuccess: (workflow) => navigate(ROUTES.WORKFLOW_DETAIL(workflow.id)) });
  return <main className="space-y-6"><PageHeader title="Create workflow" description="Build a validated draft with registered actions, safe conditions, and directory-backed assignees."/><WorkflowBuilder submitting={mutation.isPending} submitLabel="Save draft" serverError={mutation.error} onSubmit={(payload) => mutation.mutateAsync(payload).then(() => undefined)} onCancel={(path) => navigate(path)}/></main>;
}
