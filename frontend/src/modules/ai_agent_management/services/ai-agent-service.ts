import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS, withQuery,
  type APIEnvelope, type AgentCreateRequest, type AgentDetail, type AgentFilters, type AgentListItem,
  type AgentUpdateRequest, type ApprovalCreateRequest, type ApprovalDecisionRequest, type ApprovalDetail,
  type ApprovalFilters, type ApprovalListItem, type AsyncJob, type AuditEvent, type AuditFilters, type AuditTrail,
  type CostRecord, type CostRecalculationRequest, type CostSummary, type EgressRequest, type EgressRule,
  type EgressRuleRequest, type EvaluationStartRequest, type EvidenceFilters,
  type ExecuteAgentRequest, type AgentExecutionDetail, type AgentExecutionListItem, type ExecutionFilters,
  type KillSwitch, type KillSwitchActivateRequest, type LifecycleRequest, type ModuleHealth, type PageRequest,
  type PageResult, type Quota, type QuotaUsage, type ScheduleCreateRequest, type ScheduleDetail, type ScheduleFilters,
  type ScheduleListItem, type SecretAccess, type SecretCreateRequest, type SecretMetadata, type SecretRotateRequest,
  type ShardSaturation, type SoDPolicy, type SoDPolicyRequest, type SoDPolicyUpdateRequest, type SoDViolation,
  type TokenUsage, type ToolCreateRequest, type ToolDetail, type ToolFilters, type ToolInvocation,
  type ToolListItem, type ToolUpdateRequest, type ToolValidationRequest, type TransitionExecutionRequest,
  type ValidationDiagnostic,
} from "../contracts";

function unwrap<T>(response: APIEnvelope<T>): T { return response.data; }
function page<T>(response: APIEnvelope<readonly T[]>): PageResult<T> {
  if (!response.meta.pagination) throw new Error("The governed API omitted pagination metadata.");
  return { items: response.data, pagination: response.meta.pagination, correlationId: response.meta.correlation_id, receivedAt: response.meta.timestamp };
}
async function get<T>(path: string): Promise<T> { return unwrap(await apiClient.get<APIEnvelope<T>>(path)); }
async function getPage<T>(path: string): Promise<PageResult<T>> { return page(await apiClient.get<APIEnvelope<readonly T[]>>(path)); }
async function post<T>(path: string, body: object): Promise<T> { return unwrap(await apiClient.post<APIEnvelope<T>>(path, body)); }
async function patch<T>(path: string, body: object): Promise<T> { return unwrap(await apiClient.patch<APIEnvelope<T>>(path, body)); }
async function remove(path: string): Promise<void> { await apiClient.delete<void>(path); }

