/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- configuration coverage exercises governed mutation flows through mocked services; asymmetric matcher payloads are intentionally inspected. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  MasterDataConfiguration,
  MasterDataConfigurationDocument,
  MasterDataConfigurationVersion,
} from "../contracts";
import { MasterDataConfigurationPage } from "../pages/MasterDataConfigurationPage";
import { masterDataService } from "../services/master-data-service";

vi.mock("../services/master-data-service", () => ({
  masterDataService: {
    configuration: {
      current: vi.fn(),
      history: vi.fn(),
      preview: vi.fn(),
      update: vi.fn(),
      rollback: vi.fn(),
      importDocument: vi.fn(),
      exportDocument: vi.fn(),
    },
  },
}));

const stamp = "2026-07-31T00:00:00Z";
const documentFixture: MasterDataConfigurationDocument = {
  environment: "development",
  schema_policy: {
    entity_type_key_pattern: "^[a-z][a-z0-9_]*$",
    entity_type_key_max_length: 64,
    field_path_pattern: "^[a-z][a-z0-9_.]*$",
    allowed_json_schema_keywords: ["type", "properties", "required"],
    max_payload_bytes: 1024,
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
    rule_schemas: { required: {}, format: {}, range: {}, timeliness: {} },
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
    defaults: {
      algorithm: "exact",
      review_threshold: "0.80",
      auto_confirm_threshold: "0.95",
    },
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
    minimum_bar_percent: 3,
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
    percentage: 25,
  },
};

const configurationFixture: MasterDataConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  document: documentFixture,
  version: 3,
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
};

const historyFixture: MasterDataConfigurationVersion = {
  id: "version-2",
  tenant_id: "tenant-1",
  configuration: "config-1",
  version: 2,
  prior_value: null,
  new_value: documentFixture,
  actor_id: "user-1",
  correlation_id: "corr-mdm-config",
  change_type: "update",
  reason: "Previous policy",
  created_at: stamp,
};

function item<T>(data: T) {
  return { data, meta: { correlation_id: "corr-mdm-config", timestamp: stamp } };
}

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

