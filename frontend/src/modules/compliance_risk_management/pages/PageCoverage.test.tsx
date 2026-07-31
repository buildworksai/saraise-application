/* eslint-disable max-lines-per-function -- page fixtures intentionally exercise multiple compliance risk UI branches. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  RemediationDetailPage,
} from "./CalendarRemediationPages";
import { ControlDetailPage, ControlListPage, ExecuteControlTestPage } from "./ControlPages";
import {
  ComplianceRiskDashboardPage,
  RiskConfigurationPage,
  RiskConfigurationVersionDetailPage,
} from "./DashboardConfigurationPages";
import { RequirementDetailPage, RequirementListPage } from "./RequirementPages";
import { RiskAssessmentDetailPage } from "./RiskPages";

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
    expect(screen.getByRole("gridcell", { name: /Likelihood 4, impact 5, 2 risks/i })).toBeEnabled();
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
    await user.type(controlAfterLabel<HTMLTextAreaElement>("Version summary"), "Align review cadence");
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
        <Route path="/configuration/history/:version" element={<RiskConfigurationVersionDetailPage />} />
      </Routes>,
      "/configuration/history/3?environment=development"
    );

    expect(await screen.findByText("Configuration version 3")).toBeVisible();
    expect(screen.getByText("Current active version")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Rollback to this version/i })).not.toBeInTheDocument();
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
      expect(service.listControls).toHaveBeenLastCalledWith(expect.objectContaining({ frequency: "custom" }))
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
        evidence: [{ document_id: "doc-1", version_id: "ver-1", label: "Attestation", checksum: "sha" }],
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
});
