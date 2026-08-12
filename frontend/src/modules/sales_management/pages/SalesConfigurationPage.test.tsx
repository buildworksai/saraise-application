/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- configuration tests cover end-to-end governed UI mutation paths; asymmetric matcher payloads are intentionally inspected. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationExport,
  SalesConfiguration,
  SalesConfigurationVersion,
} from "../contracts";
import { SalesConfigurationPage } from "./SalesConfigurationPage";
import { salesQueryKeys, salesService } from "../services/sales-service";

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: {
    all: ["sales-management"],
    configuration: () => ["sales-management", "configuration"],
    configurationVersions: () => ["sales-management", "configuration-versions"],
    configurationVersion: (version: number) => [
      "sales-management",
      "configuration-version",
      version,
    ],
  },
  salesService: {
    getConfiguration: vi.fn(),
    previewConfiguration: vi.fn(),
    applyConfiguration: vi.fn(),
    listConfigurationVersions: vi.fn(),
    getConfigurationVersion: vi.fn(),
    rollbackConfiguration: vi.fn(),
    exportConfiguration: vi.fn(),
    importConfiguration: vi.fn(),
  },
}));

const stamp = "2026-07-31T00:00:00Z";
const mutable = {
  id: "sales-config-1",
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  deleted_at: null,
  deleted_by: null,
  lock_version: 7,
};
const configuration: SalesConfiguration = {
  ...mutable,
  environment: "development",
  default_currency: "USD",
  currency_decimal_places: 2,
  rounding_mode: "ROUND_HALF_UP",
  quotation_validity_days: 30,
  credit_check_enabled: true,
  inventory_confirmation_required: false,
  manual_discount_enabled: false,
  maximum_manual_discount_percent: "10",
  manual_tax_enabled: false,
  quotation_prefix: "QT",
  order_prefix: "SO",
  delivery_prefix: "DN",
  sequence_padding: 5,
  version: 3,
};
const version: SalesConfigurationVersion = {
  id: "config-version-2",
  tenant_id: "tenant-1",
  configuration_id: "sales-config-1",
  version: 2,
  snapshot: {
    default_currency: "EUR",
    currency_decimal_places: 2,
    rounding_mode: "ROUND_HALF_EVEN",
    quotation_validity_days: 45,
    credit_check_enabled: false,
    inventory_confirmation_required: true,
    manual_discount_enabled: true,
    maximum_manual_discount_percent: "15",
    manual_tax_enabled: true,
    quotation_prefix: "EUQ",
    order_prefix: "EUO",
    delivery_prefix: "EUD",
    sequence_padding: 6,
  },
  change_reason: "Previous rollout",
  actor_id: "user-1",
  correlation_id: "corr-sales-config",
  created_at: stamp,
};
const importDocument: ConfigurationExport = {
  schema_version: 1,
  environment: "development",
  exported_at: stamp,
  values: version.snapshot,
};

