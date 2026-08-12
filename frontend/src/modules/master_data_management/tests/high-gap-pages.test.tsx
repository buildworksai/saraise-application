/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- high-gap page tests assert governed query, mutation, and navigation payloads. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  AsyncJob,
  DataQualityIssue,
  DataQualityRule,
  MasterDataConfiguration,
  MasterDataConfigurationDocument,
  MasterDataEntity,
  MasterDataEntityListItem,
  MasterDataVersion,
  MasterEntityType,
  MatchCandidate,
  MatchingRule,
  MergeHistoryListItem,
  MergeHistory,
  MergePreview,
  MDMSummary,
  PaginationMeta,
  RulePortableDocument,
  RuleVersion,
} from "../contracts";
import { ROUTES } from "../contracts";
import { RuleGovernancePanel } from "../components/RuleGovernancePanel";
import { EntityTypeDetailPage } from "../pages/EntityTypeDetailPage";
import { EntityTypeListPage } from "../pages/EntityTypeListPage";
import { EntityVersionPage } from "../pages/EntityVersionPage";
import { AsyncJobDetailPage } from "../pages/AsyncJobDetailPage";
import { MatchingRuleDetailPage } from "../pages/MatchingRuleDetailPage";
import { MasterDataDashboardPage } from "../pages/MasterDataDashboardPage";
import { MasterDataEntityDetailPage } from "../pages/MasterDataEntityDetailPage";
import { MasterDataEntityListPage } from "../pages/MasterDataEntityListPage";
import { MatchCandidateListPage } from "../pages/MatchCandidateListPage";
import { MatchCandidateDetailPage } from "../pages/MatchCandidateDetailPage";
import { MergeHistoryDetailPage } from "../pages/MergeHistoryDetailPage";
import { MergeHistoryListPage } from "../pages/MergeHistoryListPage";
import { QualityRuleDetailPage } from "../pages/QualityRuleDetailPage";
import { QualityRuleListPage } from "../pages/QualityRuleListPage";
import { QualityIssueDetailPage } from "../pages/QualityIssueDetailPage";
import { QualityIssueListPage } from "../pages/QualityIssueListPage";
import { masterDataService } from "../services/master-data-service";

const service = vi.hoisted(() => ({
  configuration: { current: vi.fn() },
  dashboard: { get: vi.fn() },
  entityTypes: { list: vi.fn(), get: vi.fn(), deactivate: vi.fn() },
  entities: {
    list: vi.fn(),
    get: vi.fn(),
    version: vi.fn(),
    rollback: vi.fn(),
    versions: vi.fn(),
    validate: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
  },
  qualityRules: {
    list: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    history: vi.fn(),
    rollback: vi.fn(),
    importDocument: vi.fn(),
    exportDocument: vi.fn(),
  },
  qualityIssues: {
    list: vi.fn(),
    get: vi.fn(),
    assign: vi.fn(),
    resolve: vi.fn(),
    waive: vi.fn(),
  },
  matchingRules: {
    list: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    history: vi.fn(),
    rollback: vi.fn(),
    importDocument: vi.fn(),
    exportDocument: vi.fn(),
  },
  matching: { scan: vi.fn() },
  matchCandidates: { list: vi.fn(), get: vi.fn(), review: vi.fn() },
  merges: {
    list: vi.fn(),
    get: vi.fn(),
    preview: vi.fn(),
    create: vi.fn(),
    reversalPreview: vi.fn(),
    reverse: vi.fn(),
  },
  qualityScans: { create: vi.fn() },
  jobs: { get: vi.fn() },
}));

vi.mock("../services/master-data-service", () => ({ masterDataService: service }));

const stamp = "2026-07-31T00:00:00Z";
const pagination: PaginationMeta = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 2,
  has_next: true,
  has_previous: false,
};

