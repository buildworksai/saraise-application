/* eslint-disable max-lines-per-function -- These governed configuration workflows intentionally exercise full preview/save/import/rollback paths in one render. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type {
  CrmConfiguration,
  CrmConfigurationDocument,
  CrmConfigurationExport,
  CrmConfigurationPreview,
  CrmConfigurationWrite,
  CrmConfigurationVersion,
} from "../contracts";
import { ConfigurationPage } from "../pages/ConfigurationPage";
import { validateCrmConfigurationDraft } from "../pages/configuration-validation";
import { crmKeys, crmService } from "../services/crm-service";

const documentFixture: CrmConfigurationDocument = {
  field_limits: {
    phone_min_digits: 7,
    phone_max_digits: 15,
    lead_name: 80,
    lead_email: 254,
    lead_phone: 32,
    lead_status: 32,
    account_name: 120,
    account_industry: 80,
    account_postal_code: 16,
    account_country: 2,
    contact_name: 80,
    contact_email: 254,
    contact_phone: 32,
    opportunity_name: 120,
    opportunity_amount_digits: 12,
    opportunity_amount_decimals: 2,
    opportunity_currency: 3,
    opportunity_stage: 32,
    opportunity_status: 32,
    activity_subject: 120,
    activity_outcome: 500,
    activity_external_id: 80,
    actor_id: 64,
    correlation_id: 64,
    async_idempotency_key: 80,
    domain_override_reason: 250,
    transition_reason: 250,
    loss_reason: 250,
    provider_id: 80,
    provider_evidence_string: 500,
  },
  lead: {
    default_score: 10,
    default_grade: "D",
    default_score_source: "rules",
    default_status: "new",
    score_min: 0,
    score_max: 100,
    grade_thresholds: { A: 90, B: 75, C: 50, D: 0 },
    qualification_threshold: 70,
    field_score_weights: { email: 10 },
    source_score_weights: { referral: 20 },
    terminal_states: ["converted", "lost"],
    transitions: {
      contact: { from: ["new"], to: "contacted" },
      qualify: { from: ["contacted"], to: "qualified" },
    },
  },
  account: {
    default_type: "prospect",
    allowed_types: ["prospect", "customer", "partner"],
    hierarchy_max_depth: 4,
  },
  contact: {
    default_engagement_score: 0,
    engagement_score_min: 0,
    engagement_score_max: 100,
    enforce_account_email_domain: true,
    engagement_lookback_days: 90,
    engagement_points_per_interaction: 5,
  },
  opportunity: {
    default_currency: "USD",
    default_probability: 10,
    default_stage: "prospecting",
    default_status: "open",
    probability_min: 0,
    probability_max: 100,
    minimum_amount: "1.00",
    closed_won_probability: 100,
    closed_lost_probability: 0,
    terminal_states: ["closed_won", "closed_lost"],
    transitions: {
      advance: { from: ["prospecting"], to: "qualification" },
    },
    stages: [
      { name: "prospecting", probability: 10, semantic_token: "info" },
      { name: "qualification", probability: 25, semantic_token: "accent" },
      { name: "closed_won", probability: 100, semantic_token: "success" },
    ],
  },
  activity: {
    default_type: "task",
    default_related_type: "Lead",
    require_future_task_due_date: true,
  },
  hierarchy: { max_nodes: 250, max_children: 25, page_size: 50 },
  forecast: { minimum_period_days: 7, default_period_days: 30, maximum_period_days: 90 },
  providers: {
    lead_scoring: null,
    revenue_prediction: "rules",
    score_min: 0,
    score_max: 100,
    confidence_min: "0.00",
    confidence_max: "1.00",
    maximum_evidence_factors: 5,
    extension_schema_version: "1",
    extension_priority_default: 50,
    extension_priority_min: 0,
    extension_priority_max: 100,
    retry_attempts: 2,
    backoff_base_seconds: "0.20",
    backoff_max_seconds: "2.00",
    backoff_jitter_seconds: "0.10",
  },
  jobs: {
    stale_deal_days: 30,
    stale_deal_min_days: 7,
    stale_deal_max_days: 90,
    iterator_chunk_size: 50,
  },
  pagination: { default_page_size: 25, maximum_page_size: 100 },
  api: { quota_cost: 1 },
  conversion: {
    create_account_by_default: true,
    close_date_offset_days: 30,
    use_current_version: true,
    transition_key_prefix: "crm",
  },
  health: { cache_timeout_seconds: 60 },
  ui: {
    score_bands: [
      { minimum: 90, grade: "A", semantic_token: "success" },
      { minimum: 75, grade: "B", semantic_token: "accent" },
      { minimum: 50, grade: "C", semantic_token: "warning" },
      { minimum: 0, grade: "D", semantic_token: "muted" },
    ],
    hierarchy_auto_expand_levels: 2,
    hierarchy_indentation_pixels: 24,
    minimum_pipeline_bar_percent: 3,
    saved_page_size: 25,
    dashboard_forecast_period_days: 30,
    prediction_retry_enabled: true,
    stale_deal_page_size: 25,
    pipeline_fetch_limit: 50,
  },
};

const configuration: CrmConfiguration = {
  id: "config-1",
  environment: "production",
  version: 7,
  document: documentFixture,
  feature_flags: { scoring: true, forecasting: false },
  rollout: { enabled: true, percentage: 25, roles: ["sales_admin"], cohorts: ["pilot"] },
  updated_at: "2026-07-31T00:00:00Z",
};

const versions: readonly CrmConfigurationVersion[] = [
  {
    id: "version-7",
    environment: "production",
    version: 7,
    document: documentFixture,
    feature_flags: configuration.feature_flags,
    rollout: configuration.rollout,
    actor_id: "actor-1",
    correlation_id: "req-7",
    change_type: "update",
    rollback_of_version: null,
    created_at: "2026-07-31T00:00:00Z",
  },
  {
    id: "version-6",
    environment: "production",
    version: 6,
    document: documentFixture,
    feature_flags: configuration.feature_flags,
    rollout: configuration.rollout,
    actor_id: "actor-2",
    correlation_id: "req-6",
    change_type: "rollback",
    rollback_of_version: 5,
    created_at: "2026-07-30T00:00:00Z",
  },
];

function preview(valid = true): CrmConfigurationPreview {
  return {
    valid,
    diff: { rollout: { percentage: [25, 40] } },
    errors: valid ? {} : { rollout: ["Rejected by server"] },
    effective: configuration,
  };
}

function renderPage(options: { seedGovernedQueries?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (options.seedGovernedQueries) {
    queryClient.setQueryData(crmKeys.configuration(), configuration);
    queryClient.setQueryData(crmKeys.configurationVersions(), versions);
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function getTextareaByValue(container: HTMLElement, value: string): HTMLTextAreaElement {
  const textarea = Array.from(container.querySelectorAll("textarea")).find((candidate) =>
    candidate.value.includes(value)
  );
  if (!(textarea instanceof HTMLTextAreaElement)) {
    throw new Error(`Configuration textarea containing ${value} was not rendered.`);
  }
  return textarea;
}

function textFile(body: string): File {
  return {
    name: "configuration.json",
    type: "application/json",
    text: () => Promise.resolve(body),
  } as File;
}

function draftWith(
  patch: (draft: CrmConfigurationWrite) => void = () => undefined
): CrmConfigurationWrite {
  const draft: CrmConfigurationWrite = {
    environment: configuration.environment,
    document: structuredClone(documentFixture),
    feature_flags: { ...configuration.feature_flags },
    rollout: {
      ...configuration.rollout,
      roles: [...configuration.rollout.roles],
      cohorts: [...configuration.rollout.cohorts],
    },
  };
  patch(draft);
  return draft;
}

beforeEach(() => {
  vi.spyOn(crmService, "getConfiguration").mockResolvedValue(configuration);
  vi.spyOn(crmService, "listConfigurationVersions").mockResolvedValue(versions);
  vi.spyOn(crmService, "previewConfiguration").mockResolvedValue(preview());
  vi.spyOn(crmService, "updateConfiguration").mockResolvedValue(configuration);
  vi.spyOn(crmService, "rollbackConfiguration").mockResolvedValue(configuration);
  vi.spyOn(crmService, "importConfiguration").mockResolvedValue(configuration);
  vi.spyOn(crmService, "exportConfiguration").mockResolvedValue({
    schema_version: 1,
    module: "crm",
    configuration,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CRM configuration page", () => {
  it("blocks invalid rollout and descending grade thresholds before governed preview or save", () => {
    const invalidRollout = draftWith((draft) => {
      draft.rollout.percentage = 101;
    });
    expect(validateCrmConfigurationDraft(invalidRollout)).toEqual(
      expect.objectContaining({
        rollout: "Rollout must be between 0 and 100 percent.",
      })
    );

    const invalidThresholds = draftWith((draft) => {
      draft.document.lead.grade_thresholds.B = 95;
    });
    expect(validateCrmConfigurationDraft(invalidThresholds)).toEqual(
      expect.objectContaining({
        "lead.grade_thresholds": "Grade thresholds must descend from A through D.",
      })
    );
    expect(crmService.previewConfiguration).not.toHaveBeenCalled();
    expect(crmService.updateConfiguration).not.toHaveBeenCalled();
  });

  it("validates every CRM configuration boundary with explicit field errors", () => {
    const cases: readonly [
      string,
      (draft: CrmConfigurationWrite) => void,
      readonly [string, string],
    ][] = [
      [
        "blank environment",
        (draft) => {
          draft.environment = " ";
        },
        ["environment", "Environment is required."],
      ],
      [
        "negative rollout",
        (draft) => {
          draft.rollout.percentage = -1;
        },
        ["rollout", "Rollout must be between 0 and 100 percent."],
      ],
      [
        "rollout over one hundred",
        (draft) => {
          draft.rollout.percentage = 101;
        },
        ["rollout", "Rollout must be between 0 and 100 percent."],
      ],
      [
        "equal lead score bounds",
        (draft) => {
          draft.document.lead.score_min = 100;
        },
        ["lead.score_min", "Minimum score must be lower than maximum score."],
      ],
      [
        "equal A and B thresholds",
        (draft) => {
          draft.document.lead.grade_thresholds.B = 90;
        },
        ["lead.grade_thresholds", "Grade thresholds must descend from A through D."],
      ],
      [
        "equal B and C thresholds",
        (draft) => {
          draft.document.lead.grade_thresholds.C = 75;
        },
        ["lead.grade_thresholds", "Grade thresholds must descend from A through D."],
      ],
      [
        "D above C threshold",
        (draft) => {
          draft.document.lead.grade_thresholds.D = 51;
        },
        ["lead.grade_thresholds", "Grade thresholds must descend from A through D."],
      ],
      [
        "equal probability bounds",
        (draft) => {
          draft.document.opportunity.probability_min = 100;
        },
        [
          "opportunity.probability_min",
          "Minimum probability must be lower than maximum probability.",
        ],
      ],
      [
        "zero minimum amount",
        (draft) => {
          draft.document.opportunity.minimum_amount = "0";
        },
        ["opportunity.minimum_amount", "Minimum amount must be positive."],
      ],
      [
        "forecast default below minimum",
        (draft) => {
          draft.document.forecast.default_period_days = 6;
        },
        [
          "forecast.default_period_days",
          "Default forecast period must be within configured limits.",
        ],
      ],
      [
        "forecast default above maximum",
        (draft) => {
          draft.document.forecast.default_period_days = 91;
        },
        [
          "forecast.default_period_days",
          "Default forecast period must be within configured limits.",
        ],
      ],
      [
        "zero default page size",
        (draft) => {
          draft.document.pagination.default_page_size = 0;
        },
        [
          "pagination.default_page_size",
          "Default page size must be within the configured maximum.",
        ],
      ],
      [
        "default page size above maximum",
        (draft) => {
          draft.document.pagination.default_page_size = 101;
        },
        [
          "pagination.default_page_size",
          "Default page size must be within the configured maximum.",
        ],
      ],
      [
        "zero pipeline fetch limit",
        (draft) => {
          draft.document.ui.pipeline_fetch_limit = 0;
        },
        [
          "ui.pipeline_fetch_limit",
          "Pipeline fetch limit must be within the API pagination maximum.",
        ],
      ],
      [
        "pipeline fetch limit above maximum",
        (draft) => {
          draft.document.ui.pipeline_fetch_limit = 101;
        },
        [
          "ui.pipeline_fetch_limit",
          "Pipeline fetch limit must be within the API pagination maximum.",
        ],
      ],
      [
        "empty pipeline stages",
        (draft) => {
          draft.document.opportunity.stages = [];
        },
        ["opportunity.stages", "At least one pipeline stage is required."],
      ],
    ];

    expect(validateCrmConfigurationDraft(draftWith())).toEqual({});
    for (const [name, mutateDraft, [field, message]] of cases) {
      const result = validateCrmConfigurationDraft(draftWith(mutateDraft));
      expect(result, name).toEqual({ [field]: message });
    }

    const acceptedBoundaries = draftWith((draft) => {
      draft.rollout.percentage = 0;
      draft.document.forecast.default_period_days = draft.document.forecast.minimum_period_days;
      draft.document.pagination.default_page_size = 1;
      draft.document.ui.pipeline_fetch_limit = 1;
    });
    expect(validateCrmConfigurationDraft(acceptedBoundaries)).toEqual({});

    const upperAcceptedBoundaries = draftWith((draft) => {
      draft.rollout.percentage = 100;
      draft.document.forecast.default_period_days = draft.document.forecast.maximum_period_days;
      draft.document.pagination.default_page_size = draft.document.pagination.maximum_page_size;
      draft.document.ui.pipeline_fetch_limit = draft.document.pagination.maximum_page_size;
      draft.document.lead.grade_thresholds.D = draft.document.lead.grade_thresholds.C;
    });
    expect(validateCrmConfigurationDraft(upperAcceptedBoundaries)).toEqual({});
  });

  it("reports invalid JSON and non-array edits without applying them to server preview", async () => {
    const user = userEvent.setup();
    const { container } = renderPage({ seedGovernedQueries: true });

    await screen.findByText("Complete behavior document");
    const stages = getTextareaByValue(container, "prospecting");
    fireEvent.change(stages, { target: { value: "{" } });
    fireEvent.blur(stages);

    expect(await screen.findByRole("alert")).toHaveTextContent(/JSON|property|Unexpected/u);

    fireEvent.change(stages, { target: { value: "{}" } });
    fireEvent.blur(stages);

    expect(screen.getByText("Value must be a JSON array.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(crmService.previewConfiguration).toHaveBeenCalledTimes(1));
    expect(
      vi.mocked(crmService.previewConfiguration).mock.calls[0]?.[0].document.opportunity.stages
    ).toHaveLength(3);
  });

  it("requires current server preview before saving the versioned configuration", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("Server validation passed.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(crmService.updateConfiguration).toHaveBeenCalledWith(
        expect.objectContaining({ environment: "production" }),
        7
      )
    );
    expect(
      await screen.findByText("Configuration saved and audit version created.")
    ).toBeInTheDocument();
  });

  it("previews valid imports, rejects malformed import documents, exports, and rolls back old versions", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:crm-config");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const { container } = renderPage();

    await screen.findByText("Version 7");
    const input = container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement))
      throw new Error("Configuration import input missing.");

    const invalidImport = textFile(JSON.stringify({ schema_version: 2 }));
    fireEvent.change(input, { target: { files: [invalidImport] } });
    expect(
      await screen.findByText("Import must be a CRM schema version 1 export document.")
    ).toBeInTheDocument();
    expect(crmService.importConfiguration).not.toHaveBeenCalled();

    const validImport: CrmConfigurationExport = {
      schema_version: 1,
      module: "crm",
      configuration,
    };
    const validFile = textFile(JSON.stringify(validImport));
    fireEvent.change(input, { target: { files: [validFile] } });

    await waitFor(() => expect(crmService.importConfiguration).toHaveBeenCalledWith(validImport));
    expect(
      await screen.findByText("Configuration previewed, imported, and versioned.")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(crmService.exportConfiguration).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:crm-config");

    const rollbackButtons = screen.getAllByRole("button", { name: "Rollback to this version" });
    expect(rollbackButtons[0]).toBeDisabled();
    const oldVersionRollback = rollbackButtons[1];
    if (!oldVersionRollback) throw new Error("Rollback control for the previous version missing.");
    await user.click(oldVersionRollback);
    await waitFor(() => expect(crmService.rollbackConfiguration).toHaveBeenCalledWith(6));
    expect(
      await screen.findByText("Configuration rolled back through a new immutable version.")
    ).toBeInTheDocument();
  });
});
