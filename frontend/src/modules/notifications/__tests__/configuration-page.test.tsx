/* eslint-disable max-lines-per-function -- governed configuration page tests cover complete operator workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationImportInput,
  ConfigurationSimulationInput,
  ConfigurationWriteInput,
  NotificationConfiguration,
  NotificationConfigurationDocument,
} from "../contracts";
import { notificationService } from "../services/notification-service";
import { NotificationConfigurationPage } from "../pages/NotificationConfigurationPage";

vi.mock("../services/notification-service", () => ({
  NOTIFICATION_QUERY_KEYS: {
    configuration: (environment: string) => ["notifications", "configuration", environment],
  },
  notificationService: {
    configuration: {
      exportDocument: vi.fn(),
      get: vi.fn(),
      importDocument: vi.fn(),
      simulate: vi.fn(),
      update: vi.fn(),
    },
  },
}));

const configurationApi = vi.mocked(notificationService.configuration);

const channel = {
  enabled: true,
  adapter_key: "smtp",
  credential_ref: "secret://smtp",
  sender_ref: "noreply@saraise.com",
  timeout_seconds: 30,
  retry: {
    max_attempts: 3,
    base_seconds: 2,
    maximum_seconds: 120,
    retryable_outcomes: ["retryable_failure", "timeout"],
  },
  circuit: { failure_threshold: 5, reset_seconds: 60 },
  rate_limit_per_minute: 120,
};

const documentFixture: NotificationConfigurationDocument = {
  schema_version: 2,
  channels: {
    in_app: { ...channel, adapter_key: "in-app" },
    email: channel,
    sms: { ...channel, adapter_key: "twilio" },
    push: { ...channel, adapter_key: "web-push" },
    webhook: { ...channel, adapter_key: "signed-webhook" },
  },
  preferences: { default_enabled: true, mandatory_categories: ["security"] },
  batch_size: 100,
  max_attempts: 3,
  backoff: { base_seconds: 2, maximum_seconds: 120 },
  retention: { delivery_days: 90, inbox_days: 30 },
  limits: { context_bytes: 32768, metadata_bytes: 8192 },
  allowed_action_url_hosts: ["app.saraise.com"],
  allowed_webhook_hosts: ["hooks.saraise.com"],
  feature_flags: {
    digest: { enabled: true, tenant_ids: ["tenant-1"], roles: ["ops"], cohorts: ["beta"] },
  },
  digest_schedules: { hourly_minute: 15, daily_time: "09:00", weekly_day: 1 },
  quiet_hours: { start: "22:00", end: "07:00", timezone: "UTC" },
  provider_callbacks: { timestamp_tolerance_seconds: 300 },
};

const configuration: NotificationConfiguration = {
  id: "config-1",
  environment: "development",
  active_version: 4,
  document: documentFixture,
  checksum: "checksum-4",
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("NotificationConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    configurationApi.get.mockResolvedValue(configuration);
    configurationApi.simulate.mockResolvedValue({
      valid: true,
      changes: [{ path: "channels.email.timeout_seconds", before: 30, after: 45, impact: "safer" }],
      decision: "allow",
      warnings: ["partial rollout"],
    });
    configurationApi.update.mockResolvedValue({
      ...configuration,
      active_version: 5,
      document: { ...documentFixture, batch_size: 250 },
    });
    configurationApi.importDocument.mockResolvedValue({
      valid: true,
      changes: [],
      decision: "allow",
      warnings: [],
    });
    configurationApi.exportDocument.mockResolvedValue({
      schema_version: 2,
      environment: "development",
      exported_at: "2026-07-23T00:00:00Z",
      configuration: documentFixture,
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:notifications"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    if (!File.prototype.text) {
      Object.defineProperty(File.prototype, "text", {
        configurable: true,
        value(this: File) {
          return new Response(this).text();
        },
      });
    }
  });

  it("simulates changed channel settings before applying a versioned save", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Notification configuration" })
    ).toBeInTheDocument();
    const emailTimeoutInput = (await screen.findAllByLabelText("Timeout seconds"))[1];
    if (!emailTimeoutInput) throw new Error("Email timeout input was not rendered.");
    fireEvent.change(emailTimeoutInput, {
      target: { value: "45" },
    });
    await user.type(
      screen.getByPlaceholderText("Why is this configuration changing?"),
      "Tune email provider timeout"
    );
    await user.click(screen.getByRole("button", { name: "Simulate impact" }));

    await waitFor(() => expect(configurationApi.simulate).toHaveBeenCalled());
    const simulateRequest: ConfigurationSimulationInput | undefined =
      configurationApi.simulate.mock.calls.at(-1)?.[1];
    expect(simulateRequest?.document.channels.email.timeout_seconds).toBe(45);
    expect(simulateRequest?.scenario).toEqual({
      category: "system",
      channel: "in_app",
      priority: 5,
    });
    expect(await screen.findByText(/allow · 1 changes · 1 warnings/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Apply new version" }));
    await waitFor(() => expect(configurationApi.update).toHaveBeenCalled());
    const updateRequest: ConfigurationWriteInput | undefined =
      configurationApi.update.mock.calls.at(-1)?.[1];
    expect(updateRequest?.expected_version).toBe(4);
    expect(updateRequest?.change_summary).toBe("Tune email provider timeout");
  });

  it("rejects invalid JSON editor values and performs import dry-run plus export", async () => {
    const user = userEvent.setup();
    const invalid = renderPage();

    const featureFlags = await screen.findByLabelText("Feature flags and phased rollout");
    fireEvent.change(featureFlags, { target: { value: "{" } });
    expect(screen.getByRole("alert")).toHaveTextContent("feature flags must be valid JSON.");
    expect(screen.getByRole("button", { name: "Simulate impact" })).toBeDisabled();
    invalid.unmount();

    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Notification configuration" })
    ).toBeInTheDocument();
    const importPayload = JSON.stringify({
      configuration: { ...documentFixture, batch_size: 250 },
    });
    const file = new File([importPayload], "notifications-export.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn(() => Promise.resolve(importPayload)),
    });
    await user.upload(screen.getByLabelText("Import dry-run"), file);
    await waitFor(() => expect(configurationApi.importDocument).toHaveBeenCalled());
    const importRequest: ConfigurationImportInput | undefined =
      configurationApi.importDocument.mock.calls.at(-1)?.[1];
    expect(importRequest?.dry_run).toBe(true);
    expect(importRequest?.expected_version).toBe(4);
    expect(importRequest?.change_summary).toBe("Import preview: notifications-export.json");
    expect(importRequest?.document.batch_size).toBe(250);
    expect(
      await screen.findByText(
        "Import dry-run completed. Review and simulate the proposed document before applying."
      )
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(configurationApi.exportDocument).toHaveBeenCalledWith("development");
  });
});