const documentFixture: MasterDataConfigurationDocument = {
  environment: "development",
  schema_policy: {
    entity_type_key_pattern: "^[a-z][a-z0-9_]*$",
    entity_type_key_max_length: 64,
    field_path_pattern: "^[a-z][a-z0-9_.]*$",
    allowed_json_schema_keywords: ["type", "properties"],
    max_payload_bytes: 2048,
    builtin_entity_types: [],
  },
  lifecycle: { allow_physical_delete: false, merged_entities_editable: false },
  workflows: { entity: {}, quality_issue: {}, match_candidate: {}, merge: {} },
  limits: {
    display_name_max: 120,
    description_max: 500,
    owner_module_max: 80,
    entity_code_max: 80,
    entity_name_max: 160,
    source_system_max: 80,
    source_record_id_max: 120,
    resolution_max: 500,
    reason_max: 500,
    deduplication_scan_max_entities: 1000,
    merge_min_entities: 2,
    list_page_size: 25,
    selector_page_size: 100,
  },
  quality: {
    missing_values: ["", null],
    rule_schemas: {},
    referential_target_field_default: "id",
    timeliness_max_age_days_default: 30,
    no_rules_evaluated: true,
    no_rules_score: null,
    no_rules_issue_count: 0,
    score_scale: 100,
    score_decimal_places: 2,
    auto_resolve_passing: true,
    defaults: {
      rule_type: "required",
      dimension: "completeness",
      severity: "warning",
      weight: "1.0",
    },
  },
  matching: {
    algorithms: ["exact", "fuzzy"],
    soundex_mapping: {},
    soundex_output_length: 4,
    weight_sum: "1.0",
    weight_tolerance: "0.01",
    threshold_min: "0.00",
    threshold_max: "1.00",
    missing_value_score: "0.00",
    outcomes: { auto_confirm: "confirmed", review: "pending", no_match: "rejected" },
    strategy_version: 1,
    scan_statuses: ["active"],
    skip_incomplete_blocking_keys: true,
    auto_confirm_enabled: true,
    review_decisions: ["confirm", "reject"],
    defaults: { algorithm: "exact", review_threshold: "0.80", auto_confirm_threshold: "0.95" },
  },
  merge: {
    allowed_statuses: ["active"],
    survivorship_order: ["updated_at"],
    reversal_expected_version_increment: 1,
  },
  dashboard: {
    score_buckets: [{ label: "healthy", minimum: 90, maximum: 100 }],
    trend_window_days: 30,
    recent_activity_limit: 5,
    minimum_bar_percent: 5,
  },
  operational: {
    health_check_interval_seconds: 60,
    job_poll_interval_ms: 2000,
    job_poll_statuses: ["queued", "running", "retrying"],
  },
  ui: {
    sidebar_order: 10,
    skeleton_cards: 4,
    quality_issue_default_status: "open",
    status_tokens: { danger: "destructive", success: "success", warning: "warning" },
    list_page_size: 25,
  },
  entity_defaults: { source_system: "ERP" },
  feature_rollout: {
    enabled: true,
    modes: ["development"],
    roles: ["data-steward"],
    cohorts: ["pilot"],
    percentage: 100,
  },
};

const configuration: MasterDataConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  document: documentFixture,
  version: 3,
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
};

const typeCustomer: MasterEntityType = {
  id: "type-1",
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  is_deleted: false,
  deleted_at: null,
  key: "customer",
  display_name: "Customer",
  description: "Customer records",
  json_schema: { type: "object", properties: { email: { type: "string" } } },
  schema_version: 2,
  required_fields: ["email"],
  sensitive_fields: [],
  searchable_fields: ["email"],
  owner_module: "crm",
  is_system: false,
  is_active: true,
  metadata: {},
};

function entity(overrides: Partial<MasterDataEntity> = {}): MasterDataEntity {
  return {
    id: "entity-1",
    tenant_id: "tenant-1",
    created_at: stamp,
    updated_at: stamp,
    created_by: "user-1",
    updated_by: "user-1",
    is_deleted: false,
    deleted_at: null,
    entity_type: "type-1",
    entity_type_key: "customer",
    entity_type_display_name: "Customer",
    entity_code: "CUST-1",
    entity_name: "Acme",
    source_system: "ERP",
    source_record_id: "erp-1",
    status: "active",
    quality_score: "97.50",
    quality_evaluated_at: stamp,
    golden_record: null,
    is_golden: true,
    version: 4,
    data: { email: "ops@example.test", phone: "555-0100" },
    quality_summary: {
      evaluated: true,
      score: 97.5,
      evaluated_at: stamp,
      dimensions: [
        {
          dimension: "completeness",
          score: 0.975,
          passed_rules: 3,
          failed_rules: 0,
          evaluated_rules: 3,
        },
      ],
      open_issue_count: 2,
    },
    transition_history: [],
    ...overrides,
  };
}

const version: MasterDataVersion = {
  id: "version-4",
  tenant_id: "tenant-1",
  entity: "entity-1",
  version_number: 4,
  entity_type_key: "customer",
  entity_code: "CUST-1",
  entity_name: "Acme",
  data_snapshot: { email: "ops@example.test" },
  status_snapshot: "active",
  quality_score_snapshot: "97.50",
  changed_fields: ["data.email"],
  change_reason: "Correction",
  changed_by: "user-1",
  correlation_id: "corr-version-4",
  created_at: stamp,
};

const issueFixture: DataQualityIssue = {
  id: "issue-1",
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  entity: "entity-1",
  entity_code: "CUST-1",
  entity_name: "Acme",
  rule: "quality-rule-1",
  rule_name: "Email required",
  field_path: "email",
  dimension: "completeness",
  severity: "critical",
  message: "Email is required",
  evidence: { missing: true, source: "quality-scan" },
  status: "open",
  assigned_to: null,
  resolution: "",
  resolved_by: null,
  resolved_at: null,
  transition_history: [],
};

