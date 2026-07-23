import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { GovernedError } from "../components/CustomizationUI";
import { FieldDefinitionListPage } from "../pages/FieldDefinitionListPage";
import { FormListPage } from "../pages/FormListPage";
import { RuleExecutionListPage } from "../pages/RuleExecutionListPage";
import { RuleListPage } from "../pages/RuleListPage";
import { customizationFrameworkService as service } from "../services/customization-framework-service";
import type { RuntimeConfiguration } from "../contracts";

vi.mock("../services/customization-framework-service", () => ({ customizationFrameworkService: { getConfiguration: vi.fn(), listFields: vi.fn(), listForms: vi.fn(), listRules: vi.fn(), listExecutions: vi.fn() } }));
const meta = { correlation_id: "00000000-0000-4000-8000-000000000099", timestamp: "2026-07-22T00:00:00Z", pagination: { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false } } as const;
const runtimeConfiguration = {
  id: "00000000-0000-4000-8000-000000000010", tenant_id: "00000000-0000-4000-8000-000000000011", version: 1, environment: "test",
  document: {
    limits: { json_bytes: 65536, ast_nodes: 256, ast_depth: 16, evaluation_ms: 50, field_key_length: 100, field_label_length: 160, resource_key_length: 120, contract_version_length: 32, form_key_length: 100, form_name_length: 160, change_summary_length: 500, idempotency_key_length: 128, rule_priority_min: 1, rule_priority_max: 1000 },
    policies: { slug_pattern: "^[a-z][a-z0-9-]*$", field_types: ["text"], rule_triggers: ["validate"], condition_operators: ["eq"], action_types: ["reject-with-message"], value_sources: ["ui"], value_allowed_statuses: ["active"], field_delete_statuses: ["draft"], form_delete_statuses: ["draft"], field_transitions: {}, form_transitions: {}, rule_transitions: {} },
    defaults: { field_required: false, field_searchable: false, field_status: "draft", form_status: "draft", layout_schema_version: 1, layout_status: "candidate", form_surface: "default", form_layout: { schema_version: 1, sections: [] }, rule_priority: 100, rule_stop_on_match: false, rule_status: "draft", rule_language_version: 1, rule_version_status: "candidate", contract_version: "1.0" },
    list_preferences: { page_size: 25, field_ordering: "key", form_ordering: "key", rule_ordering: "priority", execution_ordering: "-executed_at" },
    navigation: { fields_order: 70, field_values_order: 71, forms_order: 72, rules_order: 73, executions_order: 74, configuration_order: 75 },
    rollout: { enabled: true, roles: [], cohorts: [] },
    rbac: { action_access: {}, sod_actions: [] },
  },
  updated_by: "00000000-0000-4000-8000-000000000012", created_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:00Z",
} as const satisfies RuntimeConfiguration;
function renderPage(page: React.ReactElement, initial = "/") { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initial]}>{page}</MemoryRouter></QueryClientProvider>); }

describe("customization page families", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(service.getConfiguration).mockResolvedValue(runtimeConfiguration); vi.mocked(service.listFields).mockResolvedValue({ data: [], meta }); vi.mocked(service.listForms).mockResolvedValue({ data: [], meta }); vi.mocked(service.listRules).mockResolvedValue({ data: [], meta }); vi.mocked(service.listExecutions).mockResolvedValue({ data: [], meta }); });

  it.each([
    ["fields", <FieldDefinitionListPage />, "No fields yet"],
    ["forms", <FormListPage />, "No forms yet"],
    ["rules", <RuleListPage />, "No rules yet"],
    ["executions", <RuleExecutionListPage />, "No executions yet"],
  ])("renders distinct empty state for %s", async (_name, page, heading) => { renderPage(page); expect(await screen.findByText(heading)).toBeInTheDocument(); });

  it("renders a distinct zero-results state from URL-backed server filters", async () => { renderPage(<FieldDefinitionListPage />, "/?search=missing"); expect(await screen.findByText("No fields match")).toBeInTheDocument(); expect(service.listFields).toHaveBeenCalledWith(expect.objectContaining({ search: "missing" })); });

  it("shows safe denied and capability-unavailable states with correlation IDs", () => { const { rerender } = render(<GovernedError error={new ApiError("hidden", 403, undefined, "permission_denied", "corr-denied")}/>); expect(screen.getByText("Access denied")).toBeInTheDocument(); expect(screen.getByText(/corr-denied/u)).toBeInTheDocument(); rerender(<GovernedError error={new ApiError("offline", 503, undefined, "capability_unavailable", "corr-down")}/>); expect(screen.getByText("Capability unavailable")).toBeInTheDocument(); expect(screen.getByText(/corr-down/u)).toBeInTheDocument(); });
});