function page<T>(data: T[]) {
  return {
    data,
    meta: {
      correlation_id: "corr-sales-config",
      timestamp: stamp,
      pagination: {
        page: 1,
        page_size: 25,
        count: data.length,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    },
  };
}

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

function jsonFile(contents: string, name: string) {
  const file = new File([contents], name, { type: "application/json" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve(contents) });
  return file;
}

describe("SalesConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "rollback-key") });
    vi.mocked(salesService.getConfiguration).mockResolvedValue(configuration);
    vi.mocked(salesService.listConfigurationVersions).mockResolvedValue(page([version]));
    vi.mocked(salesService.getConfigurationVersion).mockResolvedValue(version);
  });

  it("validates bounded policy fields before preview or apply", async () => {
    const user = userEvent.setup();
    renderPage(<SalesConfigurationPage />);

    expect(await screen.findByLabelText("Default currency")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Default currency"));
    await user.type(screen.getByLabelText("Default currency"), "US1");
    await user.clear(screen.getByLabelText("quotation prefix"));
    await user.type(screen.getByLabelText("quotation prefix"), "too_long_prefix");
    await user.type(screen.getByLabelText("Change reason"), "Bad policy");

    expect(screen.getByText("Use three uppercase letters.")).toBeInTheDocument();
    expect(screen.getByText("Use 1–12 uppercase letters, digits, or hyphens.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply configuration" })).toBeDisabled();
    expect(salesService.previewConfiguration).not.toHaveBeenCalled();
    expect(salesService.applyConfiguration).not.toHaveBeenCalled();
  });

  it("previews dry-run diffs and applies audited configuration changes", async () => {
    const user = userEvent.setup();
    vi.mocked(salesService.previewConfiguration).mockResolvedValue({
      valid: true,
      diff: [{ field: "default_currency", before: "USD", after: "EUR" }],
      affected_workflows: ["quotation"],
      restart_required: false,
      proposed: { ...version.snapshot },
    });
    vi.mocked(salesService.applyConfiguration).mockResolvedValue({
      ...configuration,
      default_currency: "EUR",
      version: 4,
    });
    renderPage(<SalesConfigurationPage />);

    expect(await screen.findByText(/Environment: development. Version 3/u)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Default currency"));
    await user.type(screen.getByLabelText("Default currency"), "eur");
    await user.type(screen.getByLabelText("Change reason"), "Switch pilot currency");
    await user.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(await screen.findByText("No service restart is required.")).toBeInTheDocument();
    expect(screen.getByText(/default_currency/u).closest("li")).toHaveTextContent("USD");
    expect(screen.getByText(/default_currency/u).closest("li")).toHaveTextContent("EUR");
    expect(salesService.previewConfiguration).toHaveBeenCalledWith(
      expect.objectContaining({ default_currency: "EUR" })
    );

    await user.click(screen.getByRole("button", { name: "Apply configuration" }));
    await waitFor(() =>
      expect(salesService.applyConfiguration).toHaveBeenCalledWith({
        expected_version: 3,
        values: expect.objectContaining({ default_currency: "EUR" }),
        reason: "Switch pilot currency",
      })
    );
  });

  it("validates imported JSON before apply and rejects malformed documents locally", async () => {
    const user = userEvent.setup();
    vi.mocked(salesService.importConfiguration).mockResolvedValueOnce({
      valid: true,
      diff: [{ field: "rounding_mode", before: "ROUND_HALF_UP", after: "ROUND_HALF_EVEN" }],
      affected_workflows: ["order-confirmation"],
      restart_required: true,
      proposed: version.snapshot,
    });
    vi.mocked(salesService.importConfiguration).mockResolvedValueOnce({
      ...configuration,
      ...version.snapshot,
      version: 4,
    });
    renderPage(<SalesConfigurationPage />);

    expect(await screen.findByLabelText("Configuration document")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Change reason"), "Import reviewed sales controls");
    await user.upload(
      screen.getByLabelText("Configuration document"),
      jsonFile("{}", "invalid.json")
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid configuration document schema."
    );
    expect(screen.getByRole("button", { name: "Validate import" })).toBeDisabled();

    await user.upload(
      screen.getByLabelText("Configuration document"),
      jsonFile(JSON.stringify(importDocument), "sales-config.json")
    );
    await user.click(screen.getByRole("button", { name: "Validate import" }));
    await waitFor(() =>
      expect(salesService.importConfiguration).toHaveBeenCalledWith({
        expected_version: 3,
        document: importDocument,
        dry_run: true,
        reason: "Import reviewed sales controls",
      })
    );
    expect(screen.getByRole("button", { name: "Apply import" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Apply import" }));
    await waitFor(() =>
      expect(salesService.importConfiguration).toHaveBeenLastCalledWith({
        expected_version: 3,
        document: importDocument,
        dry_run: false,
        reason: "Import reviewed sales controls",
      })
    );
  });

  it("loads version snapshots and submits idempotent rollback requests", async () => {
    const user = userEvent.setup();
    vi.mocked(salesService.rollbackConfiguration).mockResolvedValue({
      ...configuration,
      ...version.snapshot,
      version: 4,
    });
    renderPage(<SalesConfigurationPage />);

    expect(await screen.findByRole("button", { name: /Version 2/u })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Change reason"), "Restore approved settings");
    await user.click(screen.getByRole("button", { name: /Version 2/u }));
    expect(await screen.findByText(/ROUND_HALF_EVEN/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rollback to version 2" }));
    await user.click(screen.getByRole("button", { name: "Create rollback version" }));

    await waitFor(() =>
      expect(salesService.rollbackConfiguration).toHaveBeenCalledWith({
        target_version: 2,
        expected_version: 3,
        reason: "Restore approved settings",
        idempotency_key: "rollback-key",
      })
    );
    expect(salesQueryKeys.all).toEqual(["sales-management"]);
  });
});
