/* eslint-disable max-lines, max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- page coverage needs complete governed fixtures and typed mock-call payload inspection. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AgentDetail,
  AgentManagementConfiguration,
  AgentManagementConfigurationDocument,
  AgentManagementConfigurationVersion,
  AgentExecutionListItem,
  AgentExecutionDetail,
  AuditEvent,
  AuditTrail,
  CostSummary,
  PageResult,
  Quota,
  ShardSaturation,
  TokenUsage,
  ToolDetail,
  ToolListItem,
  ScheduleListItem,
} from "../contracts";
import { AgentDetailPage } from "./AgentDetailPage";
import { AuditExplorerPage } from "./AuditExplorerPage";
import { ConfigurationPage } from "./ConfigurationPage";
import { CreateAgentPage } from "./CreateAgentPage";
import { EditAgentPage } from "./EditAgentPage";
import { ExecutionListPage } from "./ExecutionListPage";
import { ExecutionDetailPage } from "./ExecutionDetailPage";
import { GovernancePage } from "./GovernancePage";
import { ScheduleListPage } from "./ScheduleListPage";
import { ScheduleCreatePage } from "./ScheduleCreatePage";
import { ToolCreatePage } from "./ToolCreatePage";
import { ToolEditPage } from "./ToolEditPage";
import { ToolListPage } from "./ToolListPage";
import { UsagePage } from "./UsagePage";

const mocks = vi.hoisted(() => ({
  activateAgent: vi.fn(),
  activateKillSwitch: vi.fn(),
  createAgent: vi.fn(),
  createEgressRule: vi.fn(),
  createSchedule: vi.fn(),
  createSecret: vi.fn(),
  createSoDPolicy: vi.fn(),
  createTool: vi.fn(),
  executeAgent: vi.fn(),
  exportConfiguration: vi.fn(),
  getAgent: vi.fn(),
  getConfiguration: vi.fn(),
  getExecution: vi.fn(),
  getTool: vi.fn(),
  importConfiguration: vi.fn(),
  listAgents: vi.fn(),
  listApprovals: vi.fn(),
  listAuditEvents: vi.fn(),
  listAuditTrails: vi.fn(),
  listConfigurationVersions: vi.fn(),
  listCostSummaries: vi.fn(),
  listCostRecords: vi.fn(),
  listEgressRules: vi.fn(),
  listExecutions: vi.fn(),
  listKillSwitches: vi.fn(),
  listQuotas: vi.fn(),
  listSecretAccesses: vi.fn(),
  listSecrets: vi.fn(),
  listSaturation: vi.fn(),
  listSchedules: vi.fn(),
  listSoDPolicies: vi.fn(),
  listSoDViolations: vi.fn(),
  listTokenUsage: vi.fn(),
  listTools: vi.fn(),
  listToolInvocations: vi.fn(),
  listEgressRequests: vi.fn(),
  previewConfiguration: vi.fn(),
  pauseExecution: vi.fn(),
  resumeExecution: vi.fn(),
  rollbackConfiguration: vi.fn(),
  terminateExecution: vi.fn(),
  updateTool: vi.fn(),
  updateAgent: vi.fn(),
  updateConfiguration: vi.fn(),
}));

vi.mock("../services/ai-agent-service", () => ({ aiAgentService: mocks }));

const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function page<T>(items: readonly T[]): PageResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length },
    correlationId: "corr-page",
    receivedAt: "2026-07-28T00:00:00Z",
  };
}

const documentFixture: AgentManagementConfigurationDocument = {
  schema_version: "1.0",
  provider: {
    max_tokens: 4096,
    temperature: 0.2,
    timeout_seconds: 30,
    max_retries: 2,
    retry_backoff_seconds: 1,
    circuit_failure_threshold: 5,
    circuit_reset_seconds: 60,
  },
  runner: {
    allowed_task_fields: ["goal"],
    maximum_messages: 20,
    allowed_roles: ["operator"],
  },
  registry: { key_maximum_length: 120 },
  agent: {
    metadata_fields: ["owner"],
    transition_key_maximum_length: 120,
    execution_idempotency_key_maximum_length: 120,
    search_maximum_length: 120,
    ordering_fields: ["name", "-updated_at"],
    transition_reason_maximum_length: 500,
    error_code_maximum_length: 80,
    user_bound_requires_active_session: true,
    only_active_agents_may_execute: true,
    identity_session_rules: {
      user_bound_requires_session: true,
      system_bound_forbids_session: true,
    },
    execution_state_transitions: { created: ["queued"] },
  },
  schedule: {
    default_priority: 5,
    priority_minimum: 1,
    priority_maximum: 10,
    default_maximum_retries: 1,
    maximum_retries_limit: 5,
    dispatch_batch_minimum: 1,
    dispatch_batch_maximum: 50,
  },
  approval: {
    require_for_non_read_only_tools: true,
    requester_may_approve_own_request: false,
    enforce_expiry: true,
    rejection_requires_reason: true,
    only_requester_may_cancel: true,
  },
  separation_of_duties: {
    actions_must_be_nonempty_and_different: true,
    counterpart_detection_enabled: true,
  },
  egress: {
    forbidden_ip_addresses: ["169.254.169.254"],
    internal_hostname_suffixes: [".internal"],
    allowed_url_schemes: ["https"],
    forbid_url_credentials: true,
    forbid_url_query: true,
    forbid_url_fragment: true,
  },
  health: {
    cache_probe_timeout_seconds: 1,
    minimum_rls_table_count: 1,
    outbox_stale_minutes: 10,
  },
  evaluation: {
    quality_pass_threshold: 0.9,
    quality_warn_threshold: 0.75,
    hallucination_pass_threshold: 0.05,
    hallucination_warn_threshold: 0.1,
    max_token_fallback: 2048,
    characters_per_estimated_token: 4,
    minimum_useful_output_length: 50,
    short_output_penalty: 0.25,
    efficiency_pass_threshold: 0.8,
    efficiency_warn_threshold: 0.6,
    latency_percentiles: [50, 95],
  },
  secret: { rotation_interval_minimum_days: 30 },
  ui: {
    agent_page_size: 25,
    execution_page_size: 25,
    execution_poll_interval_ms: 5000,
    approval_page_size: 25,
    approval_poll_interval_ms: 5000,
    schedule_page_size: 25,
    selection_page_size: 25,
    usage_page_size: 25,
    summary_page_size: 25,
    health_poll_interval_ms: 30000,
    saturation_warning_threshold: 0.75,
    saturation_critical_threshold: 0.9,
    status_tokens: {
      success: "status-success",
      info: "status-info",
      warning: "status-warning",
      danger: "status-danger",
      neutral: "status-neutral",
    },
    status_token_by_state: {
      active: "success",
      blocked: "danger",
      draft: "neutral",
      running: "info",
    },
    navigation_order: {
      agents: 1,
      executions: 2,
      schedules: 3,
      approvals: 4,
      tools: 5,
      configuration: 6,
      governance: 7,
      usage: 8,
      audit: 9,
    },
  },
  rollout: { enabled: true, roles: ["operator"], cohorts: [] },
};

const configuration: AgentManagementConfiguration = {
  id: "config-1",
  environment: "production",
  version: 3,
  document: documentFixture,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const version: AgentManagementConfigurationVersion = {
  id: "version-2",
  environment: "production",
  version: 2,
  previous_document: documentFixture,
  document: { ...documentFixture, provider: { ...documentFixture.provider, max_tokens: 2048 } },
  changed_by: "operator-1",
  correlation_id: "corr-version",
  change_type: "update",
  created_at: "2026-07-27T00:00:00Z",
};
const agent: AgentDetail = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "Close books",
  description: "Reconciles ledgers",
  identity_type: "user_bound",
  subject_id: "00000000-0000-4000-8000-000000000011",
  runner_key: "finance_runner",
  provider_config_id: null,
  status: "active",
  active_execution_count: 2,
  config: { cost_ceiling: 20, require_approval: true, tools: ["ledger.read"] },
  transition_history: [],
  deleted_at: null,
  provider_status: "setup_required",
  runner_status: "unavailable",
  quota: { id: "quota-1", resource: "tokens", limit: 1000, consumed: 250, remaining: 750 },
  allowed_actions: ["update", "execute", "activate"],
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const execution: AgentExecutionListItem = {
  id: "00000000-0000-4000-8000-000000000101",
  agent_id: agent.id,
  agent_name: agent.name,
  async_job_id: "00000000-0000-4000-8000-000000000201",
  state: "running",
  started_at: "2026-07-28T00:00:00Z",
  completed_at: null,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  error_code: "",
  allowed_actions: [],
};
const executionDetail: AgentExecutionDetail = {
  ...execution,
  allowed_actions: ["pause", "terminate"],
  error_message: "",
  provider_config_id: null,
  task_definition: { goal: "close books" },
  result: { status: "waiting" },
  transition_history: [
    {
      from: "queued",
      to: "running",
      transition: "dispatch",
      reason: "Worker accepted job",
      occurred_at: "2026-07-28T00:01:00Z",
      actor_id: "00000000-0000-4000-8000-000000000501",
      correlation_id: "00000000-0000-4000-8000-000000000504",
    },
  ],
};
const schedule: ScheduleListItem = {
  id: "00000000-0000-4000-8000-000000000701",
  agent_id: agent.id,
  agent_name: agent.name,
  execution_id: null,
  async_job_id: null,
  scheduled_at: "2026-07-29T04:00:00Z",
  priority: 5,
  retry_count: 1,
  max_retries: 3,
  status: "pending",
  created_at: "2026-07-28T00:00:00Z",
};
const tool: ToolDetail = {
  id: "00000000-0000-4000-8000-000000000401",
  name: "ledger.lookup",
  owning_module: "accounting_finance",
  version: "1.2.0",
  description: "Looks up ledger facts",
  side_effect_class: "read_only",
  is_active: true,
  required_permissions: ["accounting.ledger:read", "audit.evidence:read"],
  registered_at: "2026-07-28T00:00:00Z",
  input_schema: { type: "object", required: ["ledger_id"] },
  output_schema: { type: "object", additionalProperties: false },
  metadata: { owner: "finance" },
  registered_by: "00000000-0000-4000-8000-000000000411",
  updated_at: "2026-07-28T00:00:00Z",
};
const quota: Quota = {
  id: "quota-usage",
  resource: "tokens",
  limit: 1000,
  consumed: 400,
  remaining: 600,
};
const tokenUsage: TokenUsage = {
  id: "token-usage-1",
  agent_execution_id: execution.id,
  provider: "openai",
  model: "gpt-4.1",
  input_tokens: 200,
  output_tokens: 150,
  total_tokens: 350,
  usage_timestamp: "2026-07-28T00:00:00Z",
};
const costSummary: CostSummary = {
  id: "cost-summary-1",
  period_start: "2026-07-28T00:00:00Z",
  period_end: "2026-07-28T01:00:00Z",
  period_type: "hourly",
  total_cost: "1.2500",
  currency: "USD",
  total_tokens: 350,
  total_executions: 2,
  calculated_at: "2026-07-28T01:01:00Z",
  cost_by_type: { token: 1.25 },
  cost_by_module: { accounting_finance: 1.25 },
  cost_by_provider: { openai: 1.25 },
};
const saturation: ShardSaturation = {
  id: "saturation-1",
  shard_id: "tenant-shard-a",
  saturation_level: "0.95",
  active_agents: 3,
  active_executions: 9,
  cpu_usage_percent: "91.0",
  memory_usage_percent: "87.5",
  measured_at: "2026-07-28T00:00:00Z",
};
const auditEvent: AuditEvent = {
  id: "audit-event-1",
  event_type: "tool.invocation.blocked",
  agent_execution_id: execution.id,
  tool_invocation_id: null,
  approval_request_id: null,
  initiating_principal: "00000000-0000-4000-8000-000000000501",
  subject_id: "00000000-0000-4000-8000-000000000502",
  session_id: null,
  request_id: "00000000-0000-4000-8000-000000000503",
  correlation_id: "00000000-0000-4000-8000-000000000504",
  event_timestamp: "2026-07-28T00:00:00Z",
  outcome: "blocked",
  decisions: { reason: "side_effect" },
  transitions: {},
  resources: { tool_id: tool.id },
  metadata: { policy: "approval_required" },
};
const auditTrail: AuditTrail = {
  id: "00000000-0000-4000-8000-000000000601",
  request_id: "00000000-0000-4000-8000-000000000503",
  correlation_id: auditEvent.correlation_id,
  agent_execution_id: execution.id,
  initiating_principal: "00000000-0000-4000-8000-000000000501",
  request_timestamp: "2026-07-28T00:00:00Z",
  completed_timestamp: null,
  final_outcome: null,
  summary: { events: 1 },
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderRoute(element: React.ReactElement, pattern = "*", path = "/ai-agents") {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path={pattern}
            element={
              <>
                {element}
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getConfiguration.mockResolvedValue(configuration);
  mocks.listConfigurationVersions.mockResolvedValue([
    version,
    { ...version, id: "version-3", version: 3 },
  ]);
  mocks.previewConfiguration.mockResolvedValue({
    valid: true,
    changed: true,
    current_version: 3,
    proposed_version: 4,
    changes: [{ path: "provider.max_tokens", before: 4096, after: 8192 }],
  });
  mocks.updateConfiguration.mockResolvedValue({ ...configuration, version: 4 });
  mocks.rollbackConfiguration.mockResolvedValue({ ...configuration, version: 4 });
  mocks.importConfiguration.mockResolvedValue({ ...configuration, version: 4 });
  mocks.exportConfiguration.mockResolvedValue({
    schema: "saraise.ai-agent-management.configuration/v1",
    environment: "production",
    version: 3,
    configuration: documentFixture,
  });
  mocks.createAgent.mockResolvedValue({ ...agent, id: "00000000-0000-4000-8000-000000000099" });
  mocks.updateAgent.mockResolvedValue(agent);
  mocks.getAgent.mockResolvedValue(agent);
  mocks.getExecution.mockResolvedValue(executionDetail);
  mocks.listExecutions.mockResolvedValue(page([execution]));
  mocks.listSchedules.mockResolvedValue(page([schedule]));
  mocks.createSchedule.mockResolvedValue({
    id: "00000000-0000-4000-8000-000000000701",
  });
  mocks.listApprovals.mockResolvedValue(
    page([
      {
        id: "00000000-0000-4000-8000-000000000901",
        tool_id: tool.id,
        tool_name: tool.name,
        agent_execution_id: execution.id,
        requested_by: "00000000-0000-4000-8000-000000000501",
        requested_for: "00000000-0000-4000-8000-000000000502",
        approver_id: null,
        status: "pending",
        justification: "Requires side-effect approval",
        requested_at: "2026-07-28T00:02:00Z",
        expires_at: null,
        decided_at: null,
      },
    ])
  );
  mocks.listToolInvocations.mockResolvedValue(
    page([
      {
        id: "00000000-0000-4000-8000-000000000902",
        tool_id: tool.id,
        tool_name: tool.name,
        agent_execution_id: execution.id,
        approval_request_id: null,
        status: "blocked",
        input_data: { ledger_id: "ledger-1" },
        output_data: null,
        error_code: "APPROVAL_REQUIRED",
        error_message: "Approval required before invocation.",
        invoked_at: "2026-07-28T00:02:30Z",
        completed_at: null,
        duration_ms: null,
      },
    ])
  );
  mocks.listEgressRequests.mockResolvedValue(
    page([
      {
        id: "00000000-0000-4000-8000-000000000801",
        agent_execution_id: execution.id,
        destination: "api.example.com",
        resolved_address: "203.0.113.10",
        port: 443,
        protocol: "https",
        allowed: false,
        matched_rule_id: null,
        reason_code: "EGRESS_POLICY_DENIED",
        requested_at: "2026-07-28T00:03:00Z",
      },
    ])
  );
  mocks.listCostRecords.mockResolvedValue(
    page([
      {
        id: "00000000-0000-4000-8000-000000000903",
        agent_execution_id: execution.id,
        tool_invocation_id: null,
        module_name: "accounting_finance",
        cost_type: "token",
        provider: "openai",
        amount: "1.2500",
        currency: "USD",
        pricing_version: "2026-07",
        pricing_available: true,
        cost_timestamp: "2026-07-28T00:04:00Z",
      },
    ])
  );
  mocks.listAuditEvents.mockResolvedValue(page([auditEvent]));
  mocks.listAuditTrails.mockResolvedValue(page([auditTrail]));
  mocks.listQuotas.mockResolvedValue(page([quota]));
  mocks.listTokenUsage.mockResolvedValue(page([tokenUsage]));
  mocks.listCostSummaries.mockResolvedValue(page([costSummary]));
  mocks.listSaturation.mockResolvedValue(page([saturation]));
  mocks.listTools.mockResolvedValue(page<ToolListItem>([tool]));
  mocks.getTool.mockResolvedValue(tool);
  mocks.createTool.mockResolvedValue({ ...tool, id: "00000000-0000-4000-8000-000000000499" });
  mocks.updateTool.mockResolvedValue({ ...tool, description: "Updated descriptor" });
  mocks.activateAgent.mockResolvedValue(agent);
  mocks.executeAgent.mockResolvedValue({ id: "00000000-0000-4000-8000-000000000301" });
  mocks.pauseExecution.mockResolvedValue({ ...executionDetail, state: "paused" });
  mocks.resumeExecution.mockResolvedValue({ ...executionDetail, state: "running" });
  mocks.terminateExecution.mockResolvedValue({
    ...executionDetail,
    state: "cancelled",
    allowed_actions: [],
  });
  mocks.listSoDPolicies.mockResolvedValue(
    page([
      {
        id: "sod-1",
        name: "Maker checker",
        description: "",
        action_1: "invoice.prepare",
        action_2: "invoice.approve",
        is_active: true,
        created_at: "2026-07-28T00:00:00Z",
        updated_at: "2026-07-28T00:00:00Z",
      },
    ])
  );
  mocks.listEgressRules.mockResolvedValue(page([]));
  mocks.listKillSwitches.mockResolvedValue(page([]));
  mocks.listSecrets.mockResolvedValue(page([]));
  mocks.listSoDViolations.mockResolvedValue(
    page([
      {
        id: "violation-1",
        policy_id: "sod-1",
        policy_name: "Maker checker",
        agent_execution_id: null,
        tool_invocation_id: null,
        action_1_user: "user-1",
        action_2_user: "user-2",
        blocked: true,
        violation_at: "2026-07-28T00:00:00Z",
        evidence: {},
      },
    ])
  );
  mocks.listSecretAccesses.mockResolvedValue(
    page([
      {
        id: "secret-access-1",
        secret_id: "secret-1",
        secret_name: "Provider key", // pragma: allowlist secret
        agent_execution_id: null,
        accessed_by: "user-1",
        accessed_at: "2026-07-28T00:00:00Z",
        purpose: "provider call",
      },
    ])
  );
  mocks.createSoDPolicy.mockResolvedValue({ id: "sod-2" });
  mocks.createEgressRule.mockResolvedValue({ id: "egress-1" });
  mocks.activateKillSwitch.mockResolvedValue({ id: "switch-1" });
  mocks.createSecret.mockResolvedValue({ id: "secret-1" });
});

describe("AI agent configuration, governance, form, and detail coverage", () => {
  it("previews, applies, imports, exports, and rolls back runtime configuration", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn().mockReturnValue("blob:config");
    const revokeObjectURL = vi.fn();
    const linkClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    renderRoute(<ConfigurationPage />);

    expect(await screen.findByText("Runtime configuration")).toBeInTheDocument();
    const maxTokens = screen.getByDisplayValue("4096");
    await user.clear(maxTokens);
    await user.type(maxTokens, "8192");
    await user.click(screen.getByRole("button", { name: "Validate preview" }));
    expect(await screen.findByText(/Proposed version: 4/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply configuration" }));
    expect(mocks.updateConfiguration).toHaveBeenCalledTimes(1);
    const updateCalls = mocks.updateConfiguration.mock.calls as unknown as readonly [
      {
        readonly document: AgentManagementConfigurationDocument;
        readonly environment: string;
        readonly expected_version: number;
      },
    ][];
    expect(updateCalls[0]?.[0].document.provider.max_tokens).toBe(8192);
    expect(updateCalls[0]?.[0].environment).toBe("production");
    expect(updateCalls[0]?.[0].expected_version).toBe(3);

    fireEvent.change(screen.getByLabelText("Configuration import document"), {
      target: {
        value: JSON.stringify({
          schema: "saraise.ai-agent-management.configuration/v1",
          environment: "production",
          version: 4,
          configuration: documentFixture,
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Validate and import" }));
    expect(mocks.importConfiguration).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Export current version" }));
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:config");
    await user.click(screen.getAllByRole("button", { name: "Rollback" })[0]!);
    expect(mocks.rollbackConfiguration).toHaveBeenCalledWith({
      environment: "production",
      target_version: 2,
    });
    linkClick.mockRestore();
  });

  it("blocks invalid configuration before server preview", async () => {
    const user = userEvent.setup();
    renderRoute(<ConfigurationPage />);

    await screen.findByText("Runtime configuration");
    const temperature = screen.getByDisplayValue("0.2");
    await user.clear(temperature);
    await user.type(temperature, "3");
    expect(screen.getByRole("alert")).toHaveTextContent("Temperature must be between 0 and 2.");
    expect(screen.getByRole("button", { name: "Validate preview" })).toBeDisabled();
  });

  it("validates create form identity rules and submits enriched governed config", async () => {
    const user = userEvent.setup();
    renderRoute(<CreateAgentPage />);

    await user.click(screen.getByRole("button", { name: "Create draft agent" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Name, subject, and runner are required.");
    await user.type(screen.getByLabelText("Name"), "Post accruals");
    await user.type(screen.getByLabelText("Runner key"), "finance_runner");
    await user.type(screen.getByLabelText("Subject ID"), "00000000-0000-4000-8000-000000000011");
    await user.click(screen.getByRole("button", { name: "Create draft agent" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "A user-bound agent requires a session ID."
    );
    await user.type(screen.getByLabelText("Session ID"), "00000000-0000-4000-8000-000000000012");
    await user.type(screen.getByLabelText("Tool keys"), "invoice.read, workflow.submit");
    await user.type(screen.getByLabelText("Cost ceiling"), "25.5");
    await user.click(screen.getByLabelText("Require approval for governed side effects"));
    fireEvent.change(screen.getByLabelText("Runtime configuration (JSON object)"), {
      target: { value: '{"owner":"finance"}' },
    });
    await user.click(screen.getByRole("button", { name: "Create draft agent" }));

    expect(mocks.createAgent).toHaveBeenCalledWith(
      expect.objectContaining({
        config: {
          cost_ceiling: 25.5,
          owner: "finance",
          require_approval: true,
          tools: ["invoice.read", "workflow.submit"],
        },
        identity_type: "user_bound",
        name: "Post accruals",
      })
    );
    await waitFor(() =>
      expect(screen.getByTestId("path")).toHaveTextContent(
        "/ai-agents/00000000-0000-4000-8000-000000000099"
      )
    );
  });

  it("loads edit form with active-execution warning and submits a PATCH", async () => {
    const user = userEvent.setup();
    renderRoute(
      <EditAgentPage />,
      "/ai-agents/:id/edit",
      "/ai-agents/00000000-0000-4000-8000-000000000001/edit"
    );

    expect(await screen.findByText("Edit Close books")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("2 active execution");
    await user.type(screen.getByLabelText("Session ID"), "00000000-0000-4000-8000-000000000012");
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Close books v2");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(mocks.updateAgent).toHaveBeenCalledWith(
      "00000000-0000-4000-8000-000000000001",
      expect.objectContaining({ name: "Close books v2" })
    );
  });

  it("switches governance tabs and creates tenant-scoped controls", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "transition-key-1" });
    renderRoute(<GovernancePage />);

    expect(await screen.findByText("Maker checker")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create SoD policy" }));
    await user.type(screen.getByLabelText("Name"), "Payables split");
    await user.type(screen.getByLabelText("First action"), "payment.prepare");
    await user.type(screen.getByLabelText("Conflicting action"), "payment.release");
    await user.click(screen.getAllByRole("button", { name: "Create SoD policy" })[1]!);
    expect(mocks.createSoDPolicy).toHaveBeenCalledWith({
      action_1: "payment.prepare",
      action_2: "payment.release",
      name: "Payables split",
    });

    await user.click(screen.getByRole("tab", { name: "egress" }));
    await user.click(await screen.findByRole("button", { name: "Create egress rule" }));
    await user.type(screen.getByLabelText("Name"), "Provider API");
    await user.type(screen.getByLabelText("Canonical destination domain"), "api.example.com");
    await user.type(screen.getByLabelText("Port"), "8443");
    await user.click(screen.getAllByRole("button", { name: "Create egress rule" })[1]!);
    expect(mocks.createEgressRule).toHaveBeenCalledWith(
      expect.objectContaining({ destination: "api.example.com", port: 8443 })
    );

    await user.click(screen.getByRole("tab", { name: "Violations & accesses" }));
    expect(await screen.findByText("Recent SoD violations")).toBeInTheDocument();
    expect(screen.getByText("Provider key")).toBeInTheDocument();
  });

  it("renders detail evidence, blocks invalid execution JSON, and executes valid tasks", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "execution-key-1" });
    renderRoute(
      <AgentDetailPage />,
      "/ai-agents/:id",
      "/ai-agents/00000000-0000-4000-8000-000000000001"
    );

    expect(await screen.findByText("Close books")).toBeInTheDocument();
    expect(screen.getByText("Runner unavailable")).toBeInTheDocument();
    expect(screen.getByText("Provider setup required")).toBeInTheDocument();
    expect(screen.getByText(auditEvent.correlation_id)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Task definition JSON"), { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Execute" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Task definition must be a JSON object.");
    fireEvent.change(screen.getByLabelText("Task definition JSON"), {
      target: { value: '{"goal":"close"}' },
    });
    await user.click(screen.getByRole("button", { name: "Execute" }));
    expect(mocks.executeAgent).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000001", {
      idempotency_key: "execution-key-1",
      task: { goal: "close" },
    });
  });

  it("renders usage evidence, pricing unavailability, and critical saturation", async () => {
    mocks.listCostSummaries.mockResolvedValueOnce(page([{ ...costSummary, currency: "" }]));
    const user = userEvent.setup();
    renderRoute(<UsagePage />);

    expect(await screen.findByText("Usage and cost")).toBeInTheDocument();
    expect(mocks.listQuotas).toHaveBeenCalledWith({ page_size: 25 });
    expect(mocks.listTokenUsage).toHaveBeenCalledWith({ page_size: 25 });
    expect(screen.getByText("Pricing unavailable")).toBeInTheDocument();
    expect(screen.getByText("600")).toBeInTheDocument();
    expect(screen.getByText("openai / gpt-4.1")).toBeInTheDocument();
    expect(screen.getByText("tenant-shard-a · 9 active executions")).toBeInTheDocument();

    mocks.listQuotas.mockRejectedValueOnce(new Error("quota store unavailable"));
    renderRoute(<UsagePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("quota store unavailable");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mocks.listQuotas).toHaveBeenCalledTimes(3));
  });

  it("filters audit evidence and navigates correlated trails", async () => {
    const user = userEvent.setup();
    renderRoute(<AuditExplorerPage />);

    expect(await screen.findByText("Audit explorer")).toBeInTheDocument();
    const from = screen.getByLabelText("From");
    const to = screen.getByLabelText("To");
    const correlationId = screen.getByLabelText("Correlation ID");
    const outcome = screen.getByLabelText("Outcome");
    fireEvent.change(from, { target: { value: "2026-07-28T01:00" } });
    fireEvent.change(to, { target: { value: "2026-07-29T01:00" } });
    fireEvent.change(correlationId, { target: { value: "corr-target" } });
    fireEvent.change(outcome, { target: { value: "blocked" } });

    await waitFor(() =>
      expect(mocks.listAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 1,
          page_size: 25,
          start: "2026-07-28T01:00",
        })
      )
    );
    await user.click(screen.getByRole("link", { name: auditEvent.correlation_id }));
    expect(screen.getByTestId("path")).toHaveTextContent(
      "/ai-agents/audit/00000000-0000-4000-8000-000000000601"
    );
  });

  it("filters execution monitor evidence and fail-closes on missing governed response", async () => {
    const user = userEvent.setup();
    renderRoute(<ExecutionListPage />);

    expect(await screen.findByText("Execution monitor")).toBeInTheDocument();
    expect(screen.getByText("Close books")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("State"), { target: { value: "failed" } });
    await waitFor(() =>
      expect(mocks.listExecutions).toHaveBeenLastCalledWith(
        expect.objectContaining({
          ordering: "-created_at",
          page: 1,
          page_size: 25,
          state: "failed",
        })
      )
    );
    await user.click(screen.getByRole("button", { name: "Refresh evidence" }));
    await waitFor(() => expect(mocks.listExecutions).toHaveBeenCalledTimes(3));

    mocks.listExecutions.mockResolvedValueOnce(undefined);
    renderRoute(<ExecutionListPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("data is undefined");
  });

  it("renders execution detail evidence and sends guarded command payloads", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "transition-key-1" });
    renderRoute(
      <ExecutionDetailPage />,
      "/ai-agents/executions/:id",
      "/ai-agents/executions/00000000-0000-4000-8000-000000000101"
    );

    expect(await screen.findByText("Execution evidence")).toBeInTheDocument();
    expect(screen.getByText("Durable job")).toBeInTheDocument();
    expect(screen.getByLabelText("Task definition")).toHaveTextContent("close books");
    expect(screen.getByText("Tool · ledger.lookup")).toBeInTheDocument();
    expect(screen.getByText("Egress · api.example.com")).toBeInTheDocument();
    expect(screen.getByText("blocked · EGRESS_POLICY_DENIED")).toBeInTheDocument();
    expect(mocks.getExecution).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000101");
    expect(mocks.listToolInvocations).toHaveBeenCalledWith({
      execution_id: "00000000-0000-4000-8000-000000000101",
      page_size: 100,
    });
    expect(mocks.listApprovals).toHaveBeenCalledWith({
      execution_id: "00000000-0000-4000-8000-000000000101",
      page_size: 100,
    });
    expect(mocks.listEgressRequests).toHaveBeenCalledWith({
      execution_id: "00000000-0000-4000-8000-000000000101",
      page_size: 100,
    });

    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(mocks.pauseExecution).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000101", {
      transition_key: "pause-transition-key-1",
      reason: undefined,
    });

    vi.spyOn(window, "prompt").mockReturnValue("Operator terminated stalled work");
    await user.click(screen.getByRole("button", { name: "Terminate" }));
    expect(mocks.terminateExecution).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000101", {
      transition_key: "terminate-transition-key-1",
      reason: "Operator terminated stalled work",
    });
  });

  it("filters durable schedules with configured page bounds and fails closed on missing responses", async () => {
    const user = userEvent.setup();
    renderRoute(<ScheduleListPage />);

    expect(await screen.findByText("Durable schedules")).toBeInTheDocument();
    expect(screen.getByText("Close books")).toBeInTheDocument();
    expect(mocks.listSchedules).toHaveBeenCalledWith({
      ordering: "scheduled_at",
      page: 1,
      page_size: 25,
      status: undefined,
    });
    await user.selectOptions(screen.getByLabelText("Status"), "failed");
    await waitFor(() =>
      expect(mocks.listSchedules).toHaveBeenLastCalledWith({
        ordering: "scheduled_at",
        page: 1,
        page_size: 25,
        status: "failed",
      })
    );

    mocks.listSchedules.mockResolvedValueOnce(undefined);
    renderRoute(<ScheduleListPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("data is undefined");
  });

  it("creates schedules only after required agent, time, and object task validation pass", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "schedule-key-1" });
    mocks.listAgents.mockResolvedValue(page([agent]));
    renderRoute(<ScheduleCreatePage />);

    expect(await screen.findByText("Schedule governed work")).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Close books" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active agent"), agent.id);
    await user.type(screen.getByLabelText("Due time"), "2026-07-29T09:30");
    fireEvent.change(screen.getByLabelText("Scheduled task JSON"), { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Task must be a JSON object.");
    fireEvent.change(screen.getByLabelText("Scheduled task JSON"), {
      target: { value: '{"goal":"approve invoices"}' },
    });
    await user.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() => expect(mocks.createSchedule).toHaveBeenCalledTimes(1));
    expect(mocks.createSchedule).toHaveBeenCalledWith(
      expect.objectContaining({
        agent_id: agent.id,
        idempotency_key: "schedule-key-1",
        max_retries: 1,
        priority: 5,
        scheduled_at: "2026-07-29T04:00:00.000Z",
        task_data: { goal: "approve invoices" },
      })
    );
    expect(screen.getByTestId("path")).toHaveTextContent(
      "/ai-agents/schedules/00000000-0000-4000-8000-000000000701"
    );
  });

  it("searches tools and preserves immutable create and edit payload boundaries", async () => {
    const user = userEvent.setup();
    const listRender = renderRoute(<ToolListPage />);

    expect(await screen.findByText("Tool registry")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tool side effects"), {
      target: { value: "read_only" },
    });
    await waitFor(() =>
      expect(mocks.listTools).toHaveBeenLastCalledWith({
        page_size: 100,
        side_effect_class: "read_only",
        search: undefined,
      })
    );
    fireEvent.change(await screen.findByLabelText("Search tools"), { target: { value: "ledger" } });
    await waitFor(() =>
      expect(mocks.listTools).toHaveBeenLastCalledWith({
        page_size: 100,
        search: "ledger",
        side_effect_class: "read_only",
      })
    );
    listRender.unmount();

    const createRender = renderRoute(<ToolCreatePage />);
    await screen.findByText("Register governed tool");
    await user.type(screen.getByLabelText("Name"), "risk.score");
    await user.type(screen.getByLabelText("Owning module"), "compliance_risk_management");
    await user.type(screen.getByLabelText("Tool description"), "Scores tenant risks");
    await user.type(
      screen.getByLabelText("Required permissions"),
      "risk.score:execute, audit:read"
    );
    fireEvent.change(screen.getByLabelText("Input JSON Schema"), { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Save tool" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Schema must be a JSON object.");
    fireEvent.change(screen.getByLabelText("Input JSON Schema"), {
      target: { value: '{"type":"object","required":["risk_id"]}' },
    });
    await user.click(screen.getByRole("button", { name: "Save tool" }));
    expect(mocks.createTool).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "risk.score",
        owning_module: "compliance_risk_management",
        required_permissions: ["risk.score:execute", "audit:read"],
        input_schema: { type: "object", required: ["risk_id"] },
      })
    );
    createRender.unmount();

    renderRoute(
      <ToolEditPage />,
      "/ai-agents/tools/:id/edit",
      "/ai-agents/tools/00000000-0000-4000-8000-000000000401/edit"
    );
    expect(await screen.findByText("Edit ledger.lookup")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeDisabled();
    await user.clear(screen.getByLabelText("Tool description"));
    await user.type(screen.getByLabelText("Tool description"), "Updated descriptor");
    await user.click(screen.getByRole("button", { name: "Save tool" }));
    expect(mocks.updateTool).toHaveBeenCalledWith(
      "00000000-0000-4000-8000-000000000401",
      expect.objectContaining({
        description: "Updated descriptor",
        required_permissions: ["accounting.ledger:read", "audit.evidence:read"],
      })
    );
  });
});
