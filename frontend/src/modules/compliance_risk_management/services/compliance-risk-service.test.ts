/* eslint-disable max-lines-per-function -- service contract tests intentionally keep endpoint call sequences together. */
/* eslint-disable @typescript-eslint/unbound-method */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import {
  ComplianceRiskApiError,
  complianceRiskQueryKeys,
  complianceRiskService as service,
} from "./compliance-risk-service";

vi.mock("@/services/api-client", () => {
  class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public details?: unknown,
      public code?: string,
      public correlationId?: string
    ) {
      super(message);
    }
  }
  return {
    ApiError,
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const meta = {
  correlation_id: "corr-1",
  timestamp: "2026-07-23T00:00:00Z",
  pagination: {
    page: 1,
    page_size: 25,
    count: 0,
    total_pages: 0,
    has_next: false,
    has_previous: false,
  },
};
const featureFlags = {
  risk_heatmap: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
  recurring_control_tests: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
  compliance_reminders: { roles: ["tenant_admin"], cohorts: ["default"], enabled: true },
};

describe("compliance risk service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps only governed paginated envelopes and URL-encodes typed filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta });
    await expect(
      service.listRisks({ search: "policy & audit", status: "assessed", page: 2, page_size: 50 })
    ).resolves.toMatchObject({ items: [], correlation_id: "corr-1" });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.RISKS.LIST}?search=policy+%26+audit&status=assessed&page=2&page_size=50`
    );
  });

  it("rejects a fabricated collection without governed pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-2", timestamp: meta.timestamp },
    });
    await expect(service.listControls()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      correlationId: "corr-2",
    });
  });

  it("preserves status, stable code, correlation ID, and detail", async () => {
    const { ApiError } = await import("@/services/api-client");
    vi.mocked(apiClient.get).mockRejectedValue(
      new ApiError(
        "Dependency unavailable",
        503,
        { error: { detail: "safe" } },
        "CAPABILITY_UNAVAILABLE",
        "corr-503"
      )
    );
    const failure = await service.getRisk("risk-id").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ComplianceRiskApiError);
    expect(failure).toMatchObject({
      status: 503,
      code: "CAPABILITY_UNAVAILABLE",
      correlationId: "corr-503",
    });
  });

  it("uses tenant-separated stable query keys including filters and page size", () => {
    expect(complianceRiskQueryKeys.risks("tenant-a", { page: 1, page_size: 25 })).not.toEqual(
      complianceRiskQueryKeys.risks("tenant-b", { page: 1, page_size: 25 })
    );
    expect(complianceRiskQueryKeys.risks("tenant-a", { page: 1, page_size: 25 })).not.toEqual(
      complianceRiskQueryKeys.risks("tenant-a", { page: 2, page_size: 100 })
    );
  });

  it("routes control, calendar, and remediation mutations without dropping governed payload fields", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta });
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "created-1" }, meta });
    vi.mocked(apiClient.patch).mockResolvedValue({ data: { id: "updated-1" }, meta });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await service.listRiskControls("risk/with space", { status: "active", frequency: "custom" });
    await service.createRiskControl("risk-1", {
      control_code: "CTRL-9",
      name: "Daily review",
      description: "Review queued compliance exceptions.",
      test_procedure: "Sample exception approvals.",
      frequency: "daily",
      frequency_days: null,
      owner_id: "owner-1",
      default_tester_id: null,
      next_test_due: "2026-09-01",
    });
    await service.scheduleControlTest(
      "control-1",
      { scheduled_for: "2026-09-01", tester_id: "tester-1" },
      "schedule-key"
    );
    await service.startTest("test-1", { transition_key: "start-key" });
    await service.recordTestResult("test-1", {
      transition_key: "result-key",
      result: "failed",
      findings: "Missing evidence.",
      evidence: [{ document_id: "doc-1", version_id: "v1", label: "Packet", checksum: "sha" }],
      remediation: {
        action_code: "REM-9",
        description: "Collect missing evidence.",
        assigned_to_id: "owner-1",
        due_date: "2026-09-10",
        priority: "high",
      },
    });
    await service.cancelTest("test-1", { transition_key: "cancel-key", reason: "Duplicate" });
    await service.updateScheduledTest("test-1", { scheduled_for: "2026-09-03" });
    await service.deleteControl("control-1");

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.RISKS.CONTROLS("risk/with space")}?status=active&frequency=custom`
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONTROLS.TESTS("control-1"),
      expect.objectContaining({ scheduled_for: "2026-09-01", idempotency_key: "schedule-key" })
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.TESTS.RESULT("test-1"),
      expect.objectContaining({
        transition_key: "result-key",
        remediation: {
          action_code: "REM-9",
          description: "Collect missing evidence.",
          assigned_to_id: "owner-1",
          due_date: "2026-09-10",
          priority: "high",
        },
      })
    );
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.TESTS.CANCEL("test-1"), {
      transition_key: "cancel-key",
      reason: "Duplicate",
    });
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.TESTS.UPDATE("test-1"), {
      scheduled_for: "2026-09-03",
    });
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.CONTROLS.DELETE("control-1"));
  });

  it("serializes calendar, remediation, dashboard, configuration, job, and health endpoints", async () => {
    const success = { data: { id: "record-1" }, meta };
    vi.mocked(apiClient.get).mockResolvedValue(success);
    vi.mocked(apiClient.post).mockResolvedValue(success);
    vi.mocked(apiClient.put).mockResolvedValue(success);
    vi.mocked(apiClient.patch).mockResolvedValue(success);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await service.listCalendarEntries({
      date_from: "2026-08-01",
      date_to: "2026-08-31",
      event_type: "audit",
      status: "upcoming",
      page: 2,
      page_size: 100,
    });
    await service.createCalendarEntry({
      requirement_id: "requirement-1",
      title: "Audit",
      event_type: "audit",
      scheduled_date: "2026-08-15",
      reminder_days: [30, 7],
      assigned_to_id: "owner-1",
    });
    await service.updateCalendarEntry("calendar-1", { title: "Updated audit" });
    await service.transitionCalendarEntry("calendar-1", {
      command: "complete",
      transition_key: "calendar-key",
      context: { completion_date: "2026-08-15", completion_notes: "Filed." },
    });
    await service.deleteCalendarEntry("calendar-1");
    await service.listRemediations({
      status: "planned",
      priority: "critical",
      assigned_to_id: "owner-1",
      risk_id: "risk-1",
    });
    await service.createRiskRemediation("risk-1", {
      control_test_id: null,
      action_code: "REM-1",
      description: "Close gap.",
      assigned_to_id: "owner-1",
      due_date: "2026-09-01",
      priority: "critical",
    });
    await service.updateRemediation("remediation-1", { priority: "medium" });
    await service.transitionRemediation("remediation-1", {
      command: "cancel",
      transition_key: "remediation-key",
      context: { cancellation_reason: "Superseded." },
    });
    await service.deleteRemediation("remediation-1");
    await service.getDashboard({ category: "compliance", owner_id: "owner-1" });
    await service.getHeatmap({ category: "technology" });
    await service.getConfiguration("production");
    await service.previewConfiguration({
      environment: "staging",
      candidate: {
        likelihood_scale_max: 5,
        impact_scale_max: 5,
        level_thresholds: { negligible: 2, low: 5, medium: 10, high: 15, critical: 25 },
        default_review_days: 90,
        default_reminder_days: [30, 7],
        acceptance_max_days: 60,
        overdue_job_enabled: true,
        feature_flags: featureFlags,
      },
    });
    await service.publishConfiguration({
      environment: "staging",
      candidate: {
        likelihood_scale_max: 5,
        impact_scale_max: 5,
        level_thresholds: { negligible: 2, low: 5, medium: 10, high: 15, critical: 25 },
        default_review_days: 90,
        default_reminder_days: [30, 7],
        acceptance_max_days: 60,
        overdue_job_enabled: true,
        feature_flags: featureFlags,
      },
      expected_version: 3,
      change_summary: "Publish governed scoring policy.",
    });
    await service.listConfigurationVersions("production", 3, 50);
    await service.getConfigurationVersion("production", 7);
    await service.rollbackConfiguration({
      environment: "production",
      version: 6,
      expected_version: 7,
      change_summary: "Rollback unstable thresholds.",
    });
    await service.exportConfiguration("production");
    await service.importConfiguration({
      environment: "production",
      document: {
        schema: "saraise.compliance-risk.configuration",
        schema_version: 1,
        version: 7,
        environment: "production",
        configuration: {
          likelihood_scale_max: 5,
          impact_scale_max: 5,
          level_thresholds: { negligible: 2, low: 5, medium: 10, high: 15, critical: 25 },
          default_review_days: 90,
          default_reminder_days: [30, 7],
          acceptance_max_days: 60,
          overdue_job_enabled: true,
          feature_flags: featureFlags,
        },
      },
      dry_run: false,
      expected_version: 7,
      change_summary: "Promote reviewed configuration.",
    });
    await service.getJob("job/with space");
    await service.getLiveness();
    await service.getReadiness();

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CALENDAR.LIST}?date_from=2026-08-01&date_to=2026-08-31&event_type=audit&status=upcoming&page=2&page_size=100`
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CALENDAR.TRANSITION("calendar-1"),
      expect.objectContaining({ transition_key: "calendar-key" })
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.REMEDIATIONS.LIST}?status=planned&priority=critical&assigned_to_id=owner-1&risk_id=risk-1`
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.REMEDIATIONS.TRANSITION("remediation-1"),
      expect.objectContaining({ transition_key: "remediation-key" })
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DASHBOARD}?category=compliance&owner_id=owner-1`
    );
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.HEATMAP}?category=technology`);
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.ACTIVE}?environment=production`
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.ACTIVE,
      expect.objectContaining({ environment: "staging", expected_version: 3 })
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.VERSIONS}?environment=production&page=3&page_size=50`
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.VERSION(7)}?environment=production`
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.IMPORT,
      expect.objectContaining({ dry_run: false, expected_version: 7 })
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.JOB("job/with space"));
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.HEALTH.LIVE);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.HEALTH.READY);
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.CALENDAR.DELETE("calendar-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.REMEDIATIONS.DELETE("remediation-1"));
  });
});
