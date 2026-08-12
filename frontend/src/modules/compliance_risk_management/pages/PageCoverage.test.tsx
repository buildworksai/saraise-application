/* eslint-disable max-lines-per-function -- page fixtures intentionally exercise multiple compliance risk UI branches. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ComplianceCalendarEntry,
  ComplianceRequirement,
  Control,
  ControlTest,
  ControlTestResultInput,
  Paginated,
  RemediationAction,
  RiskAssessment,
  RiskConfiguration,
  RiskConfigurationVersion,
  RiskDashboardSummary,
} from "../contracts";
import {
  complianceRiskService as service,
  ComplianceRiskApiError,
} from "../services/compliance-risk-service";
import {
  CalendarEntryDetailPage,
  ComplianceCalendarPage,
  CreateCalendarEntryPage,
  CreateRemediationPage,
  EditCalendarEntryPage,
  RemediationListPage,
  RemediationDetailPage,
} from "./CalendarRemediationPages";
import {
  ControlDetailPage,
  EditControlPage,
  ControlListPage,
  ControlTestDetailPage,
  ControlTestListPage,
  CreateControlPage,
  CreateControlTestPage,
  ExecuteControlTestPage,
} from "./ControlPages";
import {
  ComplianceRiskDashboardPage,
  RiskConfigurationImportExportPage,
  RiskConfigurationHistoryPage,
  RiskConfigurationPage,
  RiskConfigurationVersionDetailPage,
} from "./DashboardConfigurationPages";
import {
  CreateRequirementPage,
  EditRequirementPage,
  RequirementDetailPage,
  RequirementListPage,
} from "./RequirementPages";
import { CreateRiskAssessmentPage, RiskAssessmentDetailPage } from "./RiskPages";

const storage = (() => {
  let values = new Map<string, string>();
  return {
    clear: () => {
      values = new Map();
    },
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => {
      values.delete(key);
    },
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
})();

Object.defineProperty(globalThis, "localStorage", {
  value: storage,
  configurable: true,
});

const { authState } = vi.hoisted(() => ({
  authState: {
    user: {
      id: "user-1",
      email: "officer@example.com",
      username: "officer",
      is_staff: false,
      is_superuser: false,
      tenant_id: "tenant-a",
      platform_role: null,
      tenant_role: "tenant_admin",
    },
    isAuthenticated: true,
    isLoading: false,
  },
}));

vi.mock("@/stores/auth-store", () => {
  const useAuthStore = (selector: (state: typeof authState) => unknown) => selector(authState);
  useAuthStore.getState = () => authState;
  return { useAuthStore };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const meta = {
  page: 1,
  page_size: 25,
  count: 0,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const paginated = <T,>(items: T[], overrides: Partial<typeof meta> = {}): Paginated<T> => ({
  items,
  pagination: {
    ...meta,
    ...overrides,
    count: overrides.count ?? items.length,
    total_pages: overrides.total_pages ?? (items.length ? 1 : 0),
  },
  correlation_id: "corr-page",
});
const audit = {
  id: "entity-1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
  created_by_id: "actor-1",
  updated_by_id: null,
};
const transition = {
  command: "create",
  from: "draft",
  to: "active",
  actor_id: "actor-1",
  correlation_id: "corr-transition",
  rationale: "Initial publication",
  occurred_at: "2026-07-01T00:00:00Z",
};
const risk: RiskAssessment = {
  ...audit,
  id: "risk-1",
  risk_code: "RISK-001",
  name: "Supplier compliance",
  category: "compliance",
  description: "Assess supplier controls.",
  likelihood: 4,
  impact: 5,
  inherent_score: "20.00",
  residual_likelihood: null,
  residual_impact: null,
  residual_score: null,
  risk_level: "critical",
  qualitative_rationale: "External dependency concentration.",
  mitigation_strategy: "",
  owner_id: "owner-1",
  review_date: "2026-08-15",
  status: "assessed",
  accepted_until: null,
  closed_at: null,
  transition_history: [transition],
};
const control: Control = {
  ...audit,
  id: "control-1",
  risk_id: "risk-1",
  control_code: "CTRL-001",
  name: "Vendor attestation",
  description: "Collect current attestation.",
  test_procedure: "Verify document checksum.",
  frequency: "custom",
  frequency_days: 45,
  owner_id: "owner-1",
  default_tester_id: null,
  next_test_due: "2026-08-10",
  status: "draft",
  transition_history: [transition],
};
const controlTest: ControlTest = {
  ...audit,
  id: "test-1",
  control_id: "control-1",
  scheduled_for: "2026-08-10",
  started_at: null,
  completed_at: null,
  tester_id: "tester-1",
  result: "not_tested",
  findings: "",
  evidence: [],
  status: "in_progress",
  cancellation_reason: "",
  transition_history: [transition],
};
const requirement: ComplianceRequirement = {
  ...audit,
  id: "requirement-1",
  regulation_code: "GDPR",
  requirement_code: "ART-30",
  regulation_name: "General Data Protection Regulation",
  title: "Processing records",
  description: "Maintain processing activity records.",
  applicability: "conditional",
  applicability_rationale: "Tenant processes personal data.",
  status: "not_assessed",
  owner_id: "owner-1",
  effective_date: "2026-01-01",
  due_date: "2026-09-01",
  last_assessed_at: null,
  source_url: "https://example.invalid/gdpr",
  cross_references: ["risk-1"],
  transition_history: [transition],
};
const calendarEntry: ComplianceCalendarEntry = {
  ...audit,
  id: "calendar-1",
  requirement_id: "requirement-1",
  title: "GDPR submission deadline",
  event_type: "deadline",
  scheduled_date: "2026-08-20",
  reminder_days: [30, 7],
  assigned_to_id: "owner-1",
  status: "overdue",
  completed_date: null,
  completion_notes: "",
  transition_history: [transition],
};
const remediation: RemediationAction = {
  ...audit,
  id: "remediation-1",
  risk_id: "risk-1",
  control_test_id: "test-1",
  action_code: "REM-001",
  description: "Refresh supplier evidence.",
  assigned_to_id: "owner-2",
  due_date: "2026-08-25",
  priority: "critical",
  status: "planned",
  completion_date: null,
  completion_evidence: [],
  cancellation_reason: "",
  transition_history: [transition],
};
const configurationDocument = {
  likelihood_scale_max: 5,
  impact_scale_max: 5,
  level_thresholds: { negligible: 2, low: 5, medium: 10, high: 15, critical: 25 },
  default_review_days: 90,
  default_reminder_days: [30, 7],
  acceptance_max_days: 60,
  overdue_job_enabled: true,
  feature_flags: {
    risk_heatmap: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
    recurring_control_tests: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
    compliance_reminders: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
  },
};
const configuration: RiskConfiguration = {
  ...audit,
  ...configurationDocument,
  id: "configuration-1",
  environment: "development",
  version: 3,
  published_at: "2026-07-15T00:00:00Z",
  published_by_id: "admin-1",
};
const configurationVersion: RiskConfigurationVersion = {
  id: "version-2",
  environment: "development",
  version: 2,
  configuration: configurationDocument,
  change_summary: "Tighten critical threshold",
  actor_id: "admin-1",
  correlation_id: "corr-version",
  created_at: "2026-07-10T00:00:00Z",
  restored_from_version: null,
};

function renderPage(ui: React.ReactElement, initialEntry = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function controlAfterLabel<T extends HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
  label: string
): T {
  const field = screen
    .getAllByText(label)
    .map((labelElement) => labelElement.parentElement?.querySelector("input, textarea, select"))
    .find(Boolean);
  if (!field) throw new Error(`No field found for ${label}`);
  return field as T;
}

function selectWithOption(value: string): HTMLSelectElement {
  const select = screen
    .getAllByRole("combobox")
    .find((element): element is HTMLSelectElement =>
      Array.from((element as HTMLSelectElement).options, (option) => option.value).includes(value)
    );
  if (!select) throw new Error(`Select option ${value} was not rendered.`);
  return select;
}

describe("compliance risk page coverage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000000");
    authState.user.tenant_role = "tenant_admin";
  });

  it("renders dashboard heatmap, empty companion panels, and navigable KPI/filter behavior", async () => {
    const user = userEvent.setup();
    const dashboard: RiskDashboardSummary = {
      total_risks: 4,
      critical_risks: 1,
      overdue_reviews: 0,
      overdue_controls: 0,
      overdue_remediations: 0,
      upcoming_events: 0,
      risks_by_level: { negligible: 0, low: 1, medium: 1, high: 1, critical: 1 },
      risks_by_status: {
        identified: 1,
        assessed: 1,
        mitigating: 1,
        accepted: 1,
        closed: 0,
      },
      overdue_work: [],
      upcoming_compliance_events: [],
    };
    vi.spyOn(service, "getDashboard").mockResolvedValue(dashboard);
    vi.spyOn(service, "getHeatmap").mockResolvedValue([
      { likelihood: 4, impact: 5, count: 2, level: "critical", risk_ids: ["risk-1"] },
    ]);

    renderPage(<ComplianceRiskDashboardPage />);

    expect(await screen.findByText("Compliance risk dashboard")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Category filter"), "compliance");
    await waitFor(() =>
      expect(service.getDashboard).toHaveBeenLastCalledWith({ category: "compliance" })
    );
    expect(
      screen.getByRole("gridcell", { name: /Likelihood 4, impact 5, 2 risks/i })
    ).toBeEnabled();
    expect(screen.getByText("No overdue work in this view.")).toBeVisible();
    expect(screen.getByText("No upcoming events in this view.")).toBeVisible();
  });

  it("previews and confirms versioned risk configuration publication", async () => {
    const user = userEvent.setup();
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(service, "previewConfiguration").mockResolvedValue({
      valid: true,
      validation_errors: [],
      score_band_changes: [{ score: 16, from: "high", to: "critical" }],
      affected_record_counts: { risks: 2, controls: 1, calendar_entries: 1 },
    });
    vi.spyOn(service, "publishConfiguration").mockResolvedValue(configuration);

    renderPage(<RiskConfigurationPage />);

    expect(await screen.findByText("Risk configuration")).toBeVisible();
    const reviewDays = controlAfterLabel<HTMLInputElement>("Default review days");
    await user.clear(reviewDays);
    await user.type(reviewDays, "120");
    await user.click(screen.getByRole("button", { name: "Preview impact" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Candidate is valid");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Version summary"),
      "Align review cadence"
    );
    await user.click(screen.getByRole("button", { name: "Publish configuration" }));
    await user.click(await screen.findByRole("button", { name: "Publish version" }));

    await waitFor(() => expect(service.publishConfiguration).toHaveBeenCalled());
    const payload = vi.mocked(service.publishConfiguration).mock.calls[0]?.[0];
    expect(payload).toMatchObject({
      environment: "development",
      expected_version: 3,
      change_summary: "Align review cadence",
    });
    expect(payload?.candidate.default_review_days).toBe(120);
  });

  it("hides configuration rollback when inspecting the active version", async () => {
    vi.spyOn(service, "getConfigurationVersion").mockResolvedValue({
      ...configurationVersion,
      version: 3,
    });
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);

    renderPage(
      <Routes>
        <Route
          path="/configuration/history/:version"
          element={<RiskConfigurationVersionDetailPage />}
        />
      </Routes>,
      "/configuration/history/3?environment=development"
    );

    expect(await screen.findByText("Configuration version 3")).toBeVisible();
    expect(screen.getByText("Current active version")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Rollback to this version/i })
    ).not.toBeInTheDocument();
  });

  it("renders risk detail trace branches and opens acceptance transition preview", async () => {
    const user = userEvent.setup();
    vi.spyOn(service, "getRisk").mockResolvedValue(risk);
    vi.spyOn(service, "listRiskControls").mockResolvedValue(paginated([control]));
    vi.spyOn(service, "listRiskRemediations").mockResolvedValue(paginated([remediation]));

    renderPage(
      <Routes>
        <Route path="/risks/:id" element={<RiskAssessmentDetailPage />} />
      </Routes>,
      "/risks/risk-1"
    );

    expect(await screen.findByText("RISK-001 · Supplier compliance")).toBeVisible();
    expect(screen.getByText("No mitigation has been documented.")).toBeVisible();
    expect(screen.getByText("CTRL-001 · Vendor attestation")).toBeVisible();
    expect(screen.getByText("REM-001 · Refresh supplier evidence.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Lifecycle action" }));
    await user.selectOptions(screen.getByLabelText("Command"), "accept");
    expect(controlAfterLabel<HTMLInputElement>("Accepted until")).toBeRequired();
    expect(screen.getByText("Preview lifecycle action")).toBeVisible();
    expect(screen.getAllByText("Accepted").length).toBeGreaterThan(0);
  });

  it("renders control list filters and custom-frequency detail with empty scheduled-test action", async () => {
    const user = userEvent.setup();
    vi.spyOn(service, "listControls").mockResolvedValue(paginated([control]));
    vi.spyOn(service, "getControl").mockResolvedValue(control);
    vi.spyOn(service, "listControlTests").mockResolvedValue(paginated([]));

    renderPage(<ControlListPage />);

    expect(await screen.findByText("CTRL-001 · Vendor attestation")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Frequency filter"), "custom");
    await waitFor(() =>
      expect(service.listControls).toHaveBeenLastCalledWith(
        expect.objectContaining({ frequency: "custom" })
      )
    );

    cleanup();
    renderPage(
      <Routes>
        <Route path="/controls/:id" element={<ControlDetailPage />} />
      </Routes>,
      "/controls/control-1"
    );

    expect(await screen.findByText("CTRL-001 · Vendor attestation")).toBeVisible();
    expect(screen.getByText("Every 45 days")).toBeVisible();
    expect(screen.getByText("No tests scheduled")).toBeVisible();
    expect(screen.getByRole("button", { name: "Schedule test" })).toBeEnabled();
  });

  it("restores execute-test draft, requires remediation for failed results, and submits payload", async () => {
    const user = userEvent.setup();
    const record = vi.spyOn(service, "recordTestResult").mockResolvedValue({
      ...controlTest,
      status: "completed",
      result: "failed",
    });
    vi.spyOn(service, "getTest").mockResolvedValue(controlTest);
    localStorage.setItem(
      "compliance-risk-test-draft:tenant-a:test-1",
      JSON.stringify({
        result: "failed",
        findings: "Old finding",
        evidence: [
          { document_id: "doc-1", version_id: "ver-1", label: "Attestation", checksum: "sha" },
        ],
      })
    );

    renderPage(
      <Routes>
        <Route path="/control-tests/:id/execute" element={<ExecuteControlTestPage />} />
        <Route
          path="/compliance-risk-management/control-tests/:id"
          element={<div>Control test detail destination</div>}
        />
      </Routes>,
      "/control-tests/test-1/execute"
    );

    expect(await screen.findByText("Execute control test")).toBeVisible();
    expect(controlAfterLabel<HTMLTextAreaElement>("Findings")).toHaveValue("Old finding");
    expect(screen.getByText("Required remediation")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Action code"), "rem-002");
    await user.type(controlAfterLabel<HTMLInputElement>("Assignee UUID"), "owner-2");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Action description"),
      "Replace expired control evidence"
    );
    await user.type(controlAfterLabel<HTMLInputElement>("Due date"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Record terminal result" }));

    await waitFor(() => expect(record).toHaveBeenCalled());
    const resultPayload = record.mock.calls[0]?.[1] as
      | (ControlTestResultInput & { transition_key: string })
      | undefined;
    expect(record.mock.calls[0]?.[0]).toBe("test-1");
    expect(resultPayload).toMatchObject({ result: "failed", findings: "Old finding" });
    expect(resultPayload?.remediation?.action_code).toBe("REM-002");
  });

  it("groups requirement list and renders conditional detail with assessment evidence fields", async () => {
    const user = userEvent.setup();
    vi.spyOn(service, "listRequirements").mockResolvedValue(paginated([requirement]));
    vi.spyOn(service, "getRequirement").mockResolvedValue(requirement);

    renderPage(<RequirementListPage />);

    expect(await screen.findByText("GDPR · General Data Protection Regulation")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Applicability filter"), "conditional");
    await waitFor(() =>
      expect(service.listRequirements).toHaveBeenLastCalledWith(
        expect.objectContaining({ applicability: "conditional" })
      )
    );

    cleanup();
    renderPage(
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetailPage />} />
      </Routes>,
      "/requirements/requirement-1"
    );

    expect(await screen.findByText("GDPR/ART-30")).toBeVisible();
    expect(screen.getByText("Tenant processes personal data.")).toBeVisible();
    expect(screen.getByText("risk-1")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Record assessment" }));
    await user.click(screen.getByRole("button", { name: "Add evidence reference" }));
    expect(screen.getByLabelText("Evidence 1 document UUID")).toBeRequired();
  });

  it("switches calendar agenda/grid views and handles terminal entry/remediation actions", async () => {
    const user = userEvent.setup();
    vi.spyOn(service, "listCalendarEntries").mockResolvedValue(paginated([calendarEntry]));
    vi.spyOn(service, "getCalendarEntry").mockResolvedValue(calendarEntry);
    vi.spyOn(service, "getRemediation").mockResolvedValue(remediation);

    renderPage(<ComplianceCalendarPage />, "/calendar?date_from=2026-08-20&date_to=2026-08-22");

    expect(await screen.findByRole("grid", { name: "Compliance event calendar" })).toBeVisible();
    expect(screen.getByText("Overdue · GDPR submission deadline")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Agenda" }));
    expect(screen.getByRole("button", { name: /GDPR submission deadline/i })).toBeVisible();

    cleanup();
    renderPage(
      <Routes>
        <Route path="/calendar/:id" element={<CalendarEntryDetailPage />} />
      </Routes>,
      "/calendar/calendar-1"
    );

    expect(await screen.findByText("GDPR submission deadline")).toBeVisible();
    expect(screen.getByRole("button", { name: "Complete" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Cancel event" })).toBeEnabled();

    cleanup();
    renderPage(
      <Routes>
        <Route path="/remediations/:id" element={<RemediationDetailPage />} />
      </Routes>,
      "/remediations/remediation-1"
    );

    expect(await screen.findByRole("heading", { name: /REM-001 · Remediation/i })).toBeVisible();
    expect(screen.getByText("Refresh supplier evidence.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
  });

  it("shows non-retryable governed access errors without assuming data", async () => {
    vi.spyOn(service, "listControls").mockRejectedValue(
      new ComplianceRiskApiError("Forbidden", 403, "FORBIDDEN", "corr-denied")
    );

    renderPage(<ControlListPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByText("Correlation ID: corr-denied")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("creates a risk assessment with residual scoring preview and normalized code", async () => {
    const user = userEvent.setup();
    const previewScore = vi.spyOn(service, "previewScore").mockResolvedValue({
      inherent_score: "20.00",
      residual_score: "6.00",
      risk_level: "critical",
      likelihood_scale_max: 5,
      impact_scale_max: 5,
      explanation: {
        formula: "likelihood * impact",
        likelihood: 4,
        impact: 5,
        threshold_version: 3,
        matched_upper_bound: 25,
      },
    });
    const createRisk = vi.spyOn(service, "createRisk").mockResolvedValue(risk);

    renderPage(<CreateRiskAssessmentPage />);

    expect(await screen.findByText("Create risk assessment")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Risk code"), "risk-009");
    await user.type(controlAfterLabel<HTMLInputElement>("Risk name"), "Hosted vendor continuity");
    await user.selectOptions(screen.getByLabelText("Category"), "operational");
    await user.type(controlAfterLabel<HTMLInputElement>("Owner principal UUID"), "owner-9");
    await user.type(controlAfterLabel<HTMLTextAreaElement>("Description"), "Vendor region outage");
    const likelihood = screen
      .getAllByLabelText(/^Likelihood/)
      .find((element): element is HTMLInputElement => element instanceof HTMLInputElement);
    const impact = screen
      .getAllByLabelText(/^Impact/)
      .find((element): element is HTMLInputElement => element instanceof HTMLInputElement);
    if (!likelihood || !impact) throw new Error("Risk score fields were not rendered.");
    await user.clear(likelihood);
    await user.type(likelihood, "4");
    await user.clear(impact);
    await user.type(impact, "5");
    await user.click(screen.getByLabelText("Capture residual assessment"));
    await user.clear(controlAfterLabel<HTMLInputElement>("Residual likelihood"));
    await user.type(controlAfterLabel<HTMLInputElement>("Residual likelihood"), "2");
    await user.clear(controlAfterLabel<HTMLInputElement>("Residual impact"));
    await user.type(controlAfterLabel<HTMLInputElement>("Residual impact"), "3");
    await user.type(controlAfterLabel<HTMLInputElement>("Review date"), "2026-10-01");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Qualitative rationale"),
      "Controls reduce concentration exposure"
    );
    await user.click(screen.getByRole("button", { name: "Save assessment" }));

    await waitFor(() => expect(createRisk).toHaveBeenCalled());
    expect(previewScore).toHaveBeenCalledWith(
      expect.objectContaining({
        likelihood: 4,
        impact: 5,
        residual_likelihood: 2,
        residual_impact: 3,
      })
    );
    expect(createRisk.mock.calls[0]?.[0]).toMatchObject({
      risk_code: "RISK-009",
      category: "operational",
      residual_likelihood: 2,
      residual_impact: 3,
      review_date: "2026-10-01",
    });
    expect(createRisk.mock.calls[0]?.[1]).toBe("00000000-0000-4000-8000-000000000000");
  });

  it("creates controls and schedules tests with normalized custom cadence payloads", async () => {
    const user = userEvent.setup();
    const createControl = vi.spyOn(service, "createControl").mockResolvedValue(control);
    const scheduleControlTest = vi
      .spyOn(service, "scheduleControlTest")
      .mockResolvedValue(controlTest);

    renderPage(<CreateControlPage />, "/controls/new?risk_id=risk-9");

    expect(await screen.findByText("Create control")).toBeVisible();
    await user.clear(controlAfterLabel<HTMLInputElement>("Risk UUID"));
    await user.type(controlAfterLabel<HTMLInputElement>("Risk UUID"), "risk-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Control code"), "ctrl-009");
    await user.type(controlAfterLabel<HTMLInputElement>("Control name"), "Provider exit test");
    await user.type(controlAfterLabel<HTMLInputElement>("Owner principal UUID"), "owner-9");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Description"),
      "Validate exit evidence"
    );
    await user.type(controlAfterLabel<HTMLTextAreaElement>("Test procedure"), "Execute tabletop");
    await user.selectOptions(screen.getByLabelText("Frequency"), "custom");
    await user.type(controlAfterLabel<HTMLInputElement>("Frequency days"), "45");
    await user.type(controlAfterLabel<HTMLInputElement>("Default tester UUID"), "tester-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Next test due"), "2026-09-15");
    await user.click(screen.getByRole("button", { name: "Save control" }));

    await waitFor(() => expect(createControl).toHaveBeenCalled());
    expect(createControl.mock.calls[0]?.[0]).toMatchObject({
      control_code: "CTRL-009",
      risk_id: "risk-9",
      frequency: "custom",
      frequency_days: 45,
      default_tester_id: "tester-9",
    });

    cleanup();
    renderPage(<CreateControlTestPage />, "/tests/new?control_id=control-9");

    expect(await screen.findByText("Schedule control test")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Control UUID"), "control-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Tester principal UUID"), "tester-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Scheduled for"), "2026-09-20");
    await user.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(scheduleControlTest).toHaveBeenCalled());
    expect(scheduleControlTest).toHaveBeenCalledWith(
      "control-9",
      { scheduled_for: "2026-09-20", tester_id: "tester-9" },
      "00000000-0000-4000-8000-000000000000"
    );
  });

  it("creates calendar and remediation records with parsed reminders and normalized action codes", async () => {
    const user = userEvent.setup();
    const createCalendarEntry = vi
      .spyOn(service, "createCalendarEntry")
      .mockResolvedValue(calendarEntry);
    const createRemediation = vi.spyOn(service, "createRemediation").mockResolvedValue(remediation);

    renderPage(<CreateCalendarEntryPage />);

    expect(await screen.findByText("Schedule compliance event")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Requirement UUID"), "requirement-9");
    await user.type(
      controlAfterLabel<HTMLInputElement>("Event title"),
      "Quarterly regulatory filing"
    );
    await user.selectOptions(screen.getByLabelText("Event type"), "submission");
    await user.type(controlAfterLabel<HTMLInputElement>("Scheduled date"), "2026-10-15");
    await user.type(controlAfterLabel<HTMLInputElement>("Assigned principal UUID"), "owner-9");
    await user.clear(controlAfterLabel<HTMLInputElement>("Reminder days"));
    await user.type(controlAfterLabel<HTMLInputElement>("Reminder days"), "bad, 14, 0, 14, 7");
    expect(screen.getByText(/Oct 1, 2026 \(14 days before\)/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save event" }));

    await waitFor(() => expect(createCalendarEntry).toHaveBeenCalled());
    expect(createCalendarEntry.mock.calls[0]?.[0]).toMatchObject({
      requirement_id: "requirement-9",
      event_type: "submission",
      reminder_days: [14, 7, 0],
    });

    cleanup();
    renderPage(
      <CreateRemediationPage />,
      "/remediations/new?risk_id=risk-9&control_test_id=test-9"
    );

    expect(await screen.findByText("Create remediation")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Risk UUID"), "risk-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Source control-test UUID"), "test-9");
    await user.type(controlAfterLabel<HTMLInputElement>("Action code"), "rem-009");
    await user.type(controlAfterLabel<HTMLInputElement>("Assigned principal UUID"), "owner-9");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Description"),
      "Collect missing artifacts"
    );
    await user.type(controlAfterLabel<HTMLInputElement>("Due date"), "2026-10-20");
    await user.selectOptions(screen.getByLabelText("Priority"), "critical");
    await user.click(screen.getByRole("button", { name: "Save action" }));

    await waitFor(() => expect(createRemediation).toHaveBeenCalled());
    expect(createRemediation.mock.calls[0]?.[0]).toMatchObject({
      risk_id: "risk-9",
      control_test_id: "test-9",
      action_code: "REM-009",
      priority: "critical",
    });
  });

  it("submits calendar terminal lifecycle commands with audited context", async () => {
    const user = userEvent.setup();
    const transitionCalendarEntry = vi
      .spyOn(service, "transitionCalendarEntry")
      .mockResolvedValue({ ...calendarEntry, status: "completed" });
    vi.spyOn(service, "getCalendarEntry").mockResolvedValue(calendarEntry);

    renderPage(
      <Routes>
        <Route path="/calendar/:id" element={<CalendarEntryDetailPage />} />
      </Routes>,
      "/calendar/calendar-1"
    );

    expect(await screen.findByText("GDPR submission deadline")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Complete" }));
    await user.clear(controlAfterLabel<HTMLInputElement>("Completion date"));
    await user.type(controlAfterLabel<HTMLInputElement>("Completion date"), "2026-08-21");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Completion notes"),
      "Submission receipt archived"
    );
    await user.click(screen.getByRole("button", { name: /^Complete$/ }));

    await waitFor(() => expect(transitionCalendarEntry).toHaveBeenCalled());
    expect(transitionCalendarEntry).toHaveBeenCalledWith("calendar-1", {
      command: "complete",
      transition_key: "00000000-0000-4000-8000-000000000000",
      context: {
        completion_date: "2026-08-21",
        completion_notes: "Submission receipt archived",
      },
    });
  });

  it("transitions remediation completion with required evidence payload", async () => {
    const user = userEvent.setup();
    const transitionRemediation = vi
      .spyOn(service, "transitionRemediation")
      .mockResolvedValue({ ...remediation, status: "completed" });
    vi.spyOn(service, "getRemediation").mockResolvedValue({
      ...remediation,
      status: "in_progress",
    });

    renderPage(
      <Routes>
        <Route path="/remediations/:id" element={<RemediationDetailPage />} />
      </Routes>,
      "/remediations/remediation-1"
    );

    expect(await screen.findByRole("heading", { name: /REM-001 · Remediation/i })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Complete" }));
    expect(screen.getByRole("button", { name: /^Complete$/ })).toBeDisabled();
    await user.clear(controlAfterLabel<HTMLInputElement>("Completion date"));
    await user.type(controlAfterLabel<HTMLInputElement>("Completion date"), "2026-08-26");
    await user.click(screen.getByRole("button", { name: "Add completion evidence" }));
    await user.type(controlAfterLabel<HTMLInputElement>("Document Id"), "doc-2");
    await user.type(controlAfterLabel<HTMLInputElement>("Version Id"), "ver-2");
    await user.type(controlAfterLabel<HTMLInputElement>("Label"), "Closure packet");
    await user.type(controlAfterLabel<HTMLInputElement>("Checksum"), "sha256-close");
    await user.click(screen.getByRole("button", { name: /^Complete$/ }));

    await waitFor(() => expect(transitionRemediation).toHaveBeenCalled());
    expect(transitionRemediation).toHaveBeenCalledWith("remediation-1", {
      command: "complete",
      transition_key: "00000000-0000-4000-8000-000000000000",
      context: {
        completion_date: "2026-08-26",
        completion_evidence: [
          {
            document_id: "doc-2",
            version_id: "ver-2",
            label: "Closure packet",
            checksum: "sha256-close",
          },
        ],
      },
    });
  });

  it("submits control and scheduled-test lifecycle commands from detail pages", async () => {
    const user = userEvent.setup();
    const transitionControl = vi.spyOn(service, "transitionControl").mockResolvedValue({
      ...control,
      status: "active",
    });
    const startTest = vi.spyOn(service, "startTest").mockResolvedValue({
      ...controlTest,
      status: "in_progress",
    });
    const cancelTest = vi.spyOn(service, "cancelTest").mockResolvedValue({
      ...controlTest,
      status: "cancelled",
    });
    vi.spyOn(service, "getControl").mockResolvedValue(control);
    vi.spyOn(service, "listControlTests").mockResolvedValue(paginated([controlTest]));
    vi.spyOn(service, "getTest").mockResolvedValue({
      ...controlTest,
      status: "scheduled",
    });

    renderPage(
      <Routes>
        <Route path="/controls/:id" element={<ControlDetailPage />} />
      </Routes>,
      "/controls/control-1"
    );

    expect(await screen.findByText("CTRL-001 · Vendor attestation")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(transitionControl).toHaveBeenCalled());
    expect(transitionControl).toHaveBeenCalledWith("control-1", {
      command: "activate",
      transition_key: "00000000-0000-4000-8000-000000000000",
    });

    cleanup();
    renderPage(
      <Routes>
        <Route path="/control-tests/:id" element={<ControlTestDetailPage />} />
        <Route
          path="/compliance-risk-management/control-tests/:id/execute"
          element={<div>Execution destination</div>}
        />
      </Routes>,
      "/control-tests/test-1"
    );

    expect(await screen.findByText(/Control test ·/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(await screen.findByRole("button", { name: "Cancel test" }));
    await waitFor(() => expect(cancelTest).toHaveBeenCalled());
    expect(cancelTest).toHaveBeenCalledWith("test-1", {
      transition_key: "00000000-0000-4000-8000-000000000000",
      reason: "Cancelled by tester through the governed UI.",
    });

    cleanup();
    renderPage(
      <Routes>
        <Route path="/control-tests/:id" element={<ControlTestDetailPage />} />
        <Route
          path="/compliance-risk-management/control-tests/:id/execute"
          element={<div>Execution destination</div>}
        />
      </Routes>,
      "/control-tests/test-1"
    );

    expect(await screen.findByText(/Control test ·/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start test" }));
    await waitFor(() =>
      expect(startTest).toHaveBeenCalledWith("test-1", {
        transition_key: "00000000-0000-4000-8000-000000000000",
      })
    );
  });

  it("records requirement assessment with evidence and deterministic transition key", async () => {
    const user = userEvent.setup();
    const assessRequirement = vi
      .spyOn(service, "assessRequirement")
      .mockResolvedValue({ ...requirement, status: "non_compliant" });
    vi.spyOn(service, "getRequirement").mockResolvedValue(requirement);

    renderPage(
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetailPage />} />
      </Routes>,
      "/requirements/requirement-1"
    );

    expect(await screen.findByText("GDPR/ART-30")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Record assessment" }));
    await user.selectOptions(screen.getByLabelText("Outcome"), "assess_non_compliant");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Rationale"),
      "Processor inventory is incomplete"
    );
    await user.click(screen.getByRole("button", { name: "Add evidence reference" }));
    await user.type(screen.getByLabelText("Evidence 1 document UUID"), "doc-3");
    await user.type(screen.getByLabelText("Evidence 1 version UUID"), "ver-3");
    await user.type(screen.getByLabelText("Evidence 1 label"), "Gap report");
    await user.type(screen.getByLabelText("Evidence 1 checksum"), "sha256-gap");
    await user.click(screen.getByRole("button", { name: "Record assessment" }));

    await waitFor(() => expect(assessRequirement).toHaveBeenCalled());
    expect(assessRequirement).toHaveBeenCalledWith("requirement-1", {
      command: "assess_non_compliant",
      rationale: "Processor inventory is incomplete",
      evidence: [
        {
          document_id: "doc-3",
          version_id: "ver-3",
          label: "Gap report",
          checksum: "sha256-gap",
        },
      ],
      transition_key: "00000000-0000-4000-8000-000000000000",
    });
  });

  it("publishes configuration rollback and exercises import/export dry-run gate", async () => {
    const user = userEvent.setup();
    const rollbackConfiguration = vi
      .spyOn(service, "rollbackConfiguration")
      .mockResolvedValue({ ...configuration, version: 4 });
    const exportConfiguration = vi.spyOn(service, "exportConfiguration").mockResolvedValue({
      schema: "saraise.compliance-risk.configuration",
      schema_version: 1,
      environment: "development",
      version: 3,
      configuration: configurationDocument,
    });
    const importConfiguration = vi
      .spyOn(service, "importConfiguration")
      .mockResolvedValueOnce({
        valid: true,
        validation_errors: [],
        score_band_changes: [],
        affected_record_counts: { risks: 0, controls: 0, calendar_entries: 0 },
      })
      .mockResolvedValueOnce(configuration);
    const click = vi.fn();
    const createObjectURL = vi.fn(() => "blob:policy");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
    });
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      const element = originalCreateElement(tagName);
      if (tagName === "a") Object.assign(element, { click });
      return element;
    });
    vi.spyOn(service, "getConfigurationVersion").mockResolvedValue(configurationVersion);
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);

    renderPage(
      <Routes>
        <Route
          path="/configuration/history/:version"
          element={<RiskConfigurationVersionDetailPage />}
        />
      </Routes>,
      "/configuration/history/2?environment=development"
    );

    expect(await screen.findByText("Configuration version 2")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Rollback to this version" }));
    await user.click(await screen.findByRole("button", { name: "Publish rollback" }));
    await waitFor(() => expect(rollbackConfiguration).toHaveBeenCalled());
    expect(rollbackConfiguration).toHaveBeenCalledWith({
      environment: "development",
      version: 2,
      expected_version: 3,
      change_summary: "Restore development configuration from version 2",
    });

    cleanup();
    renderPage(<RiskConfigurationImportExportPage />);

    expect(await screen.findByText("Configuration import / export")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(exportConfiguration).toHaveBeenCalledWith("development"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:policy");

    const file = new File(
      [
        JSON.stringify({
          schema: "saraise.compliance-risk.configuration",
          schema_version: 1,
          environment: "development",
          version: 3,
          configuration: configurationDocument,
        }),
      ],
      "configuration.json",
      { type: "application/json" }
    );
    await user.upload(screen.getByLabelText("Configuration JSON"), file);
    expect(
      await screen.findByText(/Loaded schema saraise\.compliance-risk\.configuration/)
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Run mandatory dry-run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Candidate is valid");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Publication summary"),
      "Promote reviewed policy"
    );
    await user.click(screen.getByRole("button", { name: "Publish imported policy" }));

    await waitFor(() => expect(importConfiguration).toHaveBeenCalledTimes(2));
    expect(importConfiguration.mock.calls[0]?.[0]).toMatchObject({
      environment: "development",
      dry_run: true,
      expected_version: undefined,
    });
    expect(importConfiguration.mock.calls[1]?.[0]).toMatchObject({
      environment: "development",
      dry_run: false,
      expected_version: 3,
      change_summary: "Promote reviewed policy",
    });
  });

  it("rejects malformed compliance-risk configuration JSON before dry-run", async () => {
    const user = userEvent.setup();
    const importConfiguration = vi.spyOn(service, "importConfiguration");

    renderPage(<RiskConfigurationImportExportPage />);

    expect(await screen.findByText("Configuration import / export")).toBeVisible();
    await user.upload(
      screen.getByLabelText("Configuration JSON"),
      new File(["{"], "broken-configuration.json", { type: "application/json" })
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("The selected file is not valid JSON.")
    );
    expect(screen.getByRole("button", { name: "Run mandatory dry-run" })).toBeDisabled();
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("normalizes requirement create/edit payloads and preserves immutable identifiers", async () => {
    const user = userEvent.setup();
    const createRequirement = vi.spyOn(service, "createRequirement").mockResolvedValue(requirement);
    const updateRequirement = vi.spyOn(service, "updateRequirement").mockResolvedValue({
      ...requirement,
      title: "Processing records updated",
    });
    vi.spyOn(service, "getRequirement").mockResolvedValue(requirement);

    renderPage(<CreateRequirementPage />);

    expect(await screen.findByText("Create requirement")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Regulation code"), "sox");
    await user.type(controlAfterLabel<HTMLInputElement>("Requirement code"), "sec-404");
    await user.type(controlAfterLabel<HTMLInputElement>("Regulation name"), "SOX");
    await user.type(controlAfterLabel<HTMLInputElement>("Requirement title"), "Management attest");
    await user.type(controlAfterLabel<HTMLInputElement>("Owner principal UUID"), "owner-9");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Description"),
      "Management certifies control operation"
    );
    await user.selectOptions(selectWithOption("conditional"), "conditional");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Applicability rationale"),
      "Public-company reporting scope"
    );
    await user.type(controlAfterLabel<HTMLInputElement>("Effective date"), "2026-01-01");
    await user.type(controlAfterLabel<HTMLInputElement>("Due date"), "2026-03-31");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Cross-reference requirement UUIDs"),
      "risk-1\n control-1, calendar-1"
    );
    await user.click(screen.getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    expect(createRequirement.mock.calls[0]?.[0]).toMatchObject({
      regulation_code: "SOX",
      requirement_code: "SEC-404",
      applicability: "conditional",
      applicability_rationale: "Public-company reporting scope",
      cross_references: ["risk-1", "control-1", "calendar-1"],
    });

    cleanup();
    renderPage(
      <Routes>
        <Route path="/requirements/:id/edit" element={<EditRequirementPage />} />
      </Routes>,
      "/requirements/requirement-1/edit"
    );

    expect(await screen.findByText("Edit requirement")).toBeVisible();
    expect(controlAfterLabel<HTMLInputElement>("Regulation code")).toBeDisabled();
    expect(controlAfterLabel<HTMLInputElement>("Requirement code")).toBeDisabled();
    await user.clear(controlAfterLabel<HTMLInputElement>("Requirement title"));
    await user.type(
      controlAfterLabel<HTMLInputElement>("Requirement title"),
      "Processing records updated"
    );
    await user.selectOptions(selectWithOption("mandatory"), "mandatory");
    expect(screen.queryByText("Applicability rationale")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(updateRequirement).toHaveBeenCalled());
    expect(updateRequirement.mock.calls[0]?.[0]).toBe("requirement-1");
    expect(updateRequirement.mock.calls[0]?.[1]).toMatchObject({
      regulation_code: "GDPR",
      requirement_code: "ART-30",
      title: "Processing records updated",
      applicability: "mandatory",
      applicability_rationale: "",
    });
  });

  it("edits controls and calendar events without mutating immutable relationship fields", async () => {
    const user = userEvent.setup();
    const updateControl = vi.spyOn(service, "updateControl").mockResolvedValue({
      ...control,
      frequency: "monthly",
      frequency_days: null,
    });
    const updateCalendarEntry = vi.spyOn(service, "updateCalendarEntry").mockResolvedValue({
      ...calendarEntry,
      title: "Updated filing",
    });
    vi.spyOn(service, "getControl").mockResolvedValue(control);
    vi.spyOn(service, "getCalendarEntry").mockResolvedValue(calendarEntry);

    renderPage(
      <Routes>
        <Route path="/controls/:id/edit" element={<EditControlPage />} />
      </Routes>,
      "/controls/control-1/edit"
    );

    expect(await screen.findByText("Edit control")).toBeVisible();
    expect(controlAfterLabel<HTMLInputElement>("Control code")).toBeDisabled();
    expect(controlAfterLabel<HTMLInputElement>("Risk UUID")).toBeDisabled();
    await user.clear(controlAfterLabel<HTMLInputElement>("Control name"));
    await user.type(controlAfterLabel<HTMLInputElement>("Control name"), "Monthly attestation");
    await user.selectOptions(screen.getByLabelText("Frequency"), "monthly");
    expect(screen.queryByText("Frequency days")).not.toBeInTheDocument();
    await user.clear(controlAfterLabel<HTMLInputElement>("Default tester UUID"));
    await user.click(screen.getByRole("button", { name: "Save control" }));

    await waitFor(() => expect(updateControl).toHaveBeenCalled());
    expect(updateControl).toHaveBeenCalledWith(
      "control-1",
      expect.objectContaining({
        risk_id: "risk-1",
        control_code: "CTRL-001",
        name: "Monthly attestation",
        frequency: "monthly",
        frequency_days: null,
        default_tester_id: null,
      })
    );

    cleanup();
    renderPage(
      <Routes>
        <Route path="/calendar/:id/edit" element={<EditCalendarEntryPage />} />
      </Routes>,
      "/calendar/calendar-1/edit"
    );

    expect(await screen.findByText("Edit calendar event")).toBeVisible();
    expect(controlAfterLabel<HTMLInputElement>("Requirement UUID")).toBeDisabled();
    await user.clear(controlAfterLabel<HTMLInputElement>("Event title"));
    await user.type(controlAfterLabel<HTMLInputElement>("Event title"), "Updated filing");
    await user.clear(controlAfterLabel<HTMLInputElement>("Reminder days"));
    await user.type(controlAfterLabel<HTMLInputElement>("Reminder days"), "21, bad, 3, 21");
    await user.click(screen.getByRole("button", { name: "Save event" }));

    await waitFor(() => expect(updateCalendarEntry).toHaveBeenCalled());
    expect(updateCalendarEntry).toHaveBeenCalledWith(
      "calendar-1",
      expect.objectContaining({
        requirement_id: "requirement-1",
        title: "Updated filing",
        reminder_days: [21, 3],
      })
    );
  });

  it("keeps configuration publication fail-closed until a valid preview and summary exist", async () => {
    const user = userEvent.setup();
    const previewConfiguration = vi.spyOn(service, "previewConfiguration").mockResolvedValue({
      valid: false,
      validation_errors: [
        { field: "level_thresholds.high", code: "invalid_order", message: "High must increase." },
      ],
      score_band_changes: [],
      affected_record_counts: { risks: 0, controls: 0, calendar_entries: 0 },
    });
    const publishConfiguration = vi
      .spyOn(service, "publishConfiguration")
      .mockResolvedValue(configuration);
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);

    renderPage(<RiskConfigurationPage />);

    expect(await screen.findByText("Risk configuration")).toBeVisible();
    expect(screen.getByRole("button", { name: "Publish configuration" })).toBeDisabled();
    await user.clear(screen.getByLabelText("high maximum score"));
    await user.type(screen.getByLabelText("high maximum score"), "4");
    await user.type(controlAfterLabel<HTMLTextAreaElement>("Version summary"), "Invalid threshold");
    await user.click(screen.getByRole("button", { name: "Preview impact" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Candidate is invalid");
    expect(screen.getByText("level_thresholds.high: High must increase.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Publish configuration" })).toBeDisabled();
    const previewRequest = previewConfiguration.mock.calls[0]?.[0];
    expect(previewRequest?.environment).toBe("development");
    expect(previewRequest?.candidate.level_thresholds.high).toBe(4);
    expect(publishConfiguration).not.toHaveBeenCalled();
  });

  it("serializes control, test, calendar, and remediation filters through governed list views", async () => {
    const user = userEvent.setup();
    const listControls = vi.spyOn(service, "listControls").mockResolvedValue(paginated([control]));
    vi.spyOn(service, "listTests").mockResolvedValue(paginated([controlTest]));
    vi.spyOn(service, "listCalendarEntries").mockResolvedValue(paginated([calendarEntry]));
    vi.spyOn(service, "listRemediations").mockResolvedValue(paginated([remediation]));

    renderPage(<ControlListPage />, "/controls?risk_id=risk-1&status=active&frequency=monthly");
    expect(await screen.findByText("Controls & tests")).toBeVisible();
    expect(listControls).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 25,
      status: "active",
      frequency: "monthly",
      risk_id: "risk-1",
      ordering: "next_test_due",
    });
    await user.selectOptions(selectWithOption("-created_at"), "-created_at");
    await waitFor(() =>
      expect(listControls).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: "-created_at", page: 1 })
      )
    );

    cleanup();
    renderPage(<ControlTestListPage />, "/tests?status=completed&result=failed");
    expect(await screen.findByText("Control tests")).toBeVisible();
    expect(service.listTests).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 25,
      status: "completed",
      control_id: undefined,
      result: "failed",
      ordering: "scheduled_for",
    });

    cleanup();
    renderPage(
      <ComplianceCalendarPage />,
      "/calendar?date_from=2026-08-01&date_to=2026-08-31&event_type=audit&status=upcoming&view=agenda"
    );
    expect(await screen.findByText("Compliance calendar")).toBeVisible();
    expect(service.listCalendarEntries).toHaveBeenLastCalledWith({
      date_from: "2026-08-01",
      date_to: "2026-08-31",
      event_type: "audit",
      status: "upcoming",
      page: 1,
      page_size: 100,
      ordering: "scheduled_date",
    });

    cleanup();
    renderPage(<RemediationListPage />, "/remediations?status=planned&priority=critical");
    expect(await screen.findByText("Remediation")).toBeVisible();
    expect(service.listRemediations).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 25,
      status: "planned",
      priority: "critical",
      assigned_to_id: undefined,
      risk_id: undefined,
      ordering: "due_date",
    });
  });

  it("keeps retryable list and configuration-history failures visible with explicit refetch actions", async () => {
    const user = userEvent.setup();
    const listCalendarEntries = vi
      .spyOn(service, "listCalendarEntries")
      .mockRejectedValueOnce(
        new ComplianceRiskApiError("Calendar service unavailable", 503, "UNAVAILABLE", "corr-cal")
      )
      .mockResolvedValueOnce(paginated([]));
    const listConfigurationVersions = vi
      .spyOn(service, "listConfigurationVersions")
      .mockRejectedValueOnce(
        new ComplianceRiskApiError("History query failed", 502, "BAD_GATEWAY", "corr-history")
      )
      .mockResolvedValueOnce(paginated([configurationVersion]));

    renderPage(<ComplianceCalendarPage />, "/calendar?date_from=2026-08-01&date_to=2026-08-31");
    expect(await screen.findByText("Calendar service unavailable")).toBeVisible();
    expect(screen.getByText("Correlation ID: corr-cal")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No compliance events in this range")).toBeVisible();
    expect(listCalendarEntries).toHaveBeenCalledTimes(2);

    cleanup();
    renderPage(
      <RiskConfigurationHistoryPage />,
      "/configuration/history?environment=production&page=2"
    );
    expect(await screen.findByText("History query failed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Configuration history")).toBeVisible();
    expect(listConfigurationVersions).toHaveBeenLastCalledWith("production", 2);
  });

  it("fails closed for read-only control detail actions while preserving tester transitions", async () => {
    vi.spyOn(service, "getControl").mockResolvedValue(control);
    vi.spyOn(service, "listControlTests").mockResolvedValue(paginated([]));

    authState.user.tenant_role = "tester";
    renderPage(
      <Routes>
        <Route path="/controls/:id" element={<ControlDetailPage />} />
      </Routes>,
      "/controls/control-1"
    );

    expect(await screen.findByText("CTRL-001 · Vendor attestation")).toBeVisible();
    expect(screen.getByRole("button", { name: "Activate" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByText("No tests scheduled")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Schedule test" })).not.toBeInTheDocument();
  });

  it("surfaces governed control mutation field errors without dropping the attempted payload", async () => {
    const user = userEvent.setup();
    const createControl = vi.spyOn(service, "createControl").mockRejectedValue(
      new ComplianceRiskApiError("Validation failed", 400, "VALIDATION_ERROR", "corr-control", {
        fields: [
          {
            field: "frequency_days",
            code: "min_value",
            message: "Custom cadence must be at least 7 days.",
          },
        ],
      })
    );

    renderPage(<CreateControlPage />);

    expect(await screen.findByText("Create control")).toBeVisible();
    await user.type(controlAfterLabel<HTMLInputElement>("Control code"), "ctrl-010");
    await user.type(controlAfterLabel<HTMLInputElement>("Risk UUID"), "risk-10");
    await user.type(controlAfterLabel<HTMLInputElement>("Control name"), "Evidence aging review");
    await user.type(controlAfterLabel<HTMLInputElement>("Owner principal UUID"), "owner-10");
    await user.type(controlAfterLabel<HTMLTextAreaElement>("Description"), "Review aging evidence");
    await user.type(
      controlAfterLabel<HTMLTextAreaElement>("Test procedure"),
      "Compare evidence dates to configured freshness policy"
    );
    await user.selectOptions(screen.getByLabelText("Frequency"), "custom");
    await user.clear(controlAfterLabel<HTMLInputElement>("Frequency days"));
    await user.type(controlAfterLabel<HTMLInputElement>("Frequency days"), "3");
    await user.type(controlAfterLabel<HTMLInputElement>("Next test due"), "2026-09-30");
    await user.click(screen.getByRole("button", { name: "Save control" }));

    await waitFor(() => expect(createControl).toHaveBeenCalled());
    expect(createControl.mock.calls[0]?.[0]).toMatchObject({
      control_code: "CTRL-010",
      risk_id: "risk-10",
      frequency: "custom",
      frequency_days: 3,
      next_test_due: "2026-09-30",
    });
    expect(await screen.findByText("Validation failed")).toBeVisible();
    expect(screen.getByText("Custom cadence must be at least 7 days.")).toBeVisible();
    expect(screen.getByText("Correlation ID: corr-control")).toBeVisible();
  });
});