describe("MasterDataConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    let sequence = 0;
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `config-key-${(sequence += 1)}`) });
    vi.mocked(masterDataService.configuration.current).mockResolvedValue(
      item(configurationFixture)
    );
    vi.mocked(masterDataService.configuration.history).mockResolvedValue({
      items: [historyFixture],
      meta: { correlation_id: "corr-mdm-config", timestamp: stamp },
    });
  });

  it("blocks invalid rollout and matching thresholds before server preview or save", async () => {
    const user = userEvent.setup();
    renderPage(<MasterDataConfigurationPage />);

    expect(
      await screen.findByRole("heading", { name: "Master-data configuration" })
    ).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Rollout percentage"));
    await user.type(screen.getByLabelText("Rollout percentage"), "125");
    await user.clear(screen.getByLabelText("Review threshold"));
    await user.type(screen.getByLabelText("Review threshold"), "0.99");
    await user.clear(screen.getByLabelText("Auto-confirm threshold"));
    await user.type(screen.getByLabelText("Auto-confirm threshold"), "0.90");
    await user.type(screen.getByLabelText("Change reason"), "Unsafe tenant rollout");

    expect(screen.getByText("Percentage must be between 0 and 100.")).toBeInTheDocument();
    expect(
      screen.getByText("Auto-confirm must be at least the review threshold.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply validated version" })).toBeDisabled();
    expect(masterDataService.configuration.preview).not.toHaveBeenCalled();
    expect(masterDataService.configuration.update).not.toHaveBeenCalled();
  });

  it("previews, applies, imports, and rolls back audited configuration versions", async () => {
    const user = userEvent.setup();
    const previewDocument = {
      ...documentFixture,
      feature_rollout: { ...documentFixture.feature_rollout, percentage: 40 },
    };
    vi.mocked(masterDataService.configuration.preview).mockResolvedValue(
      item({
        valid: true,
        document: previewDocument,
        changes: [{ field: "feature_rollout.percentage" }],
      })
    );
    vi.mocked(masterDataService.configuration.update).mockResolvedValue(
      item({ ...configurationFixture, document: previewDocument, version: 4 })
    );
    vi.mocked(masterDataService.configuration.importDocument).mockResolvedValue(
      item({ ...configurationFixture, document: previewDocument, version: 5 })
    );
    vi.mocked(masterDataService.configuration.rollback).mockResolvedValue(
      item({ ...configurationFixture, version: 6 })
    );
    renderPage(<MasterDataConfigurationPage />);

    expect(await screen.findByText(/Tenant-scoped version 3/u)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Rollout percentage"));
    await user.type(screen.getByLabelText("Rollout percentage"), "40");
    await user.type(screen.getByLabelText("Change reason"), "Raise tenant rollout after pilot");
    await user.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(await screen.findByText("Server validation passed")).toBeInTheDocument();
    expect(masterDataService.configuration.preview).toHaveBeenCalledWith({
      document: expect.objectContaining({
        feature_rollout: expect.objectContaining({ percentage: 40 }),
      }),
    });

    await user.click(screen.getByRole("button", { name: "Apply validated version" }));
    await waitFor(() =>
      expect(masterDataService.configuration.update).toHaveBeenCalledWith("config-1", {
        document: expect.objectContaining({
          feature_rollout: expect.objectContaining({ percentage: 40 }),
        }),
        reason: "Raise tenant rollout after pilot",
        idempotency_key: "mdm-ui:configuration-save:config-key-1",
      })
    );

    fireEvent.change(screen.getByLabelText("Configuration import document"), {
      target: { value: JSON.stringify(previewDocument) },
    });
    await user.click(screen.getByRole("button", { name: "Import validated document" }));
    await waitFor(() =>
      expect(masterDataService.configuration.importDocument).toHaveBeenCalledWith({
        document: previewDocument,
        reason: "Raise tenant rollout after pilot",
        idempotency_key: "mdm-ui:configuration-import:config-key-2",
      })
    );

    await user.click(screen.getByRole("button", { name: "Rollback to v2" }));
    await waitFor(() =>
      expect(masterDataService.configuration.rollback).toHaveBeenCalledWith({
        version: 2,
        reason: "Raise tenant rollout after pilot",
        idempotency_key: "mdm-ui:configuration-rollback:config-key-3",
      })
    );
  });

  it("exports the active document, rejects malformed imports, and renders empty history", async () => {
    const user = userEvent.setup();
    vi.mocked(masterDataService.configuration.history).mockResolvedValue({
      items: [],
      meta: { correlation_id: "corr-mdm-config", timestamp: stamp },
    });
    vi.mocked(masterDataService.configuration.exportDocument).mockResolvedValue(
      item({
        module: "master_data_management",
        schema_version: 1,
        configuration_version: 3,
        document: documentFixture,
      })
    );
    const createObjectURL = vi.fn(() => "blob:mdm-config");
    const revokeObjectURL = vi.fn();
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });

    renderPage(<MasterDataConfigurationPage />);

    expect(await screen.findByText("No configuration history was returned.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(masterDataService.configuration.exportDocument).toHaveBeenCalled());
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mdm-config");

    fireEvent.change(screen.getByLabelText("Configuration import document"), {
      target: { value: "not-json" },
    });
    await user.type(screen.getByLabelText("Change reason"), "Import malformed document");
    await user.click(screen.getByRole("button", { name: "Import validated document" }));

    expect(await screen.findByText("The import document is not valid JSON.")).toBeInTheDocument();
    expect(masterDataService.configuration.importDocument).not.toHaveBeenCalled();
  });

  it("shows governed failures for missing current configuration and history outages", async () => {
    vi.mocked(masterDataService.configuration.current).mockResolvedValue(
      item({
        ...configurationFixture,
        document: undefined as unknown as MasterDataConfigurationDocument,
      })
    );
    const { unmount } = renderPage(<MasterDataConfigurationPage />);

    expect(
      await screen.findByText("Tenant configuration was not returned. Editing is disabled.")
    ).toBeInTheDocument();
    unmount();

    vi.mocked(masterDataService.configuration.current).mockResolvedValue(
      item(configurationFixture)
    );
    vi.mocked(masterDataService.configuration.history).mockRejectedValue(
      new Error("history unavailable")
    );
    renderPage(<MasterDataConfigurationPage />);

    expect(await screen.findByText("history unavailable")).toBeInTheDocument();
  });

  it("stages typed UI, entity, and matching defaults before preview", async () => {
    const user = userEvent.setup();
    vi.mocked(masterDataService.configuration.preview).mockResolvedValue(
      item({ valid: true, document: documentFixture, changes: [] })
    );
    renderPage(<MasterDataConfigurationPage />);

    expect(
      await screen.findByRole("heading", { name: "Master-data configuration" })
    ).toBeInTheDocument();
    await user.click(screen.getByLabelText("Module enabled"));
    fireEvent.change(screen.getByLabelText("Runtime modes (comma-separated)"), {
      target: { value: "saas, self-hosted" },
    });
    fireEvent.change(screen.getByLabelText("Roles (comma-separated)"), {
      target: { value: "admin, steward" },
    });
    fireEvent.change(screen.getByLabelText("Cohorts (comma-separated)"), {
      target: { value: "pilot, global" },
    });
    await user.clear(screen.getByLabelText("Sidebar order"));
    await user.type(screen.getByLabelText("Sidebar order"), "20");
    await user.clear(screen.getByLabelText("Loading skeleton cards"));
    await user.type(screen.getByLabelText("Loading skeleton cards"), "6");
    await user.clear(screen.getByLabelText("List page size"));
    await user.type(screen.getByLabelText("List page size"), "50");
    await user.clear(screen.getByLabelText("Entity selector size"));
    await user.type(screen.getByLabelText("Entity selector size"), "250");
    await user.clear(screen.getByLabelText("Dashboard minimum bar %"));
    await user.type(screen.getByLabelText("Dashboard minimum bar %"), "7");
    await user.selectOptions(screen.getByLabelText("Default issue queue state"), "waived");
    await user.selectOptions(screen.getByLabelText("danger status token"), "warning");
    await user.selectOptions(screen.getByLabelText("success status token"), "destructive");
    await user.selectOptions(screen.getByLabelText("warning status token"), "success");
    await user.clear(screen.getByLabelText("Default source system"));
    await user.type(screen.getByLabelText("Default source system"), "CRM");
    await user.selectOptions(screen.getByLabelText("Default quality rule"), "format");
    await user.selectOptions(screen.getByLabelText("Default matching algorithm"), "fuzzy");
    await user.clear(screen.getByLabelText("Job poll interval (ms)"));
    await user.type(screen.getByLabelText("Job poll interval (ms)"), "3000");
    await user.type(screen.getByLabelText("Change reason"), "Tune operator defaults");
    await user.click(screen.getByRole("button", { name: "Preview changes" }));

    await waitFor(() =>
      expect(masterDataService.configuration.preview).toHaveBeenCalledWith({
        document: expect.objectContaining({
          feature_rollout: expect.objectContaining({
            enabled: false,
            modes: ["saas", "self-hosted"],
            roles: ["admin", "steward"],
            cohorts: ["pilot", "global"],
          }),
          ui: expect.objectContaining({
            sidebar_order: 20,
            skeleton_cards: 6,
            list_page_size: 50,
            quality_issue_default_status: "waived",
            status_tokens: { danger: "warning", success: "destructive", warning: "success" },
          }),
          limits: expect.objectContaining({ selector_page_size: 250 }),
          dashboard: expect.objectContaining({ minimum_bar_percent: 7 }),
          entity_defaults: { source_system: "CRM" },
          quality: expect.objectContaining({
            defaults: expect.objectContaining({ rule_type: "format" }),
          }),
          matching: expect.objectContaining({
            defaults: expect.objectContaining({ algorithm: "fuzzy" }),
          }),
          operational: expect.objectContaining({ job_poll_interval_ms: 3000 }),
        }),
      })
    );
  });
});
