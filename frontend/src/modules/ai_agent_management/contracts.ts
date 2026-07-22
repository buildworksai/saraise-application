/** Public v2 contracts for the tenant-scoped AI agent governance runtime. */

export type UUID = string;
export type JSONPrimitive = string | number | boolean | null;
export interface JSONObject { readonly [key: string]: JSONValue; }
export type JSONValue = JSONPrimitive | JSONObject | readonly JSONValue[];

export type AgentStatus = "draft" | "active" | "disabled" | "retired";
export type IdentityType = "user_bound" | "system_bound";
export type ExecutionState = "created" | "validated" | "queued" | "running" | "paused" | "completed" | "failed" | "terminated" | "timed_out";
export type SchedulerTaskStatus = "pending" | "queued" | "running" | "completed" | "failed" | "cancelled";
export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | "cancelled";
export type SideEffectClass = "read_only" | "workflow_transition" | "data_mutation" | "external_integration";
export type InvocationStatus = "requested" | "awaiting_approval" | "running" | "succeeded" | "failed" | "blocked" | "cancelled";
export type KillSwitchScope = "tenant" | "shard" | "agent";
export type KillSwitchStatus = "active" | "inactive";
export type CostType = "token" | "api_call" | "execution_time" | "storage" | "egress";
export type Availability = "available" | "unavailable" | "setup_required" | "not_entitled";
export type AuditOutcome = "success" | "failure" | "blocked" | "pending";

export interface TransitionEvidence {
  readonly transition: string;
  readonly from: string;
  readonly to: string;
  readonly occurred_at: string;
  readonly actor_id: UUID | null;
  readonly correlation_id?: UUID;
  readonly reason?: string;
}

export interface PaginationMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}
export interface ResponseMeta { readonly correlation_id: UUID; readonly timestamp: string; readonly pagination?: PaginationMeta; }
export interface APIEnvelope<T> { readonly data: T; readonly meta: ResponseMeta; }
export interface APIFieldError { readonly code: string; readonly message: string; readonly field?: string; readonly pointer?: string; }
export interface APIErrorEnvelope { readonly error: { readonly code: string; readonly message: string; readonly detail?: readonly APIFieldError[]; readonly correlation_id: UUID; }; }
export interface PageResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly correlationId: UUID; readonly receivedAt: string; }
export interface PageRequest { readonly page?: number; readonly page_size?: number; }

export interface AgentListItem {
  readonly id: UUID; readonly name: string; readonly description: string; readonly identity_type: IdentityType;
  readonly runner_key: string; readonly provider_config_id: UUID | null; readonly status: AgentStatus;
  readonly active_execution_count?: number; readonly updated_at: string; readonly created_at: string;
  readonly allowed_actions?: readonly string[];
}
export interface AgentDetail extends AgentListItem {
  readonly subject_id: UUID; readonly session_id: UUID | null; readonly config: JSONObject;
  readonly transition_history: readonly TransitionEvidence[]; readonly created_by: UUID; readonly deleted_at: string | null;
  readonly provider_status?: Availability; readonly runner_status?: Availability;
  readonly entitlement?: EntitlementSummary; readonly quota?: Quota;
}
export interface AgentCreateRequest { readonly name: string; readonly description?: string; readonly identity_type: IdentityType; readonly subject_id: UUID; readonly session_id?: UUID | null; readonly runner_key: string; readonly provider_config_id?: UUID | null; readonly config?: JSONObject; }
export interface AgentUpdateRequest { readonly name?: string; readonly description?: string; readonly identity_type?: IdentityType; readonly subject_id?: UUID; readonly session_id?: UUID | null; readonly runner_key?: string; readonly provider_config_id?: UUID | null; readonly config?: JSONObject; }
export interface LifecycleRequest { readonly transition_key: string; readonly reason?: string; }
export interface ExecuteAgentRequest { readonly task_definition: JSONObject; readonly input_metadata?: JSONObject; readonly idempotency_key: string; readonly schedule_at?: string | null; }
export interface EvaluationStartRequest { readonly suite_key: string; readonly idempotency_key: string; readonly baseline_job_id?: UUID | null; readonly red_team?: boolean; }

