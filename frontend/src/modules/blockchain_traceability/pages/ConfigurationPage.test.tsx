/* eslint-disable max-lines-per-function -- configuration console tests exercise coupled preview/save/import/export branches. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  TraceabilityCapabilities,
  TraceabilityConfiguration,
  TraceabilityConfigurationDocument,
  TraceabilityConfigurationExport,
  TraceabilityConfigurationVersion,
  ModuleHealth,
} from "../contracts";
import {
  BlockchainTraceabilityApiError,
  blockchainTraceabilityService,
} from "../services/blockchain_traceability-service";
import { ConfigurationPage } from "./ConfigurationPage";

const now = "2026-07-30T10:00:00.000Z";

const documentFixture: TraceabilityConfigurationDocument = {
  validation: {
    max_json_bytes: 8192,
    max_json_depth: 8,
    max_json_keys: 64,
    gtin_lengths: [8, 12, 13, 14],
    max_revocation_reason_chars: 240,
    max_authenticity_token_chars: 128,
    max_actor_id_chars: 96,
    credential_type_max_chars: 80,
  },
  network_policy: { default_confirmation_depth: 2, max_confirmation_depth: 12 },
  schema_policy: { default_version: 1, allowed_versions: [1] },
  list_policy: {
    default_page_size: 25,
    max_page_size: 100,
    history_chunk_size: 50,
    verification_chunk_size: 20,
  },
  health_policy: {
    provider_probe_cache_ttl_seconds: 60,
    outbox_freshness_seconds: 120,
    cache_marker_ttl_seconds: 30,
  },
  inventory_policy: { validation_required: true },
  anchor_policy: { default_start_sequence: 1, use_current_head_default: false },
  credential_policy: { issuer_type: "ed25519", token_entropy_bytes: 32 },
  resilience: {
    timeout_seconds: 5,
    max_attempts: 3,
    base_backoff_seconds: 1,
    max_backoff_seconds: 10,
    circuit_failure_threshold: 3,
    circuit_recovery_seconds: 60,
  },
  workflow: {
    machines: {},
    network_deletable_statuses: ["draft", "disabled"],
    asset_deletable_statuses: ["draft", "retired"],
  },
  ui: {
    sidebar_order: 40,
    positive_statuses: ["active", "confirmed", "verified", "pass"],
    warning_statuses: ["draft", "queued", "inconclusive", "warning", "recalled"],
    default_recall_reason: "Configured recall reason",
    default_revocation_reason: "Configured revocation reason",
  },
  features: {
    enabled: true,
    roles: ["traceability-admin"],
    cohorts: ["default"],
    enable_supersede: true,
    enable_health: true,
  },
};

const configuration: TraceabilityConfiguration = {
  id: "configuration-1",
  tenant_id: "tenant-1",
  environment: "default",
  version: 3,
  document: documentFixture,
  updated_at: now,
  updated_by: "admin-1",
};

const capabilities: TraceabilityCapabilities = {
  can_read: true,
  can_update: true,
  can_preview: true,
  can_rollback: true,
  can_import: true,
  can_export: true,
  can_mutate_resources: true,
  can_finalize_compliance_evidence: true,
  can_supersede_compliance_evidence: true,
  document: documentFixture,
};

const history: readonly TraceabilityConfigurationVersion[] = [
  {
    version: 3,
    document: documentFixture,
    change_type: "update",
    created_by: "admin-1",
    created_at: now,
    correlation_id: "corr-current",
  },
  {
    version: 2,
    document: {
      ...documentFixture,
      list_policy: { ...documentFixture.list_policy, default_page_size: 10 },
    },
    change_type: "import",
    created_by: "admin-2",
    created_at: "2026-07-29T10:00:00.000Z",
    correlation_id: "corr-prior",
  },
];

const health: ModuleHealth = {
  status: "healthy",
  checked_at: now,
  dependencies: [
    {
      name: "database",
      status: "healthy",
      code: "ok",
      checked_at: now,
      circuit_state: "closed",
    },
  ],
};

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: vi.fn(),
});
Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: vi.fn(),
});

function renderPage(initialEntry = "/configuration") {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("blockchain traceability configuration page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(blockchainTraceabilityService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(blockchainTraceabilityService, "getCapabilities").mockResolvedValue(capabilities);
    vi.spyOn(blockchainTraceabilityService, "listConfigurationHistory").mockResolvedValue(history);
    vi.spyOn(blockchainTraceabilityService, "getHealth").mockResolvedValue(health);
  });

  it("requires a server preview of the exact safe document before saving", async () => {
    const user = userEvent.setup();
    const preview = vi
      .spyOn(blockchainTraceabilityService, "previewConfiguration")
      .mockResolvedValue({
        valid: true,
        changes: [{ path: "list_policy.default_page_size", before: 25, after: 40 }],
        document: {
          ...documentFixture,
          list_policy: { ...documentFixture.list_policy, default_page_size: 40 },
        },
      });
    const update = vi
      .spyOn(blockchainTraceabilityService, "updateConfiguration")
      .mockResolvedValue({
        ...configuration,
        version: 4,
        document: {
          ...documentFixture,
          list_policy: { ...documentFixture.list_policy, default_page_size: 40 },
        },
      });

    renderPage();

    expect(await screen.findByText("Blockchain traceability configuration")).toBeVisible();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();

    const pageSize = screen.getByLabelText("Default list page size");
    await user.clear(pageSize);
    await user.type(pageSize, "101");
    expect(screen.getByRole("alert")).toHaveTextContent("unsafe bound");
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();

    await user.clear(pageSize);
    await user.type(pageSize, "40");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(preview).toHaveBeenCalled());
    const previewRequest = preview.mock.calls.at(-1)?.[0];
    expect(previewRequest?.environment).toBe("default");
    expect(previewRequest?.document.list_policy.default_page_size).toBe(40);
    expect(
      await screen.findByText(
        "1 validated change(s). Save is enabled only while this exact normalized document remains unchanged."
      )
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save version" }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    const updateRequest = update.mock.calls.at(-1)?.[0];
    expect(updateRequest?.environment).toBe("default");
    expect(updateRequest?.document.list_policy.default_page_size).toBe(40);
  });

  it("imports exported documents, rolls back prior versions, and downloads an export", async () => {
    const user = userEvent.setup();
    const rollback = vi
      .spyOn(blockchainTraceabilityService, "rollbackConfiguration")
      .mockResolvedValue({
        ...configuration,
        version: 4,
      });
    const importConfiguration = vi
      .spyOn(blockchainTraceabilityService, "importConfiguration")
      .mockResolvedValue({ ...configuration, version: 4 });
    const exported: TraceabilityConfigurationExport = {
      schema: "saraise.blockchain_traceability.configuration/v1",
      environment: "default",
      version: 3,
      document: documentFixture,
    };
    vi.spyOn(blockchainTraceabilityService, "exportConfiguration").mockResolvedValue(exported);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:traceability-configuration");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    renderPage("/configuration?environment=staging");

    expect(await screen.findByText("Version 3 · default")).toBeVisible();
    expect(blockchainTraceabilityService.getConfiguration).toHaveBeenCalledWith("staging");
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(blockchainTraceabilityService.exportConfiguration).toHaveBeenCalledWith("staging")
    );
    expect(createObjectUrl).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:traceability-configuration");

    fireEvent.change(screen.getByLabelText("Import JSON"), {
      target: {
        value: JSON.stringify({
          ...exported,
          document: {
            ...documentFixture,
            ui: { ...documentFixture.ui, sidebar_order: 55 },
          },
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Import document" }));

    await waitFor(() => expect(importConfiguration).toHaveBeenCalled());
    const importRequest = importConfiguration.mock.calls.at(-1)?.[0];
    expect(importRequest?.environment).toBe("staging");
    expect(importRequest?.document.ui.sidebar_order).toBe(55);

    const rollbackButtons = screen.getAllByRole("button", { name: "Rollback" });
    expect(rollbackButtons[0]).toBeDisabled();
    await user.click(rollbackButtons[1]!);

    await waitFor(() =>
      expect(rollback).toHaveBeenCalledWith({ environment: "staging", version: 2 })
    );
    expect(screen.getByText("database")).toBeVisible();
    expect(screen.getByText(/ok · /i)).toBeVisible();
  });

  it("accepts raw configuration documents and invalidates preview after governed UI edits", async () => {
    const user = userEvent.setup();
    const preview = vi
      .spyOn(blockchainTraceabilityService, "previewConfiguration")
      .mockResolvedValue({
        valid: true,
        changes: [
          { path: "features.enabled", before: true, after: false },
          { path: "ui.sidebar_order", before: 40, after: 52 },
        ],
        document: {
          ...documentFixture,
          features: { ...documentFixture.features, enabled: false },
          ui: {
            ...documentFixture.ui,
            sidebar_order: 52,
            positive_statuses: ["verified", "confirmed"],
            warning_statuses: ["queued", "warning"],
          },
        },
      });
    const importConfiguration = vi
      .spyOn(blockchainTraceabilityService, "importConfiguration")
      .mockResolvedValue({
        ...configuration,
        version: 4,
        document: {
          ...documentFixture,
          features: { ...documentFixture.features, enabled: false },
        },
      });

    renderPage();

    await screen.findByText("Blockchain traceability configuration");
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: {
        value: JSON.stringify({
          ...documentFixture,
          features: { ...documentFixture.features, enabled: false },
          ui: { ...documentFixture.ui, sidebar_order: 52 },
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(preview.mock.calls.at(-1)?.[0].document.features.enabled).toBe(false);
    expect(preview.mock.calls.at(-1)?.[0].document.ui.sidebar_order).toBe(52);
    expect(screen.getByRole("button", { name: "Save version" })).toBeEnabled();

    await user.click(screen.getByLabelText("Enable traceability capability"));
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Positive status tokens"), {
      target: { value: "verified, confirmed" },
    });
    fireEvent.change(screen.getByLabelText("Warning status tokens"), {
      target: { value: "queued, warning" },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(2));
    expect(preview.mock.calls.at(-1)?.[0].document.ui.positive_statuses).toEqual([
      "verified",
      "confirmed",
    ]);

    fireEvent.change(screen.getByLabelText("Import JSON"), {
      target: {
        value: JSON.stringify({
          ...documentFixture,
          features: { ...documentFixture.features, enabled: false },
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Import document" }));

    await waitFor(() => expect(importConfiguration).toHaveBeenCalled());
    expect(importConfiguration.mock.calls.at(-1)?.[0].document.features.enabled).toBe(false);
  });

  it("fails closed on malformed imports and shows empty health without assuming success", async () => {
    const user = userEvent.setup();
    vi.spyOn(blockchainTraceabilityService, "getHealth").mockResolvedValue({
      status: "degraded",
      checked_at: now,
      dependencies: [],
    });
    const importConfiguration = vi.spyOn(blockchainTraceabilityService, "importConfiguration");

    renderPage();

    expect(await screen.findByText("No health dependencies reported")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Import JSON"), {
      target: { value: "[1,2,3]" },
    });
    await user.click(screen.getByRole("button", { name: "Import document" }));

    expect(
      await screen.findByRole("heading", { name: "Traceability request failed" })
    ).toBeVisible();
    expect(
      screen.getByText("The operation could not be completed. No success has been assumed.")
    ).toBeVisible();
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("disables governed operations when capabilities deny the configuration surface", async () => {
    const deniedCapabilities: TraceabilityCapabilities = {
      ...capabilities,
      can_update: false,
      can_preview: false,
      can_rollback: false,
      can_import: false,
      can_export: false,
      document: {
        ...documentFixture,
        features: { ...documentFixture.features, enabled: false, enable_health: true },
      },
    };
    vi.spyOn(blockchainTraceabilityService, "getCapabilities").mockResolvedValue(
      deniedCapabilities
    );
    const getHealth = vi.spyOn(blockchainTraceabilityService, "getHealth");

    renderPage();

    expect(await screen.findByText("Blockchain traceability configuration")).toBeVisible();
    expect(screen.getByRole("button", { name: "Export" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(screen.getByLabelText("Enable traceability capability")).toBeDisabled();
    expect(screen.getByLabelText("Enable compliance supersession workflow")).toBeDisabled();
    expect(screen.getByLabelText("Enable dependency health console")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Import document" })).toBeDisabled();
    for (const button of screen.getAllByRole("button", { name: "Rollback" })) {
      expect(button).toBeDisabled();
    }
    expect(
      screen.getByText("Health visibility is disabled by the active tenant feature policy.")
    ).toBeVisible();
    expect(getHealth).not.toHaveBeenCalled();
  });

  it("shows permission and dependency failures with correlation evidence", async () => {
    vi.spyOn(blockchainTraceabilityService, "getCapabilities").mockRejectedValue(
      new BlockchainTraceabilityApiError(
        "Traceability configuration permission denied",
        403,
        "permission_denied",
        {},
        "corr-denied"
      )
    );

    renderPage();

    expect(await screen.findByRole("heading", { name: "Permission required" })).toBeVisible();
    expect(
      screen.getByText("Your session is valid, but the required tenant capability was not granted.")
    ).toBeVisible();
    expect(screen.getByText("Correlation ID: corr-denied")).toBeVisible();
  });

  it("reports history and health dependency failures without enabling rollback assumptions", async () => {
    vi.spyOn(blockchainTraceabilityService, "listConfigurationHistory").mockRejectedValue(
      new Error("history audit store unavailable")
    );
    vi.spyOn(blockchainTraceabilityService, "getHealth").mockRejectedValue(
      new BlockchainTraceabilityApiError(
        "Provider health probe timed out",
        503,
        "dependency_unavailable",
        { state: "open" },
        "corr-health"
      )
    );

    renderPage();

    expect(await screen.findByText("Blockchain traceability configuration")).toBeVisible();
    const failureHeadings = await screen.findAllByRole("heading", {
      name: /Traceability request failed|Verification dependency unavailable/,
    });
    expect(failureHeadings).toHaveLength(2);
    expect(
      screen.getByText("The operation could not be completed. No success has been assumed.")
    ).toBeVisible();
    expect(screen.getByText("Provider health probe timed out")).toBeVisible();
    expect(screen.getByText("Correlation ID: corr-health")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Rollback" })).not.toBeInTheDocument();
  });
});
