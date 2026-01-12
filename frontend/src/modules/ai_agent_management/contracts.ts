/**
 * AI Agent Management Module - Type Contracts & Endpoint Registry
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for AI Agent Management are defined here.
 *
 * DO NOT:
 * - Define ad-hoc types in page components
 * - Hardcode URL strings in service files
 * - Import directly from @/types/api in pages
 *
 * DO:
 * - Import types from this file
 * - Use ENDPOINTS constant for all API calls
 * - Add new types here when extending the module
 *
 * @module ai_agent_management/contracts
 */

import type { components } from '@/types/api';

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Agent entity */
export type Agent = components['schemas']['Agent'];

/** Agent request (for create/update) */
export type AgentRequest = components['schemas']['AgentRequest'];

/** Agent create request (alias for AgentRequest) */
export type AgentCreate = AgentRequest;

/** Agent update request (partial) */
export type AgentUpdate = components['schemas']['PatchedAgentRequest'];

/** Agent execution entity */
export type AgentExecution = components['schemas']['AgentExecution'];

/** Agent scheduler task entity */
export type AgentSchedulerTask = components['schemas']['AgentSchedulerTask'];

/** Approval request entity */
export type ApprovalRequest = components['schemas']['ApprovalRequest'];

/** Approval request (for create/update) */
export type ApprovalRequestRequest = components['schemas']['ApprovalRequestRequest'];

/** Approval request update (partial) */
export type ApprovalRequestUpdate = components['schemas']['PatchedApprovalRequestRequest'];

/** SoD (Separation of Duties) policy entity */
export type SoDPolicy = components['schemas']['SoDPolicy'];

/** SoD policy request (for create/update) */
export type SoDPolicyRequest = components['schemas']['SoDPolicyRequest'];

/** SoD policy update request (partial) */
export type SoDPolicyUpdate = components['schemas']['PatchedSoDPolicyRequest'];

/** SoD violation entity */
export type SoDViolation = components['schemas']['SoDViolation'];

/** Tenant quota entity */
export type TenantQuota = components['schemas']['TenantQuota'];

/** Quota usage entity */
export type QuotaUsage = components['schemas']['QuotaUsage'];

/** Tool entity */
export type Tool = components['schemas']['Tool'];

/** Tool request (for create/update) */
export type ToolRequest = components['schemas']['ToolRequest'];

/** Tool update request (partial) */
export type ToolUpdate = components['schemas']['PatchedToolRequest'];

/** Tool invocation entity */
export type ToolInvocation = components['schemas']['ToolInvocation'];

/** Identity type enum (user_bound or system_bound) */
export type IdentityType = components['schemas']['IdentityTypeEnum'];

/** Agent execution state enum */
export type ExecutionState = components['schemas']['StateEnum'];

/** Scheduler task status enum */
export type SchedulerTaskStatus = components['schemas']['AgentSchedulerTaskStatusEnum'];

/** Approval status enum */
export type ApprovalStatus = components['schemas']['Status2a4Enum'];

/** Quota type enum */
export type QuotaType = components['schemas']['QuotaTypeEnum'];

/** Period enum for quotas */
export type QuotaPeriod = components['schemas']['PeriodEnum'];