export const aiAgentService = {
  listAgents: (filters: AgentFilters = {}) => getPage<AgentListItem>(withQuery(ENDPOINTS.AGENTS.LIST, filters)),
  getAgent: (id: string) => get<AgentDetail>(ENDPOINTS.AGENTS.DETAIL(id)),
  createAgent: (body: AgentCreateRequest) => post<AgentDetail>(ENDPOINTS.AGENTS.CREATE, body),
  updateAgent: (id: string, body: AgentUpdateRequest) => patch<AgentDetail>(ENDPOINTS.AGENTS.UPDATE(id), body),
  retireAgent: (id: string, body: LifecycleRequest) => post<AgentDetail>(ENDPOINTS.AGENTS.RETIRE(id), body),
  activateAgent: (id: string, body: LifecycleRequest) => post<AgentDetail>(ENDPOINTS.AGENTS.ACTIVATE(id), body),
  disableAgent: (id: string, body: LifecycleRequest) => post<AgentDetail>(ENDPOINTS.AGENTS.DISABLE(id), body),
  executeAgent: (id: string, body: ExecuteAgentRequest) => post<AgentExecutionDetail>(ENDPOINTS.AGENTS.EXECUTE(id), body),
  evaluateAgent: (id: string, body: EvaluationStartRequest) => post<AsyncJob>(ENDPOINTS.AGENTS.EVALUATE(id), body),

  listExecutions: (filters: ExecutionFilters = {}) => getPage<AgentExecutionListItem>(withQuery(ENDPOINTS.EXECUTIONS.LIST, filters)),
  getExecution: (id: string) => get<AgentExecutionDetail>(ENDPOINTS.EXECUTIONS.DETAIL(id)),
  pauseExecution: (id: string, body: TransitionExecutionRequest) => post<AgentExecutionDetail>(ENDPOINTS.EXECUTIONS.PAUSE(id), body),
  resumeExecution: (id: string, body: TransitionExecutionRequest) => post<AgentExecutionDetail>(ENDPOINTS.EXECUTIONS.RESUME(id), body),
  terminateExecution: (id: string, body: TransitionExecutionRequest) => post<AgentExecutionDetail>(ENDPOINTS.EXECUTIONS.TERMINATE(id), body),

  listSchedules: (filters: ScheduleFilters = {}) => getPage<ScheduleListItem>(withQuery(ENDPOINTS.SCHEDULES.LIST, filters)),
  getSchedule: (id: string) => get<ScheduleDetail>(ENDPOINTS.SCHEDULES.DETAIL(id)),
  createSchedule: (body: ScheduleCreateRequest) => post<ScheduleDetail>(ENDPOINTS.SCHEDULES.CREATE, body),
  cancelSchedule: (id: string, body: LifecycleRequest) => post<ScheduleDetail>(ENDPOINTS.SCHEDULES.CANCEL(id), body),

  listApprovals: (filters: ApprovalFilters = {}) => getPage<ApprovalListItem>(withQuery(ENDPOINTS.APPROVALS.LIST, filters)),
  getApproval: (id: string) => get<ApprovalDetail>(ENDPOINTS.APPROVALS.DETAIL(id)),
  createApproval: (body: ApprovalCreateRequest) => post<ApprovalDetail>(ENDPOINTS.APPROVALS.CREATE, body),
  approveRequest: (id: string, body: ApprovalDecisionRequest) => post<ApprovalDetail>(ENDPOINTS.APPROVALS.APPROVE(id), body),
  rejectRequest: (id: string, body: ApprovalDecisionRequest) => post<ApprovalDetail>(ENDPOINTS.APPROVALS.REJECT(id), body),
  cancelApproval: (id: string, body: ApprovalDecisionRequest) => post<ApprovalDetail>(ENDPOINTS.APPROVALS.CANCEL(id), body),

  listTools: (filters: ToolFilters = {}) => getPage<ToolListItem>(withQuery(ENDPOINTS.TOOLS.LIST, filters)),
  getTool: (id: string) => get<ToolDetail>(ENDPOINTS.TOOLS.DETAIL(id)),
  createTool: (body: ToolCreateRequest) => post<ToolDetail>(ENDPOINTS.TOOLS.CREATE, body),
  updateTool: (id: string, body: ToolUpdateRequest) => patch<ToolDetail>(ENDPOINTS.TOOLS.UPDATE(id), body),
  deactivateTool: (id: string) => remove(ENDPOINTS.TOOLS.DELETE(id)),
  validateTool: (id: string, body: ToolValidationRequest) => post<ValidationDiagnostic>(ENDPOINTS.TOOLS.VALIDATE(id), body),
  listToolInvocations: (filters: EvidenceFilters = {}) => getPage<ToolInvocation>(withQuery(ENDPOINTS.TOOL_INVOCATIONS.LIST, filters)),
  getToolInvocation: (id: string) => get<ToolInvocation>(ENDPOINTS.TOOL_INVOCATIONS.DETAIL(id)),

  listSoDPolicies: (filters: PageRequest = {}) => getPage<SoDPolicy>(withQuery(ENDPOINTS.SOD_POLICIES.LIST, filters)),
  getSoDPolicy: (id: string) => get<SoDPolicy>(ENDPOINTS.SOD_POLICIES.DETAIL(id)),
  createSoDPolicy: (body: SoDPolicyRequest) => post<SoDPolicy>(ENDPOINTS.SOD_POLICIES.CREATE, body),
  updateSoDPolicy: (id: string, body: SoDPolicyUpdateRequest) => patch<SoDPolicy>(ENDPOINTS.SOD_POLICIES.UPDATE(id), body),
  deactivateSoDPolicy: (id: string) => remove(ENDPOINTS.SOD_POLICIES.DELETE(id)),
  listSoDViolations: (filters: EvidenceFilters = {}) => getPage<SoDViolation>(withQuery(ENDPOINTS.SOD_VIOLATIONS.LIST, filters)),

  listEgressRules: (filters: PageRequest = {}) => getPage<EgressRule>(withQuery(ENDPOINTS.EGRESS_RULES.LIST, filters)),
  createEgressRule: (body: EgressRuleRequest) => post<EgressRule>(ENDPOINTS.EGRESS_RULES.CREATE, body),
  updateEgressRule: (id: string, body: Partial<EgressRuleRequest>) => patch<EgressRule>(ENDPOINTS.EGRESS_RULES.UPDATE(id), body),
  deactivateEgressRule: (id: string) => remove(ENDPOINTS.EGRESS_RULES.DELETE(id)),
  listEgressRequests: (filters: EvidenceFilters = {}) => getPage<EgressRequest>(withQuery(ENDPOINTS.EGRESS_REQUESTS.LIST, filters)),

  listSecrets: (filters: PageRequest = {}) => getPage<SecretMetadata>(withQuery(ENDPOINTS.SECRETS.LIST, filters)),
  createSecret: (body: SecretCreateRequest) => post<SecretMetadata>(ENDPOINTS.SECRETS.CREATE, body),
  rotateSecret: (id: string, body: SecretRotateRequest) => post<SecretMetadata>(ENDPOINTS.SECRETS.ROTATE(id), body),
  deactivateSecret: (id: string, body: LifecycleRequest) => post<SecretMetadata>(ENDPOINTS.SECRETS.DEACTIVATE(id), body),
  listSecretAccesses: (filters: EvidenceFilters = {}) => getPage<SecretAccess>(withQuery(ENDPOINTS.SECRET_ACCESSES.LIST, filters)),

  listQuotas: (filters: PageRequest = {}) => getPage<Quota>(withQuery(ENDPOINTS.QUOTAS.LIST, filters)),
  listQuotaUsage: (filters: EvidenceFilters = {}) => getPage<QuotaUsage>(withQuery(ENDPOINTS.QUOTA_USAGE.LIST, filters)),
  listTokenUsage: (filters: EvidenceFilters = {}) => getPage<TokenUsage>(withQuery(ENDPOINTS.TOKEN_USAGE.LIST, filters)),
  listCostRecords: (filters: EvidenceFilters = {}) => getPage<CostRecord>(withQuery(ENDPOINTS.COST_RECORDS.LIST, filters)),
  listCostSummaries: (filters: EvidenceFilters = {}) => getPage<CostSummary>(withQuery(ENDPOINTS.COST_SUMMARIES.LIST, filters)),
  recalculateCosts: (body: CostRecalculationRequest) => post<AsyncJob>(ENDPOINTS.COST_SUMMARIES.RECALCULATE, body),
  listSaturation: (filters: EvidenceFilters = {}) => getPage<ShardSaturation>(withQuery(ENDPOINTS.SATURATION.LIST, filters)),

  listKillSwitches: (filters: PageRequest = {}) => getPage<KillSwitch>(withQuery(ENDPOINTS.KILL_SWITCHES.LIST, filters)),
  activateKillSwitch: (body: KillSwitchActivateRequest) => post<KillSwitch>(ENDPOINTS.KILL_SWITCHES.CREATE, body),
  deactivateKillSwitch: (id: string, body: LifecycleRequest) => post<KillSwitch>(ENDPOINTS.KILL_SWITCHES.DEACTIVATE(id), body),

  listAuditEvents: (filters: AuditFilters = {}) => getPage<AuditEvent>(withQuery(ENDPOINTS.AUDIT_EVENTS.LIST, filters)),
  listAuditTrails: (filters: EvidenceFilters = {}) => getPage<AuditTrail>(withQuery(ENDPOINTS.AUDIT_TRAILS.LIST, filters)),
  getAuditTrail: (id: string) => get<AuditTrail>(ENDPOINTS.AUDIT_TRAILS.DETAIL(id)),
  listJobs: (filters: PageRequest = {}) => getPage<AsyncJob>(withQuery(ENDPOINTS.JOBS.LIST, filters)),
  getJob: (id: string) => get<AsyncJob>(ENDPOINTS.JOBS.DETAIL(id)),
  getHealth: () => get<ModuleHealth>(ENDPOINTS.HEALTH),
};

export type AiAgentService = typeof aiAgentService;
