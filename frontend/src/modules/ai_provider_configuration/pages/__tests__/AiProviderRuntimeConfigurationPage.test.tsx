/* eslint-disable max-lines-per-function -- runtime configuration is a multi-panel import/export/preview form. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  AIProviderRuntimeConfiguration,
  AIProviderRuntimeConfigurationAudit,
  AIProviderRuntimeConfigurationVersion,
} from "../../contracts";
import { AiProviderRuntimeConfigurationPage } from "../AiProviderRuntimeConfigurationPage";
import { aiProviderConfigurationService } from "../../services/ai_provider_configuration-service";

vi.mock("../../services/ai_provider_configuration-service");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const stamp = "2026-01-01T00:00:00Z";
const runtimeConfiguration: AIProviderRuntimeConfiguration = {
  id: "runtime-1",
  tenant_id: "tenant-1",
  environment: "default",
  version: 3,
  updated_by: "operator-1",
  created_at: stamp,
  updated_at: stamp,
  values: {
    routing: { default_provider: "openai" },
    limits: { max_tokens: 4096 },
  },
};
const versions: AIProviderRuntimeConfigurationVersion[] = [
  {
    id: "version-2",
    tenant_id: "tenant-1",
    configuration: "runtime-1",
    version: 2,
    environment: "default",
    values: { routing: { default_provider: "anthropic" } },
    created_by: "operator-1",
    correlation_id: "corr-version-2",
    rollback_of: null,
    created_at: stamp,
  },
  {
    id: "version-3",
    tenant_id: "tenant-1",
    configuration: "runtime-1",
    version: 3,
    environment: "default",
    values: runtimeConfiguration.values,
    created_by: "operator-1",
    correlation_id: "corr-version-3",
    rollback_of: null,
    created_at: stamp,
  },
];
const audit: AIProviderRuntimeConfigurationAudit[] = [
  {
    id: "audit-1",
    tenant_id: "tenant-1",
    configuration: "runtime-1",
    action: "publish",
    actor_id: "operator-1",
    correlation_id: "corr-audit-1",
    from_version: 2,
    to_version: 3,
    before: { routing: { default_provider: "anthropic" } },
    after: runtimeConfiguration.values,
    rollback_of: null,
    created_at: stamp,
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AiProviderRuntimeConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AiProviderRuntimeConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.getRuntimeConfiguration).mockResolvedValue(
      runtimeConfiguration
    );
    vi.mocked(aiProviderConfigurationService.listRuntimeConfigurationVersions).mockResolvedValue(
      versions
    );
    vi.mocked(aiProviderConfigurationService.listRuntimeConfigurationAudit).mockResolvedValue(
      audit
    );
    vi.mocked(aiProviderConfigurationService.previewRuntimeConfiguration).mockResolvedValue({
      environment: "staging",
      current_version: 3,
      would_create_version: 4,
      changes: {
        "routing.default_provider": { before: "openai", after: "anthropic" },
      },
    });
    vi.mocked(aiProviderConfigurationService.updateRuntimeConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      environment: "staging",
      version: 4,
      values: { routing: { default_provider: "anthropic" } },
    });
    vi.mocked(aiProviderConfigurationService.rollbackRuntimeConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      version: 4,
    });
    vi.mocked(aiProviderConfigurationService.exportRuntimeConfiguration).mockResolvedValue({
      module: "ai_provider_configuration",
      environment: "default",
      version: 3,
      values: runtimeConfiguration.values,
    });
  });

  it("previews and publishes parsed runtime configuration values", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Runtime configuration" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Environment"), { target: { value: "staging" } });
    fireEvent.change(screen.getByLabelText("Runtime configuration JSON"), {
      target: { value: '{ "routing": { "default_provider": "anthropic" } }' },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() =>
      expect(aiProviderConfigurationService.previewRuntimeConfiguration).toHaveBeenCalledWith(
        "staging",
        { routing: { default_provider: "anthropic" } }
      )
    );
    expect(await screen.findByText(/would_create_version/u)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() =>
      expect(aiProviderConfigurationService.updateRuntimeConfiguration).toHaveBeenCalledWith(
        "staging",
        { routing: { default_provider: "anthropic" } }
      )
    );
  });

  it("reports invalid JSON and avoids preview or publish service calls", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByLabelText("Runtime configuration JSON");
    fireEvent.change(screen.getByLabelText("Runtime configuration JSON"), {
      target: { value: "[]" },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Configuration must be a JSON object."
    );
    expect(aiProviderConfigurationService.previewRuntimeConfiguration).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Runtime configuration JSON"), {
      target: { value: "{" },
    });
    await user.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Expected property name/u);
    expect(aiProviderConfigurationService.updateRuntimeConfiguration).not.toHaveBeenCalled();
  });

  it("renders load failures with retry-visible API problem state", async () => {
    vi.mocked(aiProviderConfigurationService.getRuntimeConfiguration).mockRejectedValue(
      new ApiError("Runtime configuration denied", 403, undefined, "DENIED", "corr-denied")
    );
    renderPage();

    expect(await screen.findByText("Access unavailable")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("corr-denied");
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  it("rolls back older versions and keeps current version disabled", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Version 2")).toBeVisible();
    const rollbackButtons = screen.getAllByRole("button", { name: "Rollback" });
    expect(rollbackButtons.at(1)).toBeDisabled();
    const priorVersionRollback = rollbackButtons.at(0);
    expect(priorVersionRollback).toBeDefined();
    await user.click(priorVersionRollback!);

    await waitFor(() =>
      expect(aiProviderConfigurationService.rollbackRuntimeConfiguration).toHaveBeenCalledWith(
        2,
        "default"
      )
    );
    expect(screen.getByText("publish to version 3")).toBeVisible();
    expect(screen.getByText("corr-audit-1")).toBeVisible();
  });
});