const matchingRuleFixture: MatchingRule = {
  id: "matching-rule-1",
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  is_deleted: false,
  deleted_at: null,
  entity_type: "type-1",
  entity_type_key: "customer",
  name: "Email exact",
  algorithm: "exact",
  field_weights: { email: 1 },
  blocking_fields: ["email"],
  review_threshold: "0.80",
  auto_confirm_threshold: "0.95",
  is_active: true,
};

const qualityRuleFixture: DataQualityRule = {
  id: "quality-rule-1",
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  is_deleted: false,
  deleted_at: null,
  entity_type: "type-1",
  entity_type_key: "customer",
  name: "Email required",
  field_path: "email",
  rule_type: "required",
  configuration: { trim: true, min_length: 1 },
  dimension: "completeness",
  severity: "critical",
  weight: "1.0",
  is_active: true,
};

const ruleVersionFixture: RuleVersion = {
  id: "rule-version-1",
  tenant_id: "tenant-1",
  rule: "quality-rule-1",
  version_number: 2,
  snapshot: { name: "Email required", field_path: "email" },
  changed_by: "user-1",
  correlation_id: "corr-rule-version",
  change_reason: "Tighten required email governance",
  created_at: stamp,
};

const portableRuleFixture: RulePortableDocument = {
  schema: "saraise.master-data-management.quality-rule",
  document_version: 1,
  rule_id: "quality-rule-1",
  version_number: 2,
  snapshot: { name: "Email required", field_path: "email" },
};

const summary: MDMSummary = {
  total_entities: 10,
  active_entities: 7,
  pending_review_entities: 1,
  merged_entities: 1,
  archived_entities: 1,
  quality_evaluated_entities: 8,
  average_quality_score: 94.5,
  score_distribution: [{ label: "healthy", minimum: 90, maximum: 100, count: 1 }],
  quality_trend: [],
  open_issues: 2,
  critical_issues: 1,
  pending_matches: 3,
  recent_activity: [
    {
      event: "entity.validated",
      aggregate_id: "entity-1",
      label: "Acme validated",
      occurred_at: stamp,
      actor_id: "user-1",
      correlation_id: "corr-activity",
    },
  ],
};

function item<T>(data: T) {
  return { data, meta: { correlation_id: "corr-mdm", timestamp: stamp } };
}

function list<T>(items: readonly T[], overrides: Partial<PaginationMeta> = {}) {
  return {
    items,
    pagination: { ...pagination, count: items.length, ...overrides },
    meta: { correlation_id: "corr-mdm-list", timestamp: stamp },
  };
}