export interface AgentExecutionListItem { readonly id: UUID; readonly agent_id: UUID; readonly agent_name?: string; readonly async_job_id: UUID; readonly state: ExecutionState; readonly initiating_actor_id: UUID; readonly started_at: string | null; readonly completed_at: string | null; readonly created_at: string; readonly error_code: string; readonly error_message: string; readonly allowed_actions?: readonly string[]; }
export interface AgentExecutionDetail extends AgentExecutionListItem { readonly session_id: UUID | null; readonly task_definition: JSONObject; readonly input_metadata: JSONObject; readonly result: JSONValue | null; readonly provider_config_id: UUID | null; readonly idempotency_key: string; readonly transition_history: readonly TransitionEvidence[]; readonly correlation_id?: UUID; }
export interface TransitionExecutionRequest extends LifecycleRequest { readonly reason?: string; }

export interface ScheduleListItem { readonly id: UUID; readonly agent_id: UUID; readonly agent_name?: string; readonly execution_id: UUID | null; readonly async_job_id: UUID | null; readonly scheduled_at: string; readonly priority: number; readonly retry_count: number; readonly max_retries: number; readonly status: SchedulerTaskStatus; readonly created_at: string; }
export interface ScheduleDetail extends ScheduleListItem { readonly task_data: JSONObject; readonly transition_history: readonly TransitionEvidence[]; readonly error_code: string; readonly error_message: string; readonly started_at: string | null; readonly completed_at: string | null; readonly idempotency_key: string; readonly outbox_status?: string | null; }
export interface ScheduleCreateRequest { readonly agent_id: UUID; readonly scheduled_at: string; readonly priority?: number; readonly max_retries?: number; readonly task_data: JSONObject; readonly idempotency_key: string; }

export interface ApprovalListItem { readonly id: UUID; readonly tool_id: UUID; readonly tool_name?: string; readonly agent_execution_id: UUID; readonly requested_by: UUID; readonly requested_for: UUID; readonly approver_id: UUID | null; readonly status: ApprovalStatus; readonly justification: string; readonly requested_at: string; readonly expires_at: string | null; readonly decided_at: string | null; readonly allowed_actions?: readonly string[]; }
export interface ApprovalDetail extends ApprovalListItem { readonly tool_invocation_id: UUID | null; readonly tool_input: JSONObject; readonly rejection_reason: string; readonly metadata: JSONObject; readonly transition_history: readonly TransitionEvidence[]; readonly sod_warning?: string | null; readonly audit_correlation_id?: UUID; }
export interface ApprovalCreateRequest { readonly tool_id: UUID; readonly agent_execution_id: UUID; readonly tool_invocation_id?: UUID | null; readonly requested_for: UUID; readonly tool_input: JSONObject; readonly justification: string; readonly expires_at?: string | null; }
export interface ApprovalDecisionRequest extends LifecycleRequest { readonly reason?: string; }

export interface ToolListItem { readonly id: UUID; readonly name: string; readonly owning_module: string; readonly version: string; readonly description: string; readonly side_effect_class: SideEffectClass; readonly is_active: boolean; readonly required_permissions: readonly string[]; readonly registered_at: string; }
export interface ToolDetail extends ToolListItem { readonly input_schema: JSONObject; readonly output_schema: JSONObject; readonly metadata: JSONObject; readonly registered_by: UUID; readonly updated_at: string; }
export interface ToolCreateRequest { readonly name: string; readonly owning_module: string; readonly version: string; readonly description?: string; readonly required_permissions?: readonly string[]; readonly input_schema: JSONObject; readonly output_schema: JSONObject; readonly side_effect_class: SideEffectClass; readonly metadata?: JSONObject; }
export interface ToolUpdateRequest { readonly description?: string; readonly required_permissions?: readonly string[]; readonly input_schema?: JSONObject; readonly output_schema?: JSONObject; readonly side_effect_class?: SideEffectClass; readonly is_active?: boolean; readonly metadata?: JSONObject; }
export interface ToolValidationRequest { readonly direction: "input" | "output"; readonly value: JSONValue; }
export interface ValidationDiagnostic { readonly valid: boolean; readonly issues: readonly APIFieldError[]; }
export interface ToolInvocation { readonly id: UUID; readonly tool_id: UUID; readonly tool_name?: string; readonly agent_execution_id: UUID | null; readonly approval_request_id: UUID | null; readonly status: InvocationStatus; readonly input_data?: JSONObject; readonly output_data?: JSONValue | null; readonly error_code: string; readonly error_message: string; readonly invoked_at: string; readonly completed_at: string | null; readonly duration_ms: number | null; }