/** Side effect class enum for tools */
export type SideEffectClass = components['schemas']['SideEffectClassEnum'];

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * AI Agent Management API Endpoints
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS, Agent } from './contracts';
 * apiClient.get<Agent[]>(ENDPOINTS.AGENTS.LIST);
 * apiClient.post<void>(ENDPOINTS.AGENTS.EXECUTE('uuid'));
 * ```
 */
export const ENDPOINTS = {
  /** Agent CRUD endpoints */
  AGENTS: {
    /** GET - List all agents */
    LIST: '/api/v1/ai-agents/agents/',
    /** GET - Get agent by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/agents/${id}/` as const,
    /** POST - Create new agent */
    CREATE: '/api/v1/ai-agents/agents/',
    /** PUT - Full update agent */
    UPDATE: (id: string) => `/api/v1/ai-agents/agents/${id}/` as const,
    /** PATCH - Partial update agent */
    PATCH: (id: string) => `/api/v1/ai-agents/agents/${id}/` as const,
    /** DELETE - Delete agent */
    DELETE: (id: string) => `/api/v1/ai-agents/agents/${id}/` as const,
    /** POST - Execute agent */
    EXECUTE: (id: string) => `/api/v1/ai-agents/agents/${id}/execute/` as const,
    /** POST - Pause agent execution */
    PAUSE: (id: string) => `/api/v1/ai-agents/agents/${id}/pause/` as const,
    /** POST - Resume agent execution */
    RESUME: (id: string) => `/api/v1/ai-agents/agents/${id}/resume/` as const,
    /** POST - Terminate agent execution */
    TERMINATE: (id: string) => `/api/v1/ai-agents/agents/${id}/terminate/` as const,
  },

  /** Agent Execution endpoints */
  EXECUTIONS: {
    /** GET - List all executions */
    LIST: '/api/v1/ai-agents/executions/',
    /** GET - Get execution by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/executions/${id}/` as const,
  },

  /** Scheduler Task endpoints */
  SCHEDULER_TASKS: {
    /** GET - List all scheduler tasks */
    LIST: '/api/v1/ai-agents/scheduler-tasks/',
    /** GET - Get scheduler task by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/scheduler-tasks/${id}/` as const,
    /** POST - Create scheduler task */
    CREATE: '/api/v1/ai-agents/scheduler-tasks/',
    /** DELETE - Delete scheduler task */
    DELETE: (id: string) => `/api/v1/ai-agents/scheduler-tasks/${id}/` as const,
  },

  /** Approval Request endpoints */
  APPROVALS: {
    /** GET - List all approval requests */
    LIST: '/api/v1/ai-agents/approvals/',
    /** GET - Get approval request by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/approvals/${id}/` as const,
    /** POST - Create approval request */
    CREATE: '/api/v1/ai-agents/approvals/',
    /** POST - Approve request */
    APPROVE: (id: string) => `/api/v1/ai-agents/approvals/${id}/approve/` as const,
    /** POST - Reject request */
    REJECT: (id: string) => `/api/v1/ai-agents/approvals/${id}/reject/` as const,
  },

  /** SoD Policy endpoints */
  SOD_POLICIES: {
    /** GET - List all SoD policies */
    LIST: '/api/v1/ai-agents/sod-policies/',
    /** GET - Get SoD policy by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/sod-policies/${id}/` as const,
    /** POST - Create SoD policy */
    CREATE: '/api/v1/ai-agents/sod-policies/',
    /** PATCH - Update SoD policy */
    UPDATE: (id: string) => `/api/v1/ai-agents/sod-policies/${id}/` as const,
    /** DELETE - Delete SoD policy */
    DELETE: (id: string) => `/api/v1/ai-agents/sod-policies/${id}/` as const,
  },

  /** SoD Violation endpoints */
  SOD_VIOLATIONS: {
    /** GET - List all SoD violations */
    LIST: '/api/v1/ai-agents/sod-violations/',
    /** GET - Get SoD violation by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/sod-violations/${id}/` as const,
  },

  /** Quota endpoints */
  QUOTAS: {
    /** GET - List all tenant quotas */
    LIST: '/api/v1/ai-agents/quotas/',
    /** GET - Get quota by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/quotas/${id}/` as const,
  },

  /** Quota Usage endpoints */
  QUOTA_USAGE: {
    /** GET - List quota usage records */
    LIST: '/api/v1/ai-agents/quota-usage/',
    /** GET - Get quota usage by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/quota-usage/${id}/` as const,
  },

  /** Tool endpoints */
  TOOLS: {
    /** GET - List all tools */
    LIST: '/api/v1/ai-agents/tools/',
    /** GET - Get tool by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/tools/${id}/` as const,
    /** POST - Register tool */
    CREATE: '/api/v1/ai-agents/tools/',
    /** PATCH - Update tool */
    UPDATE: (id: string) => `/api/v1/ai-agents/tools/${id}/` as const,
    /** DELETE - Unregister tool */
    DELETE: (id: string) => `/api/v1/ai-agents/tools/${id}/` as const,
  },

  /** Tool Invocation endpoints */
  TOOL_INVOCATIONS: {
    /** GET - List tool invocations */
    LIST: '/api/v1/ai-agents/tool-invocations/',
    /** GET - Get tool invocation by ID */
    DETAIL: (id: string) => `/api/v1/ai-agents/tool-invocations/${id}/` as const,
  },

  /** Health check endpoint */
  HEALTH: '/api/v1/ai-agents/health/',
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

/** Check if a value is a valid IdentityType */
export function isIdentityType(value: unknown): value is IdentityType {
  return value === 'user_bound' || value === 'system_bound';
}

/** Check if a value is a valid ExecutionState */
export function isExecutionState(value: unknown): value is ExecutionState {
  return (
    value === 'created' ||
    value === 'validated' ||
    value === 'running' ||
    value === 'paused' ||
    value === 'completed' ||
    value === 'failed' ||
    value === 'terminated'
  );
}

/** Check if a value is a valid SchedulerTaskStatus */
export function isSchedulerTaskStatus(value: unknown): value is SchedulerTaskStatus {
  return (
    value === 'pending' ||
    value === 'running' ||
    value === 'completed' ||
    value === 'failed' ||
    value === 'cancelled'
  );
}

/** Check if a value is a valid ApprovalStatus */
export function isApprovalStatus(value: unknown): value is ApprovalStatus {
  return (
    value === 'pending' ||
    value === 'approved' ||
    value === 'rejected' ||
    value === 'expired' ||
    value === 'cancelled'
  );
}

/** Check if a value is a valid QuotaType */
export function isQuotaType(value: unknown): value is QuotaType {
  return (
    value === 'token_count' ||
    value === 'request_count' ||
    value === 'execution_time' ||
    value === 'tool_calls' ||
    value === 'external_api_calls' ||
    value === 'data_volume'
  );
}

/** Check if a value is a valid QuotaPeriod */
export function isQuotaPeriod(value: unknown): value is QuotaPeriod {
  return (
    value === 'hourly' || value === 'daily' || value === 'weekly' || value === 'monthly'
  );
}

/** Check if a value is a valid SideEffectClass */
export function isSideEffectClass(value: unknown): value is SideEffectClass {
  return (
    value === 'read_only' ||
    value === 'workflow_transition' ||
    value === 'data_mutation' ||
    value === 'external_integration'
  );
}

// =============================================================================
// RESPONSE SHAPES - For custom API responses not in OpenAPI schema
// =============================================================================

/** Agent action response (execute/pause/resume/terminate) */
export interface AgentActionResponse {
  status: string;
  message: string;
  execution_id?: string;
}

/** Approval action response (approve/reject) */
export interface ApprovalActionResponse {
  status: string;
  message: string;
  approval_id: string;
}

// =============================================================================
// EXAMPLES - Reference for agents writing new code
// =============================================================================

/**
 * Example usage patterns for agents:
 *
 * ```typescript
 * // Importing types
 * import {
 *   Agent,
 *   AgentRequest,
 *   AgentExecution,
 *   ApprovalRequest,
 *   ENDPOINTS,
 *   AgentActionResponse,
 * } from './contracts';
 *
 * // Listing agents
 * const agents = await apiClient.get<Agent[]>(ENDPOINTS.AGENTS.LIST);
 *
 * // Creating an agent
 * const newAgent: AgentRequest = {
 *   name: 'Invoice Processor',
 *   identity_type: 'user_bound',
 *   subject_id: userId,
 *   framework: 'langgraph',
 * };
 * const created = await apiClient.post<Agent>(ENDPOINTS.AGENTS.CREATE, newAgent);
 *
 * // Executing an agent
 * const result = await apiClient.post<AgentActionResponse>(
 *   ENDPOINTS.AGENTS.EXECUTE(agentId),
 *   { task_definition: { goal: 'Process pending invoices' } }
 * );
 *
 * // Approving a request
 * const approved = await apiClient.post<ApprovalActionResponse>(
 *   ENDPOINTS.APPROVALS.APPROVE(approvalId)
 * );
 *
 * // Using with TanStack Query
 * const { data: agents } = useQuery({
 *   queryKey: ['ai-agents', 'agents'],
 *   queryFn: () => apiClient.get<Agent[]>(ENDPOINTS.AGENTS.LIST),
 * });
 * ```
 */

/**
 * EXAMPLES - Type-safe examples for AI agents
 *
 * These examples use `satisfies` to ensure type correctness at compile time.
 */
export const EXAMPLES = {
  createAgent: {
    request: {
      name: 'Invoice Processor',
      description: 'Processes invoices automatically',
      identity_type: 'user_bound',
      subject_id: 'user-123',
      framework: 'langgraph',
    } satisfies AgentRequest,
    response: {
      id: 'agent-uuid-123',
      name: 'Invoice Processor',
      description: 'Processes invoices automatically',
      identity_type: 'user_bound',
      subject_id: 'user-123',
      framework: 'langgraph',
      is_active: true,
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as Agent,
  },
  executeAgent: {
    request: {
      task_definition: {
        goal: 'Process pending invoices',
        context: { batch_id: 'batch-123' },
      },
      metadata: { priority: 'high' },
    },
    response: {
      id: 'execution-uuid-456',
      agent_id: 'agent-uuid-123',
      state: 'running',
      started_at: '2026-01-07T00:00:00Z',
    } as AgentExecution,
  },
} as const;