function renderRoute(ui: React.ReactElement, path: string, entry = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/master-data/entities/new" element={<LocationProbe />} />
          <Route path="/master-data/entities/:id" element={<LocationProbe />} />
          <Route path="/master-data/entity-types/new" element={<LocationProbe />} />
          <Route path="/master-data/entity-types/:id" element={<LocationProbe />} />
          <Route path="/master-data/entity-types/:id/edit" element={<LocationProbe />} />
          <Route path="/master-data/quality/issues/:id" element={<LocationProbe />} />
          <Route path="/master-data/quality/issues" element={<LocationProbe />} />
          <Route path="/master-data/quality/rules/new" element={<LocationProbe />} />
          <Route path="/master-data/quality/rules/:id" element={<LocationProbe />} />
          <Route path="/master-data/quality/rules" element={<LocationProbe />} />
          <Route path="/master-data/matching/rules" element={<LocationProbe />} />
          <Route path="/master-data/merges/:id" element={<LocationProbe />} />
          <Route path="/master-data/jobs/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

describe("Master Data high-gap pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    let key = 0;
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `mdm-key-${(key += 1)}`) });
    service.configuration.current.mockResolvedValue(item(configuration));
    service.dashboard.get.mockResolvedValue(item(summary));
    service.entityTypes.list.mockResolvedValue(list([typeCustomer]));
    service.entityTypes.get.mockResolvedValue(item(typeCustomer));
    service.entityTypes.deactivate.mockResolvedValue(item({ ...typeCustomer, is_active: false }));
    service.entities.list.mockResolvedValue(list<MasterDataEntityListItem>([entity()]));
    service.entities.get.mockResolvedValue(item(entity()));
    service.entities.version.mockResolvedValue(item(version));
    service.entities.rollback.mockResolvedValue(
      item(entity({ version: 5, data: version.data_snapshot }))
    );
    service.entities.versions.mockResolvedValue(list([version]));
    service.entities.validate.mockResolvedValue(
      item({
        entity_id: "entity-1",
        evaluated: true,
        score: "98.00",
        dimension_scores: { completeness: 1 },
        issue_count: 0,
        findings: [],
      })
    );
    service.entities.archive.mockResolvedValue(undefined);
    service.entities.restore.mockResolvedValue(item(entity({ status: "active" })));
    service.qualityIssues.list.mockResolvedValue(list([issueFixture]));
    service.qualityIssues.get.mockResolvedValue(item(issueFixture));
    service.qualityIssues.assign.mockResolvedValue(
      item({ ...issueFixture, assigned_to: "actor-1", status: "in_review" })
    );
    service.qualityIssues.resolve.mockResolvedValue(
      item({ ...issueFixture, status: "resolved", resolution: "Backfilled email" })
    );
    service.qualityIssues.waive.mockResolvedValue(
      item({ ...issueFixture, status: "waived", resolution: "Approved exception" })
    );
    service.qualityRules.list.mockResolvedValue(list([qualityRuleFixture]));
    service.matchingRules.list.mockResolvedValue(list([matchingRuleFixture]));
    service.matchingRules.get.mockResolvedValue(item(matchingRuleFixture));
    service.matchingRules.delete.mockResolvedValue(undefined);
    service.qualityRules.get.mockResolvedValue(item(qualityRuleFixture));
    service.qualityRules.delete.mockResolvedValue(undefined);
    service.matchingRules.history.mockResolvedValue(list([ruleVersionFixture]));
    service.qualityRules.history.mockResolvedValue(list([ruleVersionFixture]));
    service.qualityRules.rollback.mockResolvedValue(item({ id: "quality-rule-1" }));
    service.qualityRules.importDocument.mockResolvedValue(item({ id: "quality-rule-1" }));
    service.qualityRules.exportDocument.mockResolvedValue(item(portableRuleFixture));
    service.matching.scan.mockResolvedValue(
      item<AsyncJob>({
        id: "job-match-1",
        command: "master_data_management.deduplication_scan",
        status: "queued",
        attempts: 0,
        created_at: stamp,
        updated_at: stamp,
        started_at: null,
        completed_at: null,
        error_message: null,
        correlation_id: "corr-match-job",
        result: null,
      })
    );
    service.qualityScans.create.mockResolvedValue(
      item<AsyncJob>({
        id: "job-1",
        command: "master_data_management.quality_scan",
        status: "queued",
        attempts: 0,
        created_at: stamp,
        updated_at: stamp,
        started_at: null,
        completed_at: null,
        error_message: null,
        correlation_id: "corr-job",
        result: null,
      })
    );
    service.merges.list.mockResolvedValue(
      list<MergeHistoryListItem>([
        {
          id: "merge-list-1",
          tenant_id: "tenant-1",
          golden_record: "entity-1",
          golden_record_name: "Acme",
          status: "applied",
          reason: "Confirmed duplicate",
          merged_by: "user-1",
          reversed_by: null,
          reversed_at: null,
          participant_count: 2,
          correlation_id: "corr-merge-list",
          created_at: stamp,
        },
      ])
    );
    service.jobs.get.mockResolvedValue(
      item<AsyncJob>({
        id: "job-1",
        command: "master_data_management.quality_scan",
        status: "failed",
        attempts: 3,
        created_at: stamp,
        updated_at: stamp,
        started_at: stamp,
        completed_at: stamp,
        error_message: "Provider timeout",
        correlation_id: "corr-job-detail",
        result: { failed_entities: 2 },
      })
    );
  });

  it("filters entity lists, saves local views, paginates, and navigates detail/create routes", async () => {
    const user = userEvent.setup();
    renderRoute(
      <MasterDataEntityListPage />,
      ROUTES.ENTITIES,
      `${ROUTES.ENTITIES}?search=Acme&entity_type=type-1&status=active&ordering=entity_name`
    );

    expect(await screen.findByRole("heading", { name: "Master entities" })).toBeInTheDocument();
    await user.click(screen.getByText("Save current view"));
    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() =>
      expect(masterDataService.entities.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "Acme",
          entity_type: "type-1",
          status: "active",
          ordering: "entity_name",
          page: 2,
          page_size: 25,
        })
      )
    );
    expect(screen.getByRole("button", { name: "View 1" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Acme" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/master-data/entities/entity-1");
  });

  it("runs entity validation and archive commands with version and idempotency evidence", async () => {
    const user = userEvent.setup();
    renderRoute(
      <MasterDataEntityDetailPage />,
      "/master-data/entities/:id",
      ROUTES.ENTITY_DETAIL("entity-1")
    );

    expect(await screen.findByRole("heading", { name: "Acme" })).toBeInTheDocument();
    expect(screen.getByText("corr-version-4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evaluate quality" }));
    await waitFor(() =>
      expect(masterDataService.entities.validate).toHaveBeenCalledWith(
        "entity-1",
        "mdm-ui:validate-entity:mdm-key-1"
      )
    );
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Archive entity?" })).getByRole("button", {
        name: "Archive",
      })
    );
    await waitFor(() =>
      expect(masterDataService.entities.archive).toHaveBeenCalledWith("entity-1", {
        expected_version: 4,
        reason: "Archived by steward",
        idempotency_key: "mdm-ui:archive-entity:mdm-key-2",
      })
    );
  });

  it("reviews confirmed candidates, previews survivorship overrides, and applies merge tokens", async () => {
    const user = userEvent.setup();
    const candidate: MatchCandidate = {
      ...entity(),
      id: "candidate-1",
      matching_rule: "rule-1",
      matching_rule_name: "Email exact",
      left_entity: entity({
        id: "entity-left",
        entity_name: "Acme Left",
        data: { email: "a@test" },
      }),
      right_entity: entity({
        id: "entity-right",
        entity_name: "Acme Right",
        data: { email: "b@test" },
      }),
      confidence: "0.982",
      field_scores: { email: 0.98 },
      evidence: { algorithm: "exact" },
      status: "confirmed",
      reviewed_by: "user-1",
      reviewed_at: stamp,
      review_note: "duplicate",
      merge_history: null,
      transition_history: [],
    };
    const preview: MergePreview = {
      entity_ids: ["entity-left", "entity-right"],
      entity_type_key: "customer",
      fields: [
        {
          field_path: "email",
          value: "b@test",
          source_entity_id: "entity-right",
          source_entity_name: "Acme Right",
          rationale: "Steward override",
          alternatives: [],
        },
      ],
      golden_record: { email: "b@test" },
      conflicts: [],
      preview_token: "preview-token-1",
    };
    service.matchCandidates.get.mockResolvedValue(item(candidate));
    service.matchCandidates.review.mockResolvedValue(item({ ...candidate, status: "rejected" }));
    service.merges.preview.mockResolvedValue(item(preview));
    service.merges.create.mockResolvedValue(item({ id: "merge-1" }));
    renderRoute(
      <MatchCandidateDetailPage />,
      "/master-data/matches/:id",
      ROUTES.MATCH_DETAIL("candidate-1")
    );

    expect(
      await screen.findByRole("heading", { name: "Duplicate comparison" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Survivor for email"), "entity-right");
    await user.type(screen.getByLabelText("Review note"), "Use newer CRM email");
    await user.click(screen.getByRole("button", { name: "Preview survivorship" }));
    await waitFor(() =>
      expect(masterDataService.merges.preview).toHaveBeenCalledWith({
        entity_ids: ["entity-left", "entity-right"],
        survivorship_overrides: { email: "entity-right" },
      })
    );
    await user.click(await screen.findByRole("button", { name: "Apply merge" }));
    await waitFor(() =>
      expect(masterDataService.merges.create).toHaveBeenCalledWith({
        entity_ids: ["entity-left", "entity-right"],
        survivorship_overrides: { email: "entity-right" },
        reason: "Use newer CRM email",
        idempotency_key: "mdm-ui:candidate-merge:mdm-key-1",
        preview_token: "preview-token-1",
      })
    );
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/master-data/merges/merge-1")
    );
  });

  it("filters entity types and deactivates tenant-owned schemas with governed evidence", async () => {
    const user = userEvent.setup();
    renderRoute(
      <EntityTypeListPage />,
      ROUTES.ENTITY_TYPES,
      `${ROUTES.ENTITY_TYPES}?search=Cust&is_active=true`
    );

    expect(await screen.findByRole("heading", { name: "Entity types" })).toBeInTheDocument();
    expect(masterDataService.entityTypes.list).toHaveBeenCalledWith(
      expect.objectContaining({
        search: "Cust",
        is_active: true,
        ordering: "key",
        page: 1,
        page_size: 25,
      })
    );
    await user.click(screen.getByRole("link", { name: /Customer/u }));
    expect(screen.getByTestId("location")).toHaveTextContent("/master-data/entity-types/type-1");

    renderRoute(
      <EntityTypeDetailPage />,
      "/master-data/entity-types/:id",
      ROUTES.ENTITY_TYPE_DETAIL("type-1")
    );
    expect(await screen.findByRole("heading", { name: "Customer" })).toBeInTheDocument();
    expect(screen.getAllByText("email").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Deactivate entity type?" })).getByRole("button", {
        name: "Deactivate",
      })
    );
    await waitFor(() =>
      expect(masterDataService.entityTypes.deactivate).toHaveBeenCalledWith("type-1", {
        reason: "Deactivated by steward",
        idempotency_key: "mdm-ui:deactivate-type:mdm-key-1",
      })
    );
  });

  it("handles quality issue list filters plus assign, resolve, and waive transitions", async () => {
    const user = userEvent.setup();
    renderRoute(
      <QualityIssueListPage />,
      ROUTES.QUALITY_ISSUES,
      `${ROUTES.QUALITY_ISSUES}?severity=critical`
    );

    expect(await screen.findByRole("heading", { name: "Quality issue queue" })).toBeInTheDocument();
    expect(masterDataService.qualityIssues.list).toHaveBeenCalledWith(
      expect.objectContaining({
        status: "open",
        severity: "critical",
        page: 1,
        page_size: 25,
      })
    );
    await user.selectOptions(screen.getByLabelText("Filter issue status"), "in_review");
    await waitFor(() =>
      expect(masterDataService.qualityIssues.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "in_review", severity: "critical" })
      )
    );

    renderRoute(
      <QualityIssueDetailPage />,
      "/master-data/quality/issues/:id",
      ROUTES.QUALITY_ISSUE_DETAIL("issue-1")
    );
    expect(await screen.findByRole("heading", { name: "Quality issue" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Assignee actor UUID"), "actor-1");
    await user.click(screen.getByRole("button", { name: "Assign issue" }));
    await waitFor(() =>
      expect(masterDataService.qualityIssues.assign).toHaveBeenCalledWith("issue-1", {
        assignee_id: "actor-1",
        transition_key: "mdm-ui:issue-assign:mdm-key-1",
      })
    );

    await user.type(screen.getByLabelText("Resolution evidence"), "Backfilled email");
    await user.click(screen.getByRole("button", { name: "Resolve" }));
    await waitFor(() =>
      expect(masterDataService.qualityIssues.resolve).toHaveBeenCalledWith("issue-1", {
        resolution: "Backfilled email",
        transition_key: "mdm-ui:issue-resolve:mdm-key-2",
      })
    );
    await user.clear(screen.getByLabelText("Resolution evidence"));
    await user.type(screen.getByLabelText("Resolution evidence"), "Approved exception");
    await user.click(screen.getByRole("button", { name: "Waive" }));
    await waitFor(() =>
      expect(masterDataService.qualityIssues.waive).toHaveBeenCalledWith("issue-1", {
        resolution: "Approved exception",
        transition_key: "mdm-ui:issue-waive:mdm-key-3",
      })
    );
  });

  it("runs duplicate scans from active matching rules and preserves empty/error guardrails", async () => {
    const user = userEvent.setup();
    const candidate: MatchCandidate = {
      ...entity(),
      id: "candidate-list-1",
      matching_rule: "matching-rule-1",
      matching_rule_name: "Email exact",
      left_entity: entity({ id: "entity-left", entity_name: "Acme Left", entity_code: "LEFT" }),
      right_entity: entity({ id: "entity-right", entity_name: "Acme Right", entity_code: "RIGHT" }),
      confidence: "0.912",
      field_scores: { email: 0.912 },
      evidence: { algorithm: "exact" },
      status: "pending",
      reviewed_by: null,
      reviewed_at: null,
      review_note: "",
      merge_history: null,
      transition_history: [],
    };
    service.matchCandidates.list.mockResolvedValue(list([candidate]));
    renderRoute(<MatchCandidateListPage />, ROUTES.MATCHES);

    expect(await screen.findByRole("heading", { name: "Duplicate review" })).toBeInTheDocument();
    expect(screen.getByText("91.2% match")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run duplicate scan" }));
    await waitFor(() =>
      expect(masterDataService.matching.scan).toHaveBeenCalledWith({
        entity_type_id: "type-1",
        rule_ids: ["matching-rule-1"],
        idempotency_key: "mdm-ui:deduplication-scan:mdm-key-1",
      })
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/master-data/jobs/job-match-1");

    service.matchingRules.list.mockResolvedValueOnce(list([]));
    service.matchCandidates.list.mockResolvedValueOnce(list([]));
    renderRoute(<MatchCandidateListPage />, ROUTES.MATCHES);
    expect(await screen.findByText("No candidates in this queue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run duplicate scan" })).toBeDisabled();
  });

  it("rolls back entity versions and reverses merges only after authoritative previews", async () => {
    const user = userEvent.setup();
    service.entities.version.mockResolvedValueOnce(
      item({
        ...version,
        version_number: 3,
        data_snapshot: { email: "old@example.test" },
        change_reason: "Previous email",
      })
    );
    renderRoute(
      <EntityVersionPage />,
      "/master-data/entities/:id/versions/:version",
      ROUTES.ENTITY_VERSION("entity-1", 3)
    );

    expect(await screen.findByRole("heading", { name: "Version 3" })).toBeInTheDocument();
    expect(screen.getByText("corr-version-4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rollback to this version" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Create rollback version?" })).getByRole("button", {
        name: "Rollback to this version",
      })
    );
    await waitFor(() =>
      expect(masterDataService.entities.rollback).toHaveBeenCalledWith("entity-1", {
        version_number: 3,
        expected_version: 4,
        reason: "Rollback to version 3",
        idempotency_key: "mdm-ui:entity-rollback:mdm-key-1",
      })
    );

    const merge: MergeHistory = {
      id: "merge-1",
      tenant_id: "tenant-1",
      golden_record: "entity-left",
      golden_record_name: "Acme Left",
      status: "applied",
      reason: "Confirmed duplicate",
      merged_by: "user-1",
      reversed_by: null,
      reversed_at: null,
      participant_count: 2,
      correlation_id: "corr-merge-1",
      created_at: stamp,
      survivorship_policy: { email: "entity-left" },
      golden_snapshot_before: { email: "old@test" },
      golden_snapshot_after: { email: "new@test" },
      reversal_reason: "",
      transition_history: [],
      participants: [
        {
          id: "participant-1",
          source_entity: "entity-left",
          source_version: 4,
          source_snapshot: { email: "new@test" },
          role: "survivor",
          created_at: stamp,
        },
      ],
    };
    service.merges.get.mockResolvedValue(item(merge));
    service.merges.reversalPreview.mockResolvedValue(
      item({
        merge_id: "merge-1",
        can_reverse: true,
        conflicts: [],
        participant_versions: { "entity-left": 4 },
      })
    );
    service.merges.reverse.mockResolvedValue(item({ ...merge, status: "reversed" }));
    renderRoute(
      <MergeHistoryDetailPage />,
      "/master-data/merges/:id",
      ROUTES.MERGE_DETAIL("merge-1")
    );

    expect(await screen.findByRole("heading", { name: "Merge provenance" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check reversal conflicts" }));
    expect(
      await screen.findByText(/authoritative reversal preview reports no conflicts/u)
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Reversal reason"), "Source record was corrected");
    await user.click(screen.getByRole("button", { name: "Reverse merge" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Reverse this merge?" })).getByRole("button", {
        name: "Reverse merge",
      })
    );
    await waitFor(() =>
      expect(masterDataService.merges.reverse).toHaveBeenCalledWith("merge-1", {
        reason: "Source record was corrected",
        transition_key: "mdm-ui:merge-reversal:mdm-key-2",
      })
    );
  });

  it("exports, imports, and rolls back quality rule governance documents", async () => {
    const user = userEvent.setup();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      const element = originalCreateElement(tagName);
      if (tagName === "a") vi.spyOn(element, "click").mockImplementation(vi.fn());
      return element;
    });
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:quality-rule"),
      revokeObjectURL: vi.fn(),
    });
    renderRoute(<RuleGovernancePanel kind="quality" ruleId="quality-rule-1" />, "/");

    expect(await screen.findByText("Versioning and portability")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(masterDataService.qualityRules.exportDocument).toHaveBeenCalledWith("quality-rule-1")
    );

    await user.type(screen.getByLabelText("Change reason"), "Restore governed quality rule");
    const portableFile = {
      text: vi.fn().mockResolvedValue(JSON.stringify(portableRuleFixture)),
    };
    fireEvent.change(screen.getByLabelText("Choose import"), {
      target: {
        files: [portableFile],
      },
    });
    await user.click(await screen.findByRole("button", { name: "Import selected document" }));
    await waitFor(() =>
      expect(masterDataService.qualityRules.importDocument).toHaveBeenCalledWith("quality-rule-1", {
        document: portableRuleFixture,
        reason: "Restore governed quality rule",
        idempotency_key: "mdm-ui:quality-rule-import:mdm-key-2",
      })
    );

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() =>
      expect(masterDataService.qualityRules.rollback).toHaveBeenCalledWith("quality-rule-1", {
        version_number: 2,
        reason: "Restore governed quality rule",
        idempotency_key: "mdm-ui:quality-rule-rollback:mdm-key-1",
      })
    );
  });

  it("starts configured quality scans and fails closed when dashboard dependencies reject", async () => {
    const user = userEvent.setup();
    renderRoute(<MasterDataDashboardPage />, ROUTES.DASHBOARD);

    expect(
      await screen.findByRole("heading", { name: "Master data stewardship" })
    ).toBeInTheDocument();
    expect(screen.getByText("Acme validated")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Quality scan entity type"), "type-1");
    await user.click(screen.getByRole("button", { name: "Run quality scan" }));
    await waitFor(() =>
      expect(masterDataService.qualityScans.create).toHaveBeenCalledWith({
        entity_type_id: "type-1",
        idempotency_key: "mdm-ui:quality-scan:mdm-key-1",
      })
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/master-data/jobs/job-1");

    service.dashboard.get.mockRejectedValueOnce(
      new ApiError("dashboard unavailable", 503, undefined, "unavailable", "corr-dashboard-503")
    );
    renderRoute(<MasterDataDashboardPage />, ROUTES.DASHBOARD);
    expect(await screen.findByRole("alert")).toHaveTextContent("Capability unavailable");
    expect(screen.getByText(/corr-dashboard-503/u)).toBeInTheDocument();
  });

  it("filters merge history and exposes immutable merge evidence navigation", async () => {
    const user = userEvent.setup();
    renderRoute(<MergeHistoryListPage />, ROUTES.MERGES, `${ROUTES.MERGES}?status=applied`);

    expect(await screen.findByRole("heading", { name: "Merge history" })).toBeInTheDocument();
    expect(masterDataService.merges.list).toHaveBeenCalledWith(
      expect.objectContaining({
        status: "applied",
        page: 1,
        page_size: 25,
        ordering: "-created_at",
      })
    );
    await user.selectOptions(screen.getByLabelText("Filter merge status"), "reversed");
    await waitFor(() =>
      expect(masterDataService.merges.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "reversed", page: 1, ordering: "-created_at" })
      )
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(masterDataService.merges.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "reversed", page: 2 })
      )
    );
    await user.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() =>
      expect(masterDataService.merges.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: undefined, page: 1 })
      )
    );
    await user.click(screen.getByRole("link", { name: /Acme/u }));
    expect(screen.getByTestId("location")).toHaveTextContent("/master-data/merges/merge-list-1");
  });

  it("renders terminal async job evidence and routes to the correct result queue", async () => {
    const user = userEvent.setup();
    renderRoute(<AsyncJobDetailPage />, "/master-data/jobs/:id", ROUTES.JOB_DETAIL("job-1"));

    expect(await screen.findByRole("heading", { name: "Durable scan job" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Provider timeout");
    expect(screen.getByText("corr-job-detail")).toBeInTheDocument();
    expect(screen.getByText(/terminal state/u)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Open results queue" }));
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.QUALITY_ISSUES);
  });

  it("deactivates matching rules with stable idempotency while preserving governance panels", async () => {
    const user = userEvent.setup();
    renderRoute(
      <MatchingRuleDetailPage />,
      "/master-data/matching/rules/:id",
      ROUTES.MATCHING_RULE_DETAIL("matching-rule-1")
    );

    expect(await screen.findByRole("heading", { name: "Email exact" })).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("blocking")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Deactivate matching rule?" })).getByRole(
        "button",
        { name: "Deactivate" }
      )
    );
    await waitFor(() =>
      expect(masterDataService.matchingRules.delete).toHaveBeenCalledWith("matching-rule-1", {
        idempotency_key: "mdm-ui:matching-rule-deactivate:mdm-key-1",
      })
    );
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.MATCHING_RULES);
  });

  it("shows quality rule configuration and deactivates with governed payloads", async () => {
    const user = userEvent.setup();
    renderRoute(
      <QualityRuleDetailPage />,
      "/master-data/quality/rules/:id",
      ROUTES.QUALITY_RULE_DETAIL("quality-rule-1")
    );

    expect(await screen.findByRole("heading", { name: "Email required" })).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.getByText("trim")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Deactivate quality rule?" })).getByRole("button", {
        name: "Deactivate",
      })
    );
    await waitFor(() =>
      expect(masterDataService.qualityRules.delete).toHaveBeenCalledWith("quality-rule-1", {
        idempotency_key: "mdm-ui:quality-rule-deactivate:mdm-key-1",
      })
    );
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.QUALITY_RULES);
  });

  it("lists quality rules with configured paging, routes actions, and fails closed on missing responses", async () => {
    const user = userEvent.setup();
    const listRender = renderRoute(<QualityRuleListPage />, ROUTES.QUALITY_RULES);

    expect(await screen.findByRole("heading", { name: "Quality rules" })).toBeInTheDocument();
    expect(masterDataService.qualityRules.list).toHaveBeenCalledWith({
      page: 1,
      page_size: configuration.document.ui.list_page_size,
      ordering: "name",
    });
    expect(screen.getByText("Email required")).toBeInTheDocument();
    expect(screen.getByText("required")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /Email required/u }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      ROUTES.QUALITY_RULE_DETAIL("quality-rule-1")
    );
    listRender.unmount();

    service.qualityRules.list.mockResolvedValueOnce(list<DataQualityRule>([], { count: 0 }));
    const emptyRender = renderRoute(<QualityRuleListPage />, ROUTES.QUALITY_RULES);
    expect(await screen.findByText("No quality rules")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create first rule" }));
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.QUALITY_RULE_NEW);
    emptyRender.unmount();

    service.qualityRules.list.mockRejectedValueOnce(
      new ApiError("Rules unavailable", 503, undefined, "rules_down", "corr-rules")
    );
    renderRoute(<QualityRuleListPage />, ROUTES.QUALITY_RULES);
    expect(await screen.findByRole("alert")).toHaveTextContent("corr-rules");
  });
});