export interface SoDPolicy { readonly id: UUID; readonly name: string; readonly description: string; readonly action_1: string; readonly action_2: string; readonly is_active: boolean; readonly created_at: string; readonly updated_at: string; }
export interface SoDPolicyRequest { readonly name: string; readonly description?: string; readonly action_1: string; readonly action_2: string; readonly is_active?: boolean; }
export interface SoDPolicyUpdateRequest { readonly name?: string; readonly description?: string; readonly action_1?: string; readonly action_2?: string; readonly is_active?: boolean; }
export interface SoDViolation { readonly id: UUID; readonly policy_id: UUID; readonly policy_name?: string; readonly agent_execution_id: UUID | null; readonly tool_invocation_id: UUID | null; readonly action_1_user: UUID; readonly action_2_user: UUID; readonly blocked: boolean; readonly violation_at: string; readonly evidence: JSONObject; }

export interface EgressRule { readonly id: UUID; readonly name: string; readonly description: string; readonly destination_type: "domain" | "ip" | "cidr" | "url_pattern"; readonly destination: string; readonly port: number | null; readonly protocol: "http" | "https" | "tcp" | "udp"; readonly is_active: boolean; readonly created_at: string; readonly updated_at: string; }
export interface EgressRuleRequest { readonly name: string; readonly description?: string; readonly destination_type: EgressRule["destination_type"]; readonly destination: string; readonly port?: number | null; readonly protocol: EgressRule["protocol"]; readonly is_active?: boolean; }
export interface EgressRequest { readonly id: UUID; readonly agent_execution_id: UUID; readonly destination: string; readonly resolved_address: string | null; readonly port: number; readonly protocol: string; readonly allowed: boolean; readonly matched_rule_id: UUID | null; readonly requested_at: string; readonly reason_code: string; }

export interface SecretMetadata { readonly id: UUID; readonly name: string; readonly description: string; readonly secret_type: "api_key" | "password" | "token" | "certificate" | "other"; readonly is_active: boolean; readonly expires_at: string | null; readonly last_rotated_at: string; readonly rotation_interval_days: number | null; readonly created_at: string; }
export interface SecretCreateRequest { readonly name: string; readonly description?: string; readonly secret_type: SecretMetadata["secret_type"]; readonly plaintext: string; readonly expires_at?: string | null; readonly rotation_interval_days?: number | null; }
export interface SecretRotateRequest { readonly plaintext: string; readonly transition_key: string; }
export interface SecretAccess { readonly id: UUID; readonly secret_id: UUID; readonly secret_name?: string; readonly agent_execution_id: UUID | null; readonly accessed_by: UUID; readonly accessed_at: string; readonly purpose: string; }

export interface Quota { readonly id: UUID; readonly resource: string; readonly limit: number; readonly consumed: number; readonly remaining: number; readonly period_start?: string; readonly period_end?: string; }
export interface EntitlementSummary { readonly feature: string; readonly status: Availability; readonly reason?: string; }
export interface QuotaUsage { readonly id: UUID; readonly resource: string; readonly agent_execution_id: UUID | null; readonly usage_value: number; readonly remaining_after: number; readonly usage_timestamp: string; }
export interface TokenUsage { readonly id: UUID; readonly agent_execution_id: UUID; readonly provider: string; readonly model: string; readonly input_tokens: number; readonly output_tokens: number; readonly total_tokens: number; readonly usage_timestamp: string; }
export interface CostRecord { readonly id: UUID; readonly agent_execution_id: UUID | null; readonly tool_invocation_id: UUID | null; readonly module_name: string | null; readonly cost_type: CostType; readonly provider: string | null; readonly amount: string | null; readonly currency: string; readonly pricing_version: string | null; readonly pricing_available: boolean; readonly cost_timestamp: string; }
export interface CostSummary { readonly id: UUID; readonly period_start: string; readonly period_end: string; readonly period_type: "hourly" | "daily" | "weekly" | "monthly"; readonly total_cost: string; readonly currency: string; readonly total_tokens: number; readonly total_executions: number; readonly calculated_at: string; readonly breakdowns: JSONObject; }
export interface ShardSaturation { readonly id: UUID; readonly shard_id: string; readonly saturation_level: string; readonly active_agents: number; readonly active_executions: number; readonly cpu_usage_percent: string | null; readonly memory_usage_percent: string | null; readonly measured_at: string; }

