import type {
  ActionStepConfig,
  ApprovalStepConfig,
  NotificationStepConfig,
  StepType,
  WorkflowConfigurationDocument,
  WorkflowCreateDTO,
  WorkflowDetailDTO,
  WorkflowStepWriteDTO,
  WorkflowType,
} from "../contracts";

export const WORKFLOW_CATALOG_ACTIONS_QUERY_KEY = ["workflow-catalog-actions"] as const;
export const WORKFLOW_CATALOG_CONDITIONS_QUERY_KEY = ["workflow-catalog-conditions"] as const;
export const WORKFLOW_CATALOG_ASSIGNEES_QUERY_KEY = ["workflow-catalog-assignees"] as const;

export function slug(value: string, maximum: number): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "_")
    .replace(/^_|_$/gu, "")
    .slice(0, maximum);
}

export function recipientPath(config: NotificationStepConfig): string {
  const value =
    config.recipient_mapping[config.channel === "email" ? "recipient_email" : "recipient_id"];
  return typeof value === "string" ? value : "";
}

export function newStep(
  type: StepType,
  order: number,
  policy: WorkflowConfigurationDocument
): WorkflowStepWriteDTO {
  const key = `step_${order}`;
  if (type === "approval")
    return {
      key,
      name: `Approval ${order}`,
      step_type: type,
      order,
      config: {
        assignment_kind: policy.defaults.approval_assignment_kind,
        assignee_id: "",
        due_in_seconds: policy.defaults.approval_due_seconds,
        rejection_behavior: policy.defaults.approval_rejection_behavior,
        reject_step_key: null,
      },
      is_terminal: false,
    };
  if (type === "notification")
    return {
      key,
      name: `Notification ${order}`,
      step_type: type,
      order,
      config: {
        channel: "in_app",
        recipient_mapping: { recipient_id: "actor.id" },
        template_key: "workflow.task.created",
      },
      is_terminal: false,
    };
  if (type === "decision")
    return {
      key,
      name: `Decision ${order}`,
      step_type: type,
      order,
      config: { condition: {}, true_step_key: "", false_step_key: "" },
      is_terminal: false,
    };
  return {
    key,
    name: `Action ${order}`,
    step_type: type,
    order,
    config: { handler: "", schema_version: "", input_mapping: {}, configuration: {} },
    is_terminal: false,
  };
}

// Validation deliberately keeps every graph/config branch visible for step-linked feedback.
// eslint-disable-next-line complexity
export function localIssues(payload: WorkflowCreateDTO): readonly string[] {
  const issues: string[] = [];
  if (!payload.key.trim()) issues.push("Workflow key is required.");
  if (!payload.name.trim()) issues.push("Workflow name is required.");
  if (payload.steps.length === 0) issues.push("Add at least one step.");
  const keys = new Set<string>();
  for (const step of payload.steps) {
    if (!step.key.trim() || keys.has(step.key))
      issues.push(`Step ${step.order} needs a unique key.`);
    keys.add(step.key);
    if (!step.name.trim()) issues.push(`Step ${step.order} needs a name.`);
    if (step.step_type === "action" && !(step.config as ActionStepConfig).handler)
      issues.push(`${step.name}: choose an available action.`);
    if (step.step_type === "approval" && !(step.config as ApprovalStepConfig).assignee_id)
      issues.push(`${step.name}: choose an assignee.`);
    if (step.step_type === "decision") {
      const config = step.config;
      if (
        !("condition" in config) ||
        typeof config.condition.handler !== "string" ||
        !config.condition.handler
      )
        issues.push(`${step.name}: choose a condition.`);
      if (
        !("true_step_key" in config) ||
        (!keys.has(config.true_step_key) &&
          !payload.steps.some((candidate) => candidate.key === config.true_step_key))
      )
        issues.push(`${step.name}: select a valid true branch.`);
      if (
        !("false_step_key" in config) ||
        (!keys.has(config.false_step_key) &&
          !payload.steps.some((candidate) => candidate.key === config.false_step_key))
      )
        issues.push(`${step.name}: select a valid false branch.`);
    }
  }
  if (payload.steps.length > 0 && !payload.steps.some((step) => step.is_terminal))
    issues.push("Mark at least one step as terminal.");
  return issues;
}

export function workflowBuilderPayload({
  key,
  name,
  description,
  workflowType,
  triggerType,
  initial,
  steps,
}: {
  key: string;
  name: string;
  description: string;
  workflowType: WorkflowType | undefined;
  triggerType: WorkflowDetailDTO["trigger_type"] | undefined;
  initial: WorkflowDetailDTO | undefined;
  steps: readonly WorkflowStepWriteDTO[];
}): WorkflowCreateDTO | null {
  if (!workflowType || !triggerType) return null;
  return {
    key,
    name,
    description,
    workflow_type: workflowType,
    trigger_type: triggerType,
    trigger_config: initial?.trigger_config ?? {},
    required_context_schema: initial?.required_context_schema ?? {},
    steps,
  };
}

export function workflowBuilderIssues({
  payload,
  actionCatalogFailed,
  conditionCatalogFailed,
}: {
  payload: WorkflowCreateDTO | null;
  actionCatalogFailed: boolean;
  conditionCatalogFailed: boolean;
}): readonly string[] {
  if (!payload) return ["Workflow configuration is unavailable."];
  const issues = [...localIssues(payload)];
  if (actionCatalogFailed && payload.steps.some((step) => step.step_type === "action"))
    issues.push("Action catalog is unavailable.");
  if (conditionCatalogFailed && payload.steps.some((step) => step.step_type === "decision"))
    issues.push("Condition catalog is unavailable.");
  return issues;
}

export function removeStepAt(
  steps: readonly WorkflowStepWriteDTO[],
  index: number
): readonly WorkflowStepWriteDTO[] {
  return steps
    .filter((_, position) => position !== index)
    .map((step, position) => ({ ...step, order: position + 1 }));
}

export function moveStepByOffset(
  steps: readonly WorkflowStepWriteDTO[],
  index: number,
  offset: -1 | 1
): readonly WorkflowStepWriteDTO[] {
  const target = index + offset;
  const reordered = [...steps];
  const sourceStep = reordered[index];
  const targetStep = reordered[target];
  if (!sourceStep || !targetStep) return steps;
  reordered[index] = targetStep;
  reordered[target] = sourceStep;
  return reordered.map((step, position) => ({ ...step, order: position + 1 }));
}
