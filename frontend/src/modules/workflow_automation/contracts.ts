/** Public, provider-neutral contract for the workflow automation v2 API. */

export type UUID = string;
export type ISODateTime = string;
export type JsonPrimitive = string | number | boolean | null;
export type JsonArray = readonly JsonValue[];
export interface JsonObject { readonly [key: string]: JsonValue; }
export type JsonValue = JsonPrimitive | JsonObject | JsonArray;

export type WorkflowType = "approval" | "state_machine" | "sequential" | "parallel" | "conditional";
export type TriggerType = "manual" | "event" | "scheduled";
export type WorkflowStatus = "draft" | "published" | "archived";
export type StepType = "action" | "approval" | "notification" | "decision";
export type TimeoutAction = "fail" | "notify" | "escalate" | "cancel";
export type InstanceState = "pending" | "running" | "waiting" | "completed" | "failed" | "cancelled";
export type TaskStatus = "pending" | "completed" | "rejected" | "cancelled" | "expired";
export type AssignmentKind = "user" | "role";
export type CapabilityAvailability = "available" | "locked" | "setup_required" | "degraded";
export type ValidationSeverity = "error" | "warning";

export interface ActionStepConfig {
  readonly handler: string;
  readonly schema_version: string;
  readonly input_mapping: JsonObject;
  readonly configuration?: JsonObject;
}

export interface ApprovalStepConfig {
  readonly assignment_kind: AssignmentKind;
  readonly assignee_id: UUID;
  readonly due_in_seconds: number;
  readonly rejection_behavior: "fail" | "goto" | "cancel";
  readonly reject_step_key: string | null;
}

export interface NotificationStepConfig {
  readonly channel: "in_app" | "email";
  readonly recipient_mapping: JsonObject;
  readonly template_key: string;
}

export interface DecisionStepConfig {
  readonly condition: JsonObject;
  readonly true_step_key: string;
  readonly false_step_key: string;
}

export type WorkflowStepConfig = ActionStepConfig | ApprovalStepConfig | NotificationStepConfig | DecisionStepConfig;

export interface WorkflowStepReadDTO {
  readonly id: UUID;
  readonly key: string;
  readonly name: string;
  readonly step_type: StepType;
  readonly order: number;
  readonly config: WorkflowStepConfig;
  readonly timeout_seconds: number | null;
  readonly timeout_action: TimeoutAction | null;
  readonly is_terminal: boolean;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}

export interface WorkflowStepWriteDTO {
  readonly key: string;
  readonly name: string;
  readonly step_type: StepType;
  readonly order: number;
  readonly config: WorkflowStepConfig;
  readonly timeout_seconds?: number | null;
  readonly timeout_action?: TimeoutAction | null;
  readonly is_terminal?: boolean;
}

export type WorkflowAction = "view" | "edit" | "delete" | "publish" | "archive" | "clone" | "start";

export interface WorkflowListDTO {
  readonly id: UUID;
  readonly key: string;
  readonly version: number;
  readonly name: string;
  readonly description: string;
  readonly workflow_type: WorkflowType;
  readonly trigger_type: TriggerType;
  readonly status: WorkflowStatus;
  readonly step_count: number;
  readonly created_by_name: string | null;
  readonly published_at: ISODateTime | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly allowed_actions: readonly WorkflowAction[];
}

export interface TransitionEvidence {
  readonly transition_key: string;
  readonly command: string;
  readonly from_state: string;
  readonly to_state: string;
  readonly actor_id: UUID | null;
  readonly occurred_at: ISODateTime;
  readonly correlation_id: string;
}

export interface VersionSummary {
  readonly id: UUID;
  readonly version: number;
  readonly status: WorkflowStatus;
  readonly updated_at: ISODateTime;
}

export interface ExecutionStatistics {
  readonly total: number;
  readonly active: number;
  readonly completed: number;
  readonly failed: number;
  readonly completion_rate: number | null;
}

export interface WorkflowDetailDTO extends Omit<WorkflowListDTO, "step_count"> {
  readonly required_context_schema: JsonObject;
  readonly transition_history: readonly TransitionEvidence[];
  readonly steps: readonly WorkflowStepReadDTO[];
  readonly versions: readonly VersionSummary[];
  readonly execution_statistics: ExecutionStatistics;
  readonly handler_health: readonly CapabilityHealth[];
}

export interface WorkflowCreateDTO {
  readonly key: string;
  readonly name: string;
  readonly description?: string;
  readonly workflow_type: WorkflowType;
  readonly trigger_type: TriggerType;
  readonly required_context_schema?: JsonObject;
  readonly steps: readonly WorkflowStepWriteDTO[];
}

export interface WorkflowUpdateDTO extends Partial<WorkflowCreateDTO> {
  readonly expected_updated_at: ISODateTime;
}