export interface KillSwitch { readonly id: UUID; readonly name: string; readonly description: string; readonly scope: KillSwitchScope; readonly scope_id: UUID | null; readonly status: KillSwitchStatus; readonly reason: string; readonly activated_by: UUID; readonly activated_at: string; readonly deactivated_by: UUID | null; readonly deactivated_at: string | null; readonly transition_history: readonly TransitionEvidence[]; }
export interface KillSwitchActivateRequest { readonly name: string; readonly description?: string; readonly scope: KillSwitchScope; readonly scope_id?: UUID | null; readonly reason: string; readonly transition_key: string; }

export interface AuditEvent { readonly id: UUID; readonly event_type: string; readonly agent_execution_id: UUID | null; readonly tool_invocation_id: UUID | null; readonly approval_request_id: UUID | null; readonly initiating_principal: UUID; readonly subject_id: UUID; readonly session_id: UUID | null; readonly request_id: UUID; readonly correlation_id: UUID; readonly event_timestamp: string; readonly outcome: AuditOutcome; readonly decisions: JSONObject; readonly transitions: JSONObject; readonly resources: JSONObject; readonly metadata: JSONObject; }
export interface AuditTrail { readonly id: UUID; readonly request_id: UUID; readonly correlation_id: UUID; readonly agent_execution_id: UUID; readonly initiating_principal: UUID; readonly request_timestamp: string; readonly completed_timestamp: string | null; readonly final_outcome: "success" | "failure" | "blocked" | "partial" | null; readonly summary: JSONObject; readonly events?: readonly AuditEvent[]; }

export interface AsyncJob { readonly id: UUID; readonly job_type: string; readonly state: string; readonly progress_percent?: number; readonly result: JSONValue | null; readonly error_code?: string; readonly safe_message?: string; readonly correlation_id?: UUID; readonly created_at: string; readonly updated_at: string; }
export interface EvaluationMetric { readonly key: string; readonly label: string; readonly value: number; readonly unit?: string; readonly passed: boolean; readonly baseline_value?: number | null; readonly delta?: number | null; }
export interface EvaluationResult { readonly job: AsyncJob; readonly suite_key: string; readonly tested_agent_version?: string; readonly metrics: readonly EvaluationMetric[]; readonly failures: readonly string[]; readonly availability: Availability; readonly diagnostic?: string; }
export interface HealthComponent { readonly name: string; readonly status: "healthy" | "degraded" | "unhealthy"; readonly latency_ms: number; }
export interface ModuleHealth { readonly status: "healthy" | "degraded" | "unhealthy"; readonly components: readonly HealthComponent[]; }
export interface CostRecalculationRequest { readonly period_start: string; readonly period_end: string; readonly period_type: CostSummary["period_type"]; readonly currency: string; readonly idempotency_key: string; }

