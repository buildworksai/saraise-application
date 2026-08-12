/* eslint-disable max-lines-per-function -- page fixtures intentionally exercise multiple compliance UI branches. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ComplianceAssessment,
  ComplianceActivity,
  ComplianceConfigurationRevision,
  ComplianceEvidence,
  ComplianceFramework,
  CompliancePolicy,
  CompliancePolicyVersion,
  ComplianceRequirement,
  DashboardSummaryDTO,
  PaginatedEnvelope,
  RequirementPolicyMapping,
} from "../contracts";
import { complianceService } from "../services/compliance-service";
import {
  ComplianceDashboardPage,
  CreateFrameworkPage,
  CreateCompliancePolicyPage,
  CreateEvidencePage,
  CreateAssessmentPage,
  EditFrameworkPage,
  EditRequirementPage,
  AssessmentHistoryPage,
  ComplianceActivityPage,
  CompliancePolicyDetailPage,
  EditCompliancePolicyPage,
  EditEvidencePage,
  CompliancePolicyListPage,
  ConfigurationDetailPage,
  ConfigurationListPage,
  EditConfigurationPage,
  EvidenceDetailPage,
  EvidenceListPage,
  FrameworkDetailPage,
  FrameworkListPage,
  CreateRequirementPage,
  RequirementMappingPage,
  RequirementDetailPage,
  RequirementListPage,
} from "./CompliancePages";

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

const page = <T,>(data: T[]): PaginatedEnvelope<T> => ({
  data,
  meta: {
    correlation_id: "corr-page",
    timestamp: "2026-07-31T00:00:00Z",
    pagination: {
      page: 1,
      page_size: 25,
      count: data.length,
      total_pages: data.length ? 2 : 0,
      has_next: Boolean(data.length),
      has_previous: false,
    },
  },
});

const audit = {
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
  created_by: "actor-1",
  updated_by: null,
  deleted_at: null,
  deleted_by: null,
};

const framework: ComplianceFramework = {
  ...audit,
  id: "framework-1",
  code: "SOC2",
  name: "SOC 2",
  version: "2026",
  category: "security",
  description: "Trust services criteria",
  source_kind: "custom",
  source_package: "",
  source_version: "",
  status: "draft",
  requirement_count: 2,
  allowed_actions: ["update", "activate"],
};

const requirement: ComplianceRequirement = {
  ...audit,
  id: "requirement-1",
  framework: "framework-1",
  framework_code: "SOC2",
  code: "CC1.1",
  title: "Governance responsibilities",
  description: "Board oversight is documented.",
  section: "CC1",
  guidance: "Review board minutes.",
  applicability: "applicable",
  applicability_rationale: "",
  status: "active",
  sort_order: 1,
  tags: ["governance", "board"],
  mapping_count: 0,
  evidence_count: 0,
  gap_status: undefined,
  allowed_actions: ["update"],
};

const assessment: ComplianceAssessment = {
  id: "assessment-1",
  requirement: "requirement-1",
  requirement_code: "CC1.1",
  mapping: null,
  status: "partial",
  notes: "",
  assessor: "assessor-1",
  assessed_at: "2026-07-20T00:00:00Z",
  due_date: null,
  source: "manual",
  created_at: "2026-07-20T00:00:00Z",
};

const policy: CompliancePolicy = {
  ...audit,
  id: "policy-1",
  code: "POL-001",
  title: "Vendor compliance policy",
  summary: "Vendor controls must stay current.",
  category: "third_party",
  owner: "owner-1",
  owner_name: "Control owner",
  review_frequency_days: 180,
  effective_date: "2026-01-01",
  expiry_date: "2027-01-01",
  next_review_date: "2026-07-01",
  status: "draft",
  current_version: 1,
  mapping_count: 0,
  allowed_actions: ["update"],
};

const evidence: ComplianceEvidence = {
  ...audit,
  id: "evidence-1",
  name: "SOC report",
  description: "Independent report",
  evidence_type: "report",
  reference_kind: "external_url",
  document_id: null,
  external_uri: "https://example.invalid/soc.pdf",
  text_reference: "",
  sha256: "a".repeat(64),
  classification: "confidential",
  collection_method: "manual",
  collected_by: "collector-1",
  collected_at: "2026-07-20T00:00:00Z",
  valid_from: "2026-07-01T00:00:00Z",
  valid_until: "2026-12-31T00:00:00Z",
  requirement_links: [],
  allowed_actions: ["update", "validate"],
};

const configurationDocument = {
  policy_code_prefix: "POL",
  default_review_frequency_days: 365,
  expiry_warning_days: 60,
  evidence_warning_days: 30,
  minimum_assessment_note_length: 20,
  allow_external_evidence_urls: false,
  bulk_import_row_limit: 500,
  regulation_categories: ["security", "privacy"],
  rollout: {
    frameworks: { enabled: false, roles: ["compliance_admin"], cohorts: ["default"] },
  },
};

const configurationRevision: ComplianceConfigurationRevision = {
  id: "configuration-1",
  environment: "staging",
  version: 2,
  status: "draft",
  ...configurationDocument,
  document: configurationDocument,
  created_by: "admin-1",
  created_at: "2026-07-20T00:00:00Z",
  activated_at: null,
  activated_by: null,
  allowed_actions: ["update", "activate"],
};

const mapping: RequirementPolicyMapping = {
  ...audit,
  id: "mapping-1",
  requirement: "requirement-1",
  requirement_code: "CC1.1",
  policy: "policy-1",
  policy_code: "POL-001",
  policy_version: "version-1",
  coverage: "full",
  rationale: "Policy covers the control objective.",
  mapped_at: "2026-07-21T00:00:00Z",
};

const policyVersion: CompliancePolicyVersion = {
  id: "version-1",
  policy: "policy-1",
  version: 1,
  content: "Policy content body",
  content_sha256: "b".repeat(64),
  change_summary: "Initial controlled release",
  created_by: "author-1",
  created_at: "2026-07-22T00:00:00Z",
  approved_by: null,
  approved_at: null,
  published_by: null,
  published_at: null,
};

const activityEntry: ComplianceActivity = {
  id: "activity-1",
  entity_type: "policy",
  entity_id: "policy-1",
  action: "policy.submit",
  actor: "reviewer-1",
  occurred_at: "2026-07-23T00:00:00Z",
  correlation_id: "corr-activity",
  reason: "",
  before: { status: "draft" },
  after: { status: "in_review" },
};

function renderPage(ui: React.ReactElement, initialEntry = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("compliance management pages", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders dashboard loading, guided incomplete steps, and a clear assessment queue", async () => {
    const summary: DashboardSummaryDTO = {
      frameworks: 1,
      requirements: 4,
      unassessed_requirements: 0,
      gaps: 1,
      review_queue: 2,
      expiring_evidence: 3,
    };
    vi.spyOn(complianceService, "dashboard").mockResolvedValue(summary);

    renderPage(<ComplianceDashboardPage />);

    expect(screen.getByLabelText("Loading compliance workspace")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(await screen.findByText("Compliance workspace")).toBeVisible();
    expect(screen.getByText("Requirements")).toBeVisible();
    expect(screen.getByText("4")).toBeVisible();
    expect(screen.getByText("Queue is clear")).toBeVisible();
    expect(screen.getByText("Author policies")).toBeVisible();
  });

  it("saves, restores, filters, and paginates framework list state", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.frameworks, "list").mockResolvedValue(page([framework]));

    renderPage(<FrameworkListPage />);

    expect(await screen.findByRole("link", { name: "SOC 2" })).toBeVisible();
    await user.type(screen.getByLabelText("Search"), "soc{Enter}");
    await user.click(screen.getByRole("button", { name: "Save filter" }));
    expect(localStorage.getItem("compliance-filter:frameworks")).toContain("search=soc");
    await user.selectOptions(screen.getByLabelText("Framework status"), "active");
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "soc", status: "active" })
      )
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "soc", status: undefined })
      )
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
  });

  it("renders framework detail readiness and hides forbidden actions", async () => {
    vi.spyOn(complianceService.frameworks, "get").mockResolvedValue({
      ...framework,
      status: "active",
      allowed_actions: [],
      description: "",
    });
    vi.spyOn(complianceService.frameworks, "status").mockResolvedValue({
      framework,
      readiness: {
        framework_id: "framework-1",
        score: 75,
        earned_points: 3,
        possible_points: 4,
        formula: "earned / possible",
        requirements: [
          { requirement_id: "requirement-1", code: "CC1.1", status: "partial", points: 1 },
          {
            requirement_id: "requirement-2",
            code: "CC1.2",
            status: "not_assessed",
            points: 0,
          },
        ],
      },
      gaps: { framework_id: "framework-1", total: 2, gap_count: 1, gaps: [] },
    });

    renderPage(
      <Routes>
        <Route path="/frameworks/:id" element={<FrameworkDetailPage />} />
      </Routes>,
      "/frameworks/framework-1"
    );

    expect(await screen.findByText("SOC 2")).toBeVisible();
    expect(screen.getByText("75.0%")).toBeVisible();
    expect(screen.getByText("No description provided.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("renders requirement grouped list filters and empty create action", async () => {
    const user = userEvent.setup();
    const list = vi.spyOn(complianceService.requirements, "list");
    list.mockResolvedValueOnce(page([requirement])).mockResolvedValue(page([]));

    renderPage(<RequirementListPage />);

    expect(await screen.findByRole("link", { name: "Governance responsibilities" })).toBeVisible();
    expect(screen.getByText("0 policies · 0 evidence")).toBeVisible();
    await user.type(screen.getByLabelText("Framework UUID"), "framework-1");
    await user.tab();
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(
        expect.objectContaining({ framework_id: "framework-1" })
      )
    );
    expect(await screen.findByText("No requirements")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create requirement" })).toBeEnabled();
  });

  it("renders requirement detail gap, assessment, mappings, and evidence branches", async () => {
    vi.spyOn(complianceService.requirements, "get").mockResolvedValue(requirement);
    vi.spyOn(complianceService.assessments, "list").mockResolvedValue(page([assessment]));
    vi.spyOn(complianceService.mappings, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService.evidence, "list").mockResolvedValue(page([]));

    renderPage(
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetailPage />} />
      </Routes>,
      "/requirements/requirement-1"
    );

    expect(await screen.findByText("Governance responsibilities")).toBeVisible();
    expect(screen.getByText("unmapped")).toBeVisible();
    expect(screen.getByText("No notes.")).toBeVisible();
    expect(screen.getByText(/explainable gap/i)).toBeVisible();
    expect(screen.getByText("No evidence is attached.")).toBeVisible();
  });

  it("validates policy metadata locally before creating a governed policy payload", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(complianceService.policies, "create").mockResolvedValue(policy);

    renderPage(<CreateCompliancePolicyPage />);

    expect(await screen.findByText("Create policy")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save policy" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Code, title, and category are required.");
    expect(create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Policy code"), "POL-009");
    await user.type(screen.getByLabelText("Title"), "Supplier due diligence");
    await user.type(screen.getByLabelText("Category"), "third_party");
    await user.type(screen.getByLabelText("Owner ID"), "owner-9");
    await user.clear(screen.getByLabelText("Review frequency (days)"));
    await user.type(screen.getByLabelText("Review frequency (days)"), "90");
    await user.type(screen.getByLabelText("Effective date"), "2026-08-01");
    await user.type(screen.getByLabelText("Expiry date"), "2027-08-01");
    await user.type(screen.getByLabelText("Summary"), "Review supplier attestations quarterly.");
    await user.click(screen.getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      code: "POL-009",
      title: "Supplier due diligence",
      category: "third_party",
      owner_id: "owner-9",
      review_frequency_days: 90,
      effective_date: "2026-08-01",
      expiry_date: "2027-08-01",
    });
  });

  it("validates evidence references and creates external evidence with ISO dates", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(complianceService.evidence, "create").mockResolvedValue(evidence);

    renderPage(<CreateEvidencePage />);

    expect(await screen.findByText("Register evidence")).toBeVisible();
    await user.type(screen.getByLabelText("Name"), "Vendor SOC report");
    await user.selectOptions(screen.getByLabelText("Reference kind"), "external_url");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));
    expect(screen.getByRole("alert")).toHaveTextContent("An external URL is required.");
    expect(create).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Type"), "report");
    await user.selectOptions(screen.getByLabelText("Classification"), "confidential");
    await user.type(screen.getByLabelText("External URL"), "https://example.invalid/soc.pdf");
    fireEvent.change(screen.getByLabelText("Collected at"), {
      target: { value: "2026-07-20T10:00" },
    });
    fireEvent.change(screen.getByLabelText("Valid from"), {
      target: { value: "2026-07-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Valid until"), {
      target: { value: "2026-12-31T23:59" },
    });
    await user.type(screen.getByLabelText("Description"), "Independent assurance report");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      name: "Vendor SOC report",
      evidence_type: "report",
      reference_kind: "external_url",
      external_uri: "https://example.invalid/soc.pdf",
      classification: "confidential",
      collected_at: new Date("2026-07-20T10:00").toISOString(),
      valid_from: new Date("2026-07-01T00:00").toISOString(),
      valid_until: new Date("2026-12-31T23:59").toISOString(),
    });
  });

  it("creates a compliance configuration revision with normalized limits and rollout policy", async () => {
    const user = userEvent.setup();
    const create = vi
      .spyOn(complianceService.configuration, "create")
      .mockResolvedValue(configurationRevision);

    renderPage(<EditConfigurationPage />, "/configuration/new?environment=staging");

    expect(await screen.findByText("Create configuration revision")).toBeVisible();
    await user.clear(screen.getByLabelText("Policy code prefix"));
    await user.type(screen.getByLabelText("Policy code prefix"), "cmp");
    await user.clear(screen.getByLabelText("Default review frequency (days)"));
    await user.type(screen.getByLabelText("Default review frequency (days)"), "120");
    fireEvent.click(screen.getByLabelText("Allow external evidence URLs"));
    fireEvent.click(screen.getByLabelText("Enable framework capability"));
    fireEvent.change(screen.getByLabelText("Regulation categories"), {
      target: { value: "security, privacy, ai" },
    });
    fireEvent.change(screen.getByLabelText("Rollout roles"), {
      target: { value: "compliance_admin, auditor" },
    });
    fireEvent.change(screen.getByLabelText("Rollout cohorts"), {
      target: { value: "default" },
    });
    await user.click(screen.getByRole("button", { name: "Save draft revision" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      environment: "staging",
      document: {
        policy_code_prefix: "CMP",
        default_review_frequency_days: 120,
        allow_external_evidence_urls: true,
        regulation_categories: ["security", "privacy", "ai"],
        rollout: {
          frameworks: {
            roles: ["compliance_admin", "auditor"],
            cohorts: ["default"],
          },
        },
      },
    });
  });

  it("filters the policy list, renders owner fallbacks, and reports empty guided creation", async () => {
    const user = userEvent.setup();
    const list = vi.spyOn(complianceService.policies, "list");
    list.mockResolvedValueOnce(page([{ ...policy, owner: null, owner_name: undefined }]));
    list.mockResolvedValue(page([]));

    renderPage(<CompliancePolicyListPage />);

    expect(await screen.findByRole("link", { name: "Vendor compliance policy" })).toBeVisible();
    expect(screen.getByText("Unassigned")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Policy status"), "published");

    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ status: "published" }))
    );
    expect(await screen.findByText("No policies")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create policy" })).toBeEnabled();
  });

  it("creates an immutable policy version and submits a draft policy with transition evidence", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.policies, "get").mockResolvedValue({
      ...policy,
      status: "draft",
      allowed_actions: ["update", "submit"],
      summary: "",
    });
    vi.spyOn(complianceService.policies, "versions").mockResolvedValue(page([]));
    vi.spyOn(complianceService.mappings, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService, "activity").mockResolvedValue(page([]));
    const createVersion = vi
      .spyOn(complianceService.policies, "createVersion")
      .mockResolvedValue(policyVersion);
    const transition = vi
      .spyOn(complianceService.policies, "transition")
      .mockResolvedValue({ ...policy, status: "in_review" });

    renderPage(
      <Routes>
        <Route path="/policies/:id" element={<CompliancePolicyDetailPage />} />
      </Routes>,
      "/policies/policy-1"
    );

    expect(await screen.findByText("No summary provided.")).toBeVisible();
    expect(screen.getByText("No policy versions")).toBeVisible();
    await user.type(screen.getByLabelText("Policy content"), "Controlled policy body");
    await user.type(screen.getByLabelText("Change summary"), "Initial release");
    await user.click(screen.getByRole("button", { name: "Create immutable version" }));

    await waitFor(() => expect(createVersion).toHaveBeenCalled());
    expect(createVersion.mock.calls[0]?.[0]).toBe("policy-1");
    expect(createVersion.mock.calls[0]?.[1]).toEqual({
      content: "Controlled policy body",
      change_summary: "Initial release",
    });
    expect(createVersion.mock.calls[0]?.[2]).toMatch(/^compliance-ui:policy-version:/);

    await user.click(screen.getByRole("button", { name: "submit" }));
    await waitFor(() => expect(transition).toHaveBeenCalled());
    expect(transition.mock.calls[0]?.[0]).toBe("policy-1");
    expect(transition.mock.calls[0]?.[1]).toBe("submit");
    expect(transition.mock.calls[0]?.[2].transition_key).toMatch(/^compliance-ui:policy-submit:/);
  });

  it("bulk maps requirements to published policies only after a selected policy exists", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.requirements, "list").mockResolvedValue(page([requirement]));
    vi.spyOn(complianceService.policies, "list").mockResolvedValue(
      page([{ ...policy, status: "published" }])
    );
    const bulk = vi.spyOn(complianceService.mappings, "bulk").mockResolvedValue([mapping]);

    renderPage(<RequirementMappingPage />, "/mapping?framework_id=framework-1");

    expect(await screen.findByText("CC1.1")).toBeVisible();
    expect(screen.getByRole("button", { name: "Save coverage updates" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Policy for CC1.1"), "policy-1");
    await user.selectOptions(screen.getByLabelText("Coverage for CC1.1"), "partial");
    await user.click(screen.getByRole("button", { name: "Save coverage updates" }));

    await waitFor(() => expect(bulk).toHaveBeenCalled());
    expect(bulk.mock.calls[0]?.[0]).toEqual({
      rows: [{ requirement_id: "requirement-1", policy_id: "policy-1", coverage: "partial" }],
    });
    expect(bulk.mock.calls[0]?.[1]).toMatch(/^compliance-ui:bulk-mapping:/);
  });

  it("requires rationale for non-compliant assessments and persists governed assessment payloads", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(complianceService.assessments, "create").mockResolvedValue(assessment);

    renderPage(<CreateAssessmentPage />, "/assessments/new?requirement=requirement-1");

    expect(await screen.findByText("Record assessment")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Assessment status"), "non_compliant");
    await user.click(screen.getByRole("button", { name: "Record immutable assessment" }));
    expect(create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/Notes/), "Board approval evidence is missing.");
    await user.type(screen.getByLabelText("Follow-up due date"), "2026-09-30");
    await user.click(screen.getByRole("button", { name: "Record immutable assessment" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toEqual({
      requirement_id: "requirement-1",
      status: "non_compliant",
      notes: "Board approval evidence is missing.",
      due_date: "2026-09-30",
    });
    expect(create.mock.calls[0]?.[1]).toMatch(/^compliance-ui:assessment:/);
  });

  it("imports portable configuration and switches environment-specific revision lists", async () => {
    const activeRevisions: ComplianceConfigurationRevision[] = [
      { ...configurationRevision, status: "active", activated_at: "2026-07-21T00:00:00Z" },
    ];
    const list = vi
      .spyOn(complianceService.configuration, "list")
      .mockResolvedValue({ ...page(activeRevisions), data: activeRevisions });
    const importConfiguration = vi
      .spyOn(complianceService.configuration, "import")
      .mockResolvedValue(configurationRevision);

    renderPage(<ConfigurationListPage />, "/configuration?environment=production");

    expect(await screen.findByRole("link", { name: "Review" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Environment"), { target: { value: "staging" } });
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({ environment: "staging", ordering: "-version" })
    );

    const portable = {
      schema: "saraise.compliance.configuration/v1",
      environment: "staging",
      configuration: configurationDocument,
    };
    const importFile = new File([JSON.stringify(portable)], "configuration.json", {
      type: "application/json",
    });
    Object.defineProperty(importFile, "text", {
      value: () => Promise.resolve(JSON.stringify(portable)),
    });
    const input = document.querySelector('input[type="file"]');
    expect(input).toBeInstanceOf(HTMLInputElement);
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [importFile],
      },
    });

    await waitFor(() => expect(importConfiguration).toHaveBeenCalled());
    expect(importConfiguration.mock.calls[0]?.[0]).toEqual(portable);
    expect(importConfiguration.mock.calls[0]?.[1]).toMatch(/^compliance-ui:configuration-import:/);
  });

  it("rejects malformed configuration imports before calling the governed import endpoint", async () => {
    const activeRevisions: ComplianceConfigurationRevision[] = [
      { ...configurationRevision, status: "active", activated_at: "2026-07-21T00:00:00Z" },
    ];
    vi.spyOn(complianceService.configuration, "list").mockResolvedValue({
      ...page(activeRevisions),
      data: activeRevisions,
    });
    const importConfiguration = vi.spyOn(complianceService.configuration, "import");

    renderPage(<ConfigurationListPage />, "/configuration?environment=production");

    expect(await screen.findByRole("link", { name: "Review" })).toBeVisible();
    const invalidFile = new File(["{"], "broken-configuration.json", {
      type: "application/json",
    });
    Object.defineProperty(invalidFile, "text", {
      value: () => Promise.resolve("{"),
    });
    const input = document.querySelector('input[type="file"]');
    expect(input).toBeInstanceOf(HTMLInputElement);
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [invalidFile],
      },
    });

    await waitFor(() =>
      expect(
        screen.getByText((content) => content.includes("Expected property name"))
      ).toBeVisible()
    );
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("previews, rolls back, and exports active configuration revisions", async () => {
    const createObjectURL = vi.fn(() => "blob:configuration");
    const revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    vi.spyOn(complianceService.configuration, "get").mockResolvedValue({
      ...configurationRevision,
      status: "active",
      activated_at: "2026-07-21T00:00:00Z",
    });
    vi.spyOn(complianceService.configuration, "preview").mockResolvedValue({
      revision_id: "configuration-1",
      environment: "staging",
      affected: { frameworks: 2, policies: 3, evidence: 4 },
      diff: [
        {
          field: "default_review_frequency_days",
          before: 365,
          after: 120,
        },
      ],
    });
    const rollback = vi
      .spyOn(complianceService.configuration, "rollback")
      .mockResolvedValue(configurationRevision);
    const exportRevision = vi.spyOn(complianceService.configuration, "export").mockResolvedValue({
      schema: "saraise.compliance.configuration/v1",
      environment: "staging",
      configuration: configurationDocument,
    });

    renderPage(
      <Routes>
        <Route path="/configuration/:id" element={<ConfigurationDetailPage />} />
      </Routes>,
      "/configuration/configuration-1"
    );

    expect(await screen.findByText("staging configuration v2")).toBeVisible();
    expect(screen.getByText("default_review_frequency_days")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Rollback to this version" }));
    await waitFor(() => expect(rollback).toHaveBeenCalled());
    expect(rollback.mock.calls[0]?.[1].transition_key).toMatch(
      /^compliance-ui:configuration-rollback:/
    );

    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(exportRevision).toHaveBeenCalledWith("configuration-1"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:configuration");
  });

  it("validates evidence from detail while preserving existing requirement evidence", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.evidence, "get").mockResolvedValue({
      ...evidence,
      requirement_links: [
        {
          id: "link-1",
          evidence: "evidence-1",
          requirement: "requirement-1",
          requirement_code: "CC1.1",
          relevance: "primary",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
    });
    const validate = vi.spyOn(complianceService.evidence, "validate").mockResolvedValue({
      evidence_id: "evidence-1",
      reference_valid: true,
      hash_valid: false,
      fresh: true,
      checked_at: "2026-07-23T00:00:00Z",
    });

    renderPage(
      <Routes>
        <Route path="/evidence/:id" element={<EvidenceDetailPage />} />
      </Routes>,
      "/evidence/evidence-1"
    );

    expect(await screen.findByText("SOC report")).toBeVisible();
    expect(screen.getByText("CC1.1 · primary")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Validate now" }));
    await waitFor(() => expect(validate).toHaveBeenCalledWith("evidence-1"));
    expect(await screen.findByText("Mismatch")).toBeVisible();
  });

  it("filters assessment history and renders expired evidence freshness without mutating", async () => {
    const assessmentList = vi
      .spyOn(complianceService.assessments, "list")
      .mockResolvedValue(page([{ ...assessment, notes: "" }]));
    vi.spyOn(complianceService.evidence, "list").mockResolvedValue(
      page([{ ...evidence, valid_until: "2020-01-01T00:00:00Z" }])
    );

    const history = renderPage(
      <AssessmentHistoryPage />,
      "/assessments?requirement_id=requirement-1&status=partial"
    );

    expect(await screen.findByText("CC1.1")).toBeVisible();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(assessmentList).toHaveBeenCalledWith(
      expect.objectContaining({ requirement_id: "requirement-1", status: "partial" })
    );
    history.unmount();

    renderPage(<EvidenceListPage />);
    expect(await screen.findByRole("link", { name: "SOC report" })).toBeVisible();
    expect(screen.getByText("expired")).toBeVisible();
  });

  it("updates existing evidence from loaded metadata with normalized nullable references", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.evidence, "get").mockResolvedValue({
      ...evidence,
      reference_kind: "dms_document",
      external_uri: "",
      text_reference: "",
      document_id: "document-1",
    });
    const update = vi
      .spyOn(complianceService.evidence, "update")
      .mockResolvedValue({ ...evidence, name: "Updated SOC report" });

    renderPage(
      <Routes>
        <Route path="/evidence/:id/edit" element={<EditEvidencePage />} />
      </Routes>,
      "/evidence/evidence-1/edit"
    );

    expect(await screen.findByDisplayValue("SOC report")).toBeVisible();
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated SOC report");
    await user.selectOptions(screen.getByLabelText("Reference kind"), "text_reference");
    await user.type(screen.getByLabelText("Text reference"), "Control owner attestation retained.");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0]?.[0]).toBe("evidence-1");
    expect(update.mock.calls[0]?.[1]).toMatchObject({
      name: "Updated SOC report",
      reference_kind: "text_reference",
      document_id: null,
      text_reference: "Control owner attestation retained.",
    });
  });

  it("renders evidence and activity list empty/error branches with retryable governed state", async () => {
    vi.spyOn(complianceService.evidence, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService, "activity").mockResolvedValue(page([activityEntry]));

    renderPage(<EvidenceListPage />);
    expect(await screen.findByText("No evidence")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Register evidence" })).toHaveLength(2);

    cleanup();
    renderPage(<ComplianceActivityPage />);
    expect(
      await screen.findByText((_, element) => element?.textContent === "policy.submit · policy")
    ).toBeVisible();
    expect(screen.getByText("No reason supplied.")).toBeVisible();
    expect(screen.getByText("Correlation: corr-activity")).toBeVisible();
  });

  it("surfaces dashboard service failures and missing dashboard payloads", async () => {
    const dashboard = vi
      .spyOn(complianceService, "dashboard")
      .mockRejectedValueOnce(new Error("dashboard offline"))
      .mockResolvedValueOnce(null as never);

    const failed = renderPage(<ComplianceDashboardPage />);

    expect(await screen.findByText("dashboard offline")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(dashboard).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No dashboard response was received.")).toBeVisible();
    failed.unmount();
  });

  it("creates extension-backed frameworks only after required metadata is complete", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(complianceService.frameworks, "create").mockResolvedValue({
      ...framework,
      id: "framework-new",
      source_kind: "extension",
      source_package: "soc2-extension",
    });

    renderPage(<CreateFrameworkPage />);

    expect(await screen.findByText("Create framework")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save framework" }));
    expect(create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Code"), "SOC2");
    await user.type(screen.getByLabelText("Name"), "SOC 2 Extension");
    await user.clear(screen.getByLabelText("Version"));
    await user.type(screen.getByLabelText("Version"), "2026");
    await user.type(screen.getByLabelText("Category"), "security");
    await user.selectOptions(screen.getByLabelText("Source kind"), "extension");
    await user.type(screen.getByLabelText("Source package"), "soc2-extension");
    await user.type(screen.getByLabelText("Description"), "Extension-managed SOC 2 controls.");
    await user.click(screen.getByRole("button", { name: "Save framework" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toEqual({
      code: "SOC2",
      name: "SOC 2 Extension",
      version: "2026",
      category: "security",
      description: "Extension-managed SOC 2 controls.",
      source_kind: "extension",
      source_package: "soc2-extension",
      source_version: "",
    });
  });

  it("creates not-applicable requirements with rationale and deduplicated bounded tags", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(complianceService.requirements, "create").mockResolvedValue({
      ...requirement,
      id: "requirement-new",
      applicability: "not_applicable",
    });

    renderPage(<CreateRequirementPage />);

    expect(await screen.findByText("Create requirement")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save requirement" }));
    expect(create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Framework UUID"), "framework-1");
    await user.type(screen.getByLabelText("Code"), "CC2.1");
    await user.type(screen.getByLabelText("Title"), "System change control");
    await user.type(screen.getByLabelText("Description"), "Change control is not in scope.");
    await user.selectOptions(screen.getByLabelText("Applicability"), "not_applicable");
    await user.type(screen.getByLabelText("Applicability rationale"), "Handled by parent entity.");
    fireEvent.change(screen.getByLabelText("Tags (comma separated, max 50)"), {
      target: { value: "change, audit, change, evidence" },
    });
    await user.click(screen.getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toMatchObject({
      framework_id: "framework-1",
      code: "CC2.1",
      title: "System change control",
      description: "Change control is not in scope.",
      applicability: "not_applicable",
      applicability_rationale: "Handled by parent entity.",
      tags: ["change", "audit", "evidence"],
    });
  });

  it("keeps draft activation disabled when configuration preview fails and retries the preview", async () => {
    const user = userEvent.setup();
    const preview = vi
      .spyOn(complianceService.configuration, "preview")
      .mockRejectedValueOnce(new Error("preview failed"))
      .mockResolvedValueOnce({
        revision_id: "configuration-1",
        environment: "staging",
        affected: { frameworks: 0, policies: 0, evidence: 0 },
        diff: [],
      });
    vi.spyOn(complianceService.configuration, "get").mockResolvedValue({
      ...configurationRevision,
      status: "draft",
    });
    const activate = vi.spyOn(complianceService.configuration, "activate");

    renderPage(
      <Routes>
        <Route path="/configuration/:id" element={<ConfigurationDetailPage />} />
      </Routes>,
      "/configuration/configuration-1"
    );

    expect(await screen.findByText("staging configuration v2")).toBeVisible();
    expect(screen.getByRole("button", { name: "Activate" })).toBeDisabled();
    expect(screen.getByText("preview failed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No effective changes.")).toBeVisible();
    expect(activate).not.toHaveBeenCalled();
  });

  it("activates draft frameworks through governed transition keys and refetches readiness", async () => {
    const user = userEvent.setup();
    const get = vi.spyOn(complianceService.frameworks, "get").mockResolvedValue({
      ...framework,
      status: "draft",
      allowed_actions: ["update", "activate"],
    });
    vi.spyOn(complianceService.frameworks, "status").mockResolvedValue({
      framework,
      readiness: {
        framework_id: "framework-1",
        score: 50,
        earned_points: 1,
        possible_points: 2,
        formula: "earned / possible",
        requirements: [
          { requirement_id: "requirement-1", code: "CC1.1", status: "partial", points: 1 },
        ],
      },
      gaps: { framework_id: "framework-1", total: 2, gap_count: 1, gaps: [] },
    });
    const activate = vi.spyOn(complianceService.frameworks, "activate").mockResolvedValue({
      ...framework,
      status: "active",
    });

    renderPage(
      <Routes>
        <Route path="/frameworks/:id" element={<FrameworkDetailPage />} />
      </Routes>,
      "/frameworks/framework-1"
    );

    expect(await screen.findByRole("button", { name: "Activate" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Activate" }));

    await waitFor(() => expect(activate).toHaveBeenCalled());
    expect(activate.mock.calls[0]?.[0]).toBe("framework-1");
    expect(activate.mock.calls[0]?.[1].transition_key).toMatch(
      /^compliance-ui:activate-framework:/
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("updates existing configuration drafts from the loaded document instead of default values", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.configuration, "get").mockResolvedValue({
      ...configurationRevision,
      environment: "production",
      document: {
        ...configurationDocument,
        policy_code_prefix: "CMP",
        default_review_frequency_days: 90,
        rollout: {
          frameworks: { enabled: true, roles: ["compliance_admin"], cohorts: ["enterprise"] },
        },
      },
    });
    const update = vi
      .spyOn(complianceService.configuration, "update")
      .mockResolvedValue(configurationRevision);

    renderPage(
      <Routes>
        <Route path="/configuration/:id/edit" element={<EditConfigurationPage />} />
        <Route
          path="/compliance-management/configuration/:id"
          element={<div>Saved revision</div>}
        />
      </Routes>,
      "/configuration/configuration-1/edit"
    );

    expect(await screen.findByDisplayValue("CMP")).toBeVisible();
    await user.clear(screen.getByLabelText("Bulk import row limit"));
    await user.type(screen.getByLabelText("Bulk import row limit"), "750");
    fireEvent.change(screen.getByLabelText("Rollout cohorts"), {
      target: { value: "enterprise, pilot" },
    });
    await user.click(screen.getByRole("button", { name: "Save draft revision" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update.mock.calls[0]?.[0]).toBe("configuration-1");
    expect(update.mock.calls[0]?.[1]).toMatchObject({
      environment: "production",
      document: {
        policy_code_prefix: "CMP",
        default_review_frequency_days: 90,
        bulk_import_row_limit: 750,
        rollout: {
          frameworks: {
            enabled: true,
            roles: ["compliance_admin"],
            cohorts: ["enterprise", "pilot"],
          },
        },
      },
    });
  });

  it("surfaces retryable framework list failures before restoring governed rows", async () => {
    const user = userEvent.setup();
    const list = vi
      .spyOn(complianceService.frameworks, "list")
      .mockRejectedValueOnce(new Error("frameworks unavailable"))
      .mockResolvedValueOnce(page([framework]));

    renderPage(<FrameworkListPage />);

    expect(await screen.findByText("frameworks unavailable")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("link", { name: "SOC 2" })).toBeVisible();
  });

  it("preserves governed policy ownership on edit and blocks invalid review windows locally", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.policies, "get").mockResolvedValue(policy);
    const update = vi.spyOn(complianceService.policies, "update").mockResolvedValue({
      ...policy,
      title: "Vendor compliance policy updated",
    });

    renderPage(
      <Routes>
        <Route path="/policies/:id/edit" element={<EditCompliancePolicyPage />} />
      </Routes>,
      "/policies/policy-1/edit"
    );

    expect(await screen.findByText("Edit policy")).toBeVisible();
    expect(screen.getByLabelText("Owner ID")).toHaveValue("owner-1");
    await user.clear(screen.getByLabelText("Expiry date"));
    await user.type(screen.getByLabelText("Expiry date"), "2025-12-31");
    await user.click(screen.getByRole("button", { name: "Save policy" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Expiry date must be later than effective date."
    );
    expect(update).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Vendor compliance policy updated");
    await user.clear(screen.getByLabelText("Expiry date"));
    await user.type(screen.getByLabelText("Expiry date"), "2027-12-31");
    await user.click(screen.getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update).toHaveBeenCalledWith(
      "policy-1",
      expect.objectContaining({
        code: "POL-001",
        title: "Vendor compliance policy updated",
        owner_id: "owner-1",
        effective_date: "2026-01-01",
        expiry_date: "2027-12-31",
      })
    );
  });

  it("activates draft configuration only after successful preview with audited transition payload", async () => {
    const user = userEvent.setup();
    const get = vi.spyOn(complianceService.configuration, "get").mockResolvedValue({
      ...configurationRevision,
      status: "draft",
    });
    vi.spyOn(complianceService.configuration, "preview").mockResolvedValue({
      revision_id: "configuration-1",
      environment: "staging",
      affected: { frameworks: 1, policies: 2, evidence: 3 },
      diff: [{ field: "policy_code_prefix", before: "POL", after: "CMP" }],
    });
    const activate = vi
      .spyOn(complianceService.configuration, "activate")
      .mockResolvedValue({ ...configurationRevision, status: "active" });

    renderPage(
      <Routes>
        <Route path="/configuration/:id" element={<ConfigurationDetailPage />} />
      </Routes>,
      "/configuration/configuration-1"
    );

    expect(await screen.findByText("staging configuration v2")).toBeVisible();
    expect(screen.getByText("policy_code_prefix")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Activate" }));

    await waitFor(() => expect(activate).toHaveBeenCalled());
    expect(activate.mock.calls[0]?.[0]).toBe("configuration-1");
    expect(activate.mock.calls[0]?.[1].transition_key).toMatch(
      /^compliance-ui:configuration-activate:/
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("edits framework metadata and reports retryable edit-load failures", async () => {
    const user = userEvent.setup();
    const get = vi
      .spyOn(complianceService.frameworks, "get")
      .mockRejectedValueOnce(new Error("framework load failed"))
      .mockResolvedValue(framework);
    const update = vi
      .spyOn(complianceService.frameworks, "update")
      .mockResolvedValue({ ...framework, name: "SOC 2 Trust Services" });

    renderPage(
      <Routes>
        <Route path="/frameworks/:id/edit" element={<EditFrameworkPage />} />
      </Routes>,
      "/frameworks/framework-1/edit"
    );

    expect(await screen.findByText("framework load failed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(await screen.findByDisplayValue("SOC 2")).toBeVisible();
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "SOC 2 Trust Services");
    await user.click(screen.getByRole("button", { name: "Save framework" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update).toHaveBeenCalledWith(
      "framework-1",
      expect.objectContaining({
        code: "SOC2",
        name: "SOC 2 Trust Services",
        source_kind: "custom",
      })
    );
  });

  it("renders requirement detail populated mappings, evidence, and unassessed branches", async () => {
    vi.spyOn(complianceService.requirements, "get").mockResolvedValue({
      ...requirement,
      allowed_actions: [],
      mapping_count: 1,
      evidence_count: 1,
      gap_status: "mapped",
    });
    vi.spyOn(complianceService.assessments, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService.mappings, "list").mockResolvedValue(page([mapping]));
    vi.spyOn(complianceService.evidence, "list").mockResolvedValue(page([evidence]));

    renderPage(
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetailPage />} />
      </Routes>,
      "/requirements/requirement-1"
    );

    expect(await screen.findByText("Governance responsibilities")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.getByText("Unassessed")).toBeVisible();
    expect(screen.getByText("POL-001 · full")).toBeVisible();
    expect(screen.getByRole("link", { name: "SOC report" })).toBeVisible();
  });

  it("updates existing requirements from immutable loaded fields", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.requirements, "get").mockResolvedValue(requirement);
    const update = vi
      .spyOn(complianceService.requirements, "update")
      .mockResolvedValue({ ...requirement, title: "Updated governance responsibility" });

    renderPage(
      <Routes>
        <Route path="/requirements/:id/edit" element={<EditRequirementPage />} />
      </Routes>,
      "/requirements/requirement-1/edit"
    );

    expect(await screen.findByDisplayValue("CC1.1")).toBeVisible();
    expect(screen.getByLabelText("Framework UUID")).toBeDisabled();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Updated governance responsibility");
    await user.clear(screen.getByLabelText("Sort order"));
    await user.type(screen.getByLabelText("Sort order"), "7");
    await user.click(screen.getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    expect(update).toHaveBeenCalledWith(
      "requirement-1",
      expect.objectContaining({
        framework_id: "framework-1",
        code: "CC1.1",
        title: "Updated governance responsibility",
        sort_order: 7,
      })
    );
  });

  it("renders non-draft policy history, mappings, activity, and request-change transition", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.policies, "get").mockResolvedValue({
      ...policy,
      status: "in_review",
      allowed_actions: ["request-changes", "approve"],
      mapping_count: 1,
    });
    vi.spyOn(complianceService.policies, "versions").mockResolvedValue(page([policyVersion]));
    vi.spyOn(complianceService.mappings, "list").mockResolvedValue(page([mapping]));
    vi.spyOn(complianceService, "activity").mockResolvedValue(page([activityEntry]));
    const transition = vi
      .spyOn(complianceService.policies, "transition")
      .mockResolvedValue({ ...policy, status: "draft" });

    renderPage(
      <Routes>
        <Route path="/policies/:id" element={<CompliancePolicyDetailPage />} />
      </Routes>,
      "/policies/policy-1"
    );

    expect(await screen.findByText("Version 1")).toBeVisible();
    expect(screen.queryByLabelText("Policy content")).not.toBeInTheDocument();
    expect(screen.getByText("CC1.1 · full")).toBeVisible();
    expect(screen.getByText("policy.submit")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "request changes" }));

    await waitFor(() => expect(transition).toHaveBeenCalled());
    expect(transition.mock.calls[0]?.[1]).toBe("request-changes");
    expect(transition.mock.calls[0]?.[2]).toMatchObject({
      reason: "Changes requested by reviewer",
    });
  });

  it("renders empty assessment, configuration, and activity surfaces", async () => {
    const emptyConfigurationPage = page<ComplianceConfigurationRevision>([]);
    vi.spyOn(complianceService.assessments, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService.configuration, "list").mockResolvedValue({
      data: [] as ComplianceConfigurationRevision[],
      meta: emptyConfigurationPage.meta,
    });
    vi.spyOn(complianceService, "activity").mockResolvedValue(page([]));

    const assessments = renderPage(<AssessmentHistoryPage />);
    expect(await screen.findByText("No assessments")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Record assessment" })).toHaveLength(2);
    assessments.unmount();

    const configurations = renderPage(
      <ConfigurationListPage />,
      "/configuration?environment=staging"
    );
    expect(await screen.findByText("No configuration revisions")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create revision" })).toBeEnabled();
    configurations.unmount();

    renderPage(<ComplianceActivityPage />);
    expect(await screen.findByText("No activity")).toBeVisible();
  });
});