export interface ValidationIssueDTO {
  readonly code: string;
  readonly severity: ValidationSeverity;
  readonly message: string;
  readonly step_key: string | null;
  readonly pointer: string | null;
  readonly remediation: string | null;
}

export interface DefinitionValidationResultDTO {
  readonly valid: boolean;
  readonly issues: readonly ValidationIssueDTO[];
  readonly warnings: readonly ValidationIssueDTO[];
}

export interface WorkflowPublishDTO { readonly transition_key: string; }
export interface WorkflowCloneDTO { readonly name?: string; }

export interface WorkflowInstanceListDTO {
  readonly id: UUID;
  readonly workflow_id: UUID;
  readonly workflow_name: string;
  readonly workflow_version: number;
  readonly state: InstanceState;
  readonly current_step_name: string | null;
  readonly entity_type: string;
  readonly entity_id: UUID | null;
  readonly subject: string | null;
  readonly priority: number;
  readonly correlation_id: string;
  readonly started_by_name: string | null;
  readonly started_at: ISODateTime | null;
  readonly completed_at: ISODateTime | null;
  readonly created_at: ISODateTime;
  readonly failure_code: string;
  readonly failure_message: string;
  readonly allowed_actions: readonly ("view" | "cancel")[];
}

export interface WorkflowTaskListDTO {
  readonly id: UUID;
  readonly instance_id: UUID;
  readonly workflow_id: UUID;
  readonly workflow_name: string;
  readonly workflow_version: number;
  readonly step_id: UUID;
  readonly step_name: string;
  readonly assignment_kind: AssignmentKind;
  readonly assignment_label: string;
  readonly subject: string | null;
  readonly status: TaskStatus;
  readonly due_date: ISODateTime | null;
  readonly created_at: ISODateTime;
  readonly completed_at: ISODateTime | null;
  readonly correlation_id: string;
  readonly allowed_actions: readonly ("view" | "complete" | "reject")[];
}

export interface WorkflowTaskDetailDTO extends WorkflowTaskListDTO {
  readonly safe_context: JsonObject;
  readonly meta_data: JsonObject;
  readonly transition_history: readonly TransitionEvidence[];
  readonly completed_by_name: string | null;
}

export interface WorkflowInstanceDetailDTO extends WorkflowInstanceListDTO {
  readonly context_data: JsonObject;
  readonly result_data: JsonObject;
  readonly current_step: WorkflowStepReadDTO | null;
  readonly transition_history: readonly TransitionEvidence[];
  readonly tasks: readonly WorkflowTaskListDTO[];
}

export interface WorkflowInstanceStartDTO {
  readonly workflow_id: UUID;
  readonly context_data: JsonObject;
  readonly idempotency_key: string;
  readonly entity_type?: string;
  readonly entity_id?: UUID;
  readonly priority?: number;
}

export interface WorkflowInstanceCancelDTO { readonly transition_key: string; readonly reason?: string; }
export interface WorkflowTaskCompleteDTO { readonly meta_data: JsonObject; readonly transition_key: string; }
export interface WorkflowTaskRejectDTO { readonly reason: string; readonly meta_data: JsonObject; readonly transition_key: string; }

export interface PaginationMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ResponseMeta { readonly correlation_id: string; readonly timestamp: string; readonly pagination?: PaginationMeta; }
export interface GovernedEnvelope<T> { readonly data: T; readonly meta: ResponseMeta; }
export interface PaginatedResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly correlationId: string; readonly receivedAt: string; }
export interface ApiFieldError { readonly field: string; readonly code: string; readonly message: string; }
export interface StableApiErrorBody {
  readonly error: { readonly code: string; readonly message: string; readonly detail: { readonly field_errors?: readonly ApiFieldError[]; readonly retryable?: boolean; }; readonly correlation_id: string; };
}

export interface PageFilters { readonly page?: number; readonly page_size?: number; readonly search?: string; }
export type WorkflowOrdering = "name" | "-name" | "version" | "-version" | "created_at" | "-created_at" | "updated_at" | "-updated_at";
export interface WorkflowFilters extends PageFilters { readonly status?: WorkflowStatus; readonly workflow_type?: WorkflowType; readonly trigger_type?: TriggerType; readonly key?: string; readonly created_by?: UUID; readonly updated_after?: ISODateTime; readonly ordering?: WorkflowOrdering; }
export type InstanceOrdering = "priority" | "-priority" | "created_at" | "-created_at" | "completed_at" | "-completed_at";
export interface InstanceFilters extends PageFilters { readonly workflow_id?: UUID; readonly state?: InstanceState; readonly entity_type?: string; readonly entity_id?: UUID; readonly started_by?: UUID; readonly created_after?: ISODateTime; readonly created_before?: ISODateTime; readonly ordering?: InstanceOrdering; }
export type TaskOrdering = "due_date" | "-due_date" | "created_at" | "-created_at";
export interface TaskFilters extends PageFilters { readonly status?: TaskStatus; readonly workflow_id?: UUID; readonly instance_id?: UUID; readonly assignment_kind?: AssignmentKind; readonly overdue?: boolean; readonly due_before?: ISODateTime; readonly scope?: "mine" | "all"; readonly ordering?: TaskOrdering; }