export interface AgentFilters extends PageRequest { readonly status?: AgentStatus; readonly identity_type?: IdentityType; readonly runner_key?: string; readonly subject_id?: UUID; readonly search?: string; readonly ordering?: "name" | "-name" | "created_at" | "-created_at" | "updated_at" | "-updated_at"; }
export interface ExecutionFilters extends PageRequest { readonly agent_id?: UUID; readonly state?: ExecutionState; readonly actor_id?: UUID; readonly created_after?: string; readonly created_before?: string; readonly ordering?: "created_at" | "-created_at" | "started_at" | "-started_at" | "completed_at" | "-completed_at"; }
export interface ScheduleFilters extends PageRequest { readonly agent_id?: UUID; readonly status?: SchedulerTaskStatus; readonly scheduled_after?: string; readonly scheduled_before?: string; readonly ordering?: "priority" | "-priority" | "scheduled_at" | "-scheduled_at"; }
export interface ApprovalFilters extends PageRequest { readonly status?: ApprovalStatus; readonly tool_id?: UUID; readonly execution_id?: UUID; readonly approver_id?: UUID; readonly expires_after?: string; readonly expires_before?: string; }
export interface ToolFilters extends PageRequest { readonly owning_module?: string; readonly side_effect_class?: SideEffectClass; readonly is_active?: boolean; readonly search?: string; readonly ordering?: "name" | "-name" | "registered_at" | "-registered_at"; }
export interface EvidenceFilters extends PageRequest { readonly execution_id?: UUID; readonly start?: string; readonly end?: string; readonly ordering?: string; }
export interface AuditFilters extends EvidenceFilters { readonly correlation_id?: UUID; readonly event_type?: string; readonly outcome?: AuditOutcome; }

type QueryScalar = string | number | boolean | undefined | null;
export function withQuery<T extends object>(path: string, filters: T): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters as { readonly [key: string]: QueryScalar })) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `${path}?${encoded}` : path;
}

const API_ROOT = "/api/v2/ai-agent-management";
const resource = (name: string) => `${API_ROOT}/${name}/` as const;
const detail = (name: string, id: UUID) => `${API_ROOT}/${name}/${encodeURIComponent(id)}/` as const;
const action = (name: string, id: UUID, verb: string) => `${API_ROOT}/${name}/${encodeURIComponent(id)}/${verb}/` as const;

export const ENDPOINTS = {
  AGENTS: { LIST: resource("agents"), CREATE: resource("agents"), DETAIL: (id: UUID) => detail("agents", id), UPDATE: (id: UUID) => detail("agents", id), DELETE: (id: UUID) => detail("agents", id), ACTIVATE: (id: UUID) => action("agents", id, "activate"), DISABLE: (id: UUID) => action("agents", id, "disable"), RETIRE: (id: UUID) => action("agents", id, "retire"), EXECUTE: (id: UUID) => action("agents", id, "execute"), EVALUATE: (id: UUID) => action("agents", id, "evaluate") },
  EXECUTIONS: { LIST: resource("executions"), DETAIL: (id: UUID) => detail("executions", id), PAUSE: (id: UUID) => action("executions", id, "pause"), RESUME: (id: UUID) => action("executions", id, "resume"), TERMINATE: (id: UUID) => action("executions", id, "terminate") },
  SCHEDULES: { LIST: resource("schedules"), CREATE: resource("schedules"), DETAIL: (id: UUID) => detail("schedules", id), CANCEL: (id: UUID) => action("schedules", id, "cancel") },
  APPROVALS: { LIST: resource("approvals"), CREATE: resource("approvals"), DETAIL: (id: UUID) => detail("approvals", id), APPROVE: (id: UUID) => action("approvals", id, "approve"), REJECT: (id: UUID) => action("approvals", id, "reject"), CANCEL: (id: UUID) => action("approvals", id, "cancel") },
  SOD_POLICIES: { LIST: resource("sod-policies"), CREATE: resource("sod-policies"), DETAIL: (id: UUID) => detail("sod-policies", id), UPDATE: (id: UUID) => detail("sod-policies", id), DELETE: (id: UUID) => detail("sod-policies", id) },
  SOD_VIOLATIONS: { LIST: resource("sod-violations"), DETAIL: (id: UUID) => detail("sod-violations", id) },
  TOOLS: { LIST: resource("tools"), CREATE: resource("tools"), DETAIL: (id: UUID) => detail("tools", id), UPDATE: (id: UUID) => detail("tools", id), DELETE: (id: UUID) => detail("tools", id), VALIDATE: (id: UUID) => action("tools", id, "validate") },
  TOOL_INVOCATIONS: { LIST: resource("tool-invocations"), DETAIL: (id: UUID) => detail("tool-invocations", id) },
  EGRESS_RULES: { LIST: resource("egress-rules"), CREATE: resource("egress-rules"), DETAIL: (id: UUID) => detail("egress-rules", id), UPDATE: (id: UUID) => detail("egress-rules", id), DELETE: (id: UUID) => detail("egress-rules", id) },
  EGRESS_REQUESTS: { LIST: resource("egress-requests"), DETAIL: (id: UUID) => detail("egress-requests", id) },
  SECRETS: { LIST: resource("secrets"), CREATE: resource("secrets"), DETAIL: (id: UUID) => detail("secrets", id), ROTATE: (id: UUID) => action("secrets", id, "rotate"), DEACTIVATE: (id: UUID) => action("secrets", id, "deactivate") },
  SECRET_ACCESSES: { LIST: resource("secret-accesses"), DETAIL: (id: UUID) => detail("secret-accesses", id) },
  QUOTAS: { LIST: resource("quotas"), DETAIL: (id: UUID) => detail("quotas", id) },
  QUOTA_USAGE: { LIST: resource("quota-usage"), DETAIL: (id: UUID) => detail("quota-usage", id) },
  SATURATION: { LIST: resource("saturation"), DETAIL: (id: UUID) => detail("saturation", id) },
  KILL_SWITCHES: { LIST: resource("kill-switches"), CREATE: resource("kill-switches"), DETAIL: (id: UUID) => detail("kill-switches", id), DEACTIVATE: (id: UUID) => action("kill-switches", id, "deactivate") },
  TOKEN_USAGE: { LIST: resource("token-usage"), DETAIL: (id: UUID) => detail("token-usage", id) },
  COST_RECORDS: { LIST: resource("cost-records"), DETAIL: (id: UUID) => detail("cost-records", id) },
  COST_SUMMARIES: { LIST: resource("cost-summaries"), DETAIL: (id: UUID) => detail("cost-summaries", id), RECALCULATE: `${API_ROOT}/cost-summaries/recalculate/` },
  AUDIT_EVENTS: { LIST: resource("audit-events"), DETAIL: (id: UUID) => detail("audit-events", id) },
  AUDIT_TRAILS: { LIST: resource("audit-trails"), DETAIL: (id: UUID) => detail("audit-trails", id) },
  JOBS: { LIST: resource("jobs"), DETAIL: (id: UUID) => detail("jobs", id) },
  HEALTH: `${API_ROOT}/health/`,
} as const;

export const ROUTES = {
  AGENTS: "/ai-agents", AGENT_CREATE: "/ai-agents/create", AGENT_DETAIL: (id: UUID) => `/ai-agents/${id}` as const, AGENT_EDIT: (id: UUID) => `/ai-agents/${id}/edit` as const,
  EXECUTIONS: "/ai-agents/executions", EXECUTION_DETAIL: (id: UUID) => `/ai-agents/executions/${id}` as const,
  SCHEDULES: "/ai-agents/schedules", SCHEDULE_CREATE: "/ai-agents/schedules/create", SCHEDULE_DETAIL: (id: UUID) => `/ai-agents/schedules/${id}` as const,
  APPROVALS: "/ai-agents/approvals", APPROVAL_DETAIL: (id: UUID) => `/ai-agents/approvals/${id}` as const,
  TOOLS: "/ai-agents/tools", TOOL_CREATE: "/ai-agents/tools/create", TOOL_DETAIL: (id: UUID) => `/ai-agents/tools/${id}` as const, TOOL_EDIT: (id: UUID) => `/ai-agents/tools/${id}/edit` as const,
  GOVERNANCE: "/ai-agents/governance", USAGE: "/ai-agents/usage", AUDIT: "/ai-agents/audit", AUDIT_TRAIL_DETAIL: (id: UUID) => `/ai-agents/audit/${id}` as const,
  EVALUATION: (id: UUID) => `/ai-agents/${id}/evaluation` as const,
} as const;

export function isExecutionState(value: unknown): value is ExecutionState { return typeof value === "string" && ["created", "validated", "queued", "running", "paused", "completed", "failed", "terminated", "timed_out"].includes(value); }