export type UISchemaField =
  | { readonly kind: "text"; readonly key: string; readonly label: string; readonly required: boolean; readonly description?: string; readonly placeholder?: string }
  | { readonly kind: "number"; readonly key: string; readonly label: string; readonly required: boolean; readonly description?: string; readonly minimum?: number; readonly maximum?: number }
  | { readonly kind: "boolean"; readonly key: string; readonly label: string; readonly required: boolean; readonly description?: string }
  | { readonly kind: "select"; readonly key: string; readonly label: string; readonly required: boolean; readonly description?: string; readonly options: readonly { readonly value: string; readonly label: string }[] }
  | { readonly kind: "lookup"; readonly key: string; readonly label: string; readonly required: boolean; readonly description?: string; readonly lookup_key: string };

export interface CapabilityHealth { readonly key: string; readonly availability: CapabilityAvailability; readonly reason: string | null; }
export interface HandlerDescriptorDTO extends CapabilityHealth {
  readonly display_name: string;
  readonly description: string;
  readonly category: string;
  readonly owning_module: string;
  readonly schema_version: string;
  readonly descriptor_fingerprint: string;
  readonly required_permission: string;
  readonly required_entitlement: string;
  readonly ui_schema: readonly UISchemaField[];
  readonly input_schema: JsonObject;
  readonly output_schema: JsonObject;
  readonly idempotent: boolean;
  readonly network_access: boolean;
}
export interface ConditionDescriptorDTO extends CapabilityHealth { readonly display_name: string; readonly description: string; readonly owning_module: string; readonly schema_version: string; readonly descriptor_fingerprint: string; readonly ui_schema: readonly UISchemaField[]; }
export interface SubjectResolverDescriptorDTO extends CapabilityHealth { readonly entity_type: string; readonly display_name: string; readonly owning_module: string; }
export interface LookupOptionDTO { readonly id: UUID; readonly label: string; readonly description: string | null; readonly kind: string; }

export const MODULE_API_PREFIX = "/api/v2/workflow-automation";
export const ENDPOINTS = {
  WORKFLOWS: {
    LIST: `${MODULE_API_PREFIX}/workflows/`, CREATE: `${MODULE_API_PREFIX}/workflows/`, VALIDATE: `${MODULE_API_PREFIX}/workflows/validate/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/` as const,
    PUBLISH: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/publish/` as const,
    ARCHIVE: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/archive/` as const,
    CLONE: (id: UUID) => `${MODULE_API_PREFIX}/workflows/${id}/clone/` as const,
  },
  INSTANCES: { LIST: `${MODULE_API_PREFIX}/instances/`, START: `${MODULE_API_PREFIX}/instances/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/instances/${id}/` as const, CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/instances/${id}/cancel/` as const },
  TASKS: { LIST: `${MODULE_API_PREFIX}/tasks/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/tasks/${id}/` as const, COMPLETE: (id: UUID) => `${MODULE_API_PREFIX}/tasks/${id}/complete/` as const, REJECT: (id: UUID) => `${MODULE_API_PREFIX}/tasks/${id}/reject/` as const },
  CATALOG: { ACTIONS: `${MODULE_API_PREFIX}/catalog/actions/`, CONDITIONS: `${MODULE_API_PREFIX}/catalog/conditions/`, SUBJECTS: `${MODULE_API_PREFIX}/catalog/subjects/`, ASSIGNEES: `${MODULE_API_PREFIX}/catalog/assignees/`, LOOKUP: (key: string) => `${MODULE_API_PREFIX}/catalog/lookups/${encodeURIComponent(key)}/` as const },
} as const;

export const ROUTES = {
  WORKFLOWS: "/workflow-automation/workflows", WORKFLOW_CREATE: "/workflow-automation/workflows/new", WORKFLOW_DETAIL: (id: string) => `/workflow-automation/workflows/${id}` as const, WORKFLOW_EDIT: (id: string) => `/workflow-automation/workflows/${id}/edit` as const,
  INSTANCES: "/workflow-automation/instances", INSTANCE_DETAIL: (id: string) => `/workflow-automation/instances/${id}` as const,
  TASKS: "/workflow-automation/tasks", TASK_DETAIL: (id: string) => `/workflow-automation/tasks/${id}` as const,
} as const;
