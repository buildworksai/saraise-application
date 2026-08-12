/* eslint-disable max-lines-per-function -- provider console workflow coverage requires complete governed fixtures. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AiProviderConfigurationListPage } from "../AiProviderConfigurationListPage";
import { aiProviderConfigurationService } from "../../services/ai_provider_configuration-service";
import type {
  AIModel,
  AIModelDeployment,
  AIProvider,
  AIProviderCredential,
  AIProviderRuntimeConfiguration,
  AIUsageLog,
} from "../../contracts";

vi.mock("../../services/ai_provider_configuration-service");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const provider: AIProvider = {
  id: "provider-1",
  name: "OpenAI",
  provider_type: "openai",
  is_active: true,
  models_count: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const model: AIModel = {
  id: "model-1",
  provider: provider.id,
  provider_name: provider.name,
  provider_type: "openai",
  model_id: "gpt-enterprise",
  display_name: "GPT Enterprise",
  capabilities: ["text", "function_calling"],
  pricing: {},
  max_tokens: 128000,
  is_active: true,
  deployments_count: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const credential: AIProviderCredential = {
  id: "credential-1",
  tenant_id: "tenant-1",
  provider: provider.id,
  provider_name: provider.name,
  provider_type: "openai",
  label: "Primary OpenAI key",
  status: "valid",
  secret_hint: "key-hint-test", // pragma: allowlist secret
  has_secret: true,
  last_verified_at: "2026-01-02T00:00:00Z",
  last_error_code: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};
const deployment: AIModelDeployment = {
  id: "deployment-1",
  tenant_id: "tenant-1",
  model: model.id,
  credential: credential.id,
  deployment_name: "Support primary",
  model_name: model.display_name,
  model_id: model.model_id,
  provider_name: provider.name,
  config: { temperature: 0.2, max_tokens: 4096 },
  status: "active",
  created_by: "operator-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-03T00:00:00Z",
};
const inactiveDeployment: AIModelDeployment = {
  ...deployment,
  id: "deployment-2",
  deployment_name: "Support backup",
  status: "inactive",
};
const errorDeployment: AIModelDeployment = {
  ...deployment,
  id: "deployment-3",
  deployment_name: "Broken deployment",
  status: "error",
};
const usageLog: AIUsageLog = {
  id: "usage-1",
  tenant_id: "tenant-1",
  deployment: deployment.id,
  deployment_name: deployment.deployment_name,
  model_name: model.display_name,
  prompt_tokens: 1250,
  completion_tokens: 750,
  total_tokens: 2000,
  cost: "0.125",
  currency: "USD",
  provider_request_id: "req_123",
  created_at: "2026-01-04T00:00:00Z",
};
const runtimeConfiguration: AIProviderRuntimeConfiguration = {
  id: "runtime-config-1",
  tenant_id: "tenant-1",
  environment: "default",
  version: 1,
  updated_by: "operator-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  values: {
    deployment_policy: {
      default_name: "Default deployment",
      defaults: { temperature: 0.3, max_tokens: 2048 },
      limits: { temperature_min: 0, temperature_max: 1, max_tokens_min: 10, max_tokens_max: 4096 },
    },
    field_limits: { deployment_name_max: 120 },
  },
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AiProviderConfigurationListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AiProviderConfigurationListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiProviderConfigurationService.listProviders).mockResolvedValue([provider]);
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.listModels).mockResolvedValue([model]);
    vi.mocked(aiProviderConfigurationService.listDeployments).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.listUsageLogs).mockResolvedValue([]);
    vi.mocked(aiProviderConfigurationService.getHealth).mockResolvedValue({ status: "healthy" });
    vi.mocked(aiProviderConfigurationService.getRuntimeConfiguration).mockResolvedValue(
      runtimeConfiguration
    );
  });

  it("renders the provider catalog and tenant metrics", async () => {
    renderPage();
    expect(
      screen.getByRole("status", { name: /loading ai provider configuration/i })
    ).toBeInTheDocument();
    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Connected credentials")).toBeInTheDocument();
    expect(screen.getByText("Service healthy")).toBeInTheDocument();
  });

  it("supports resource tabs, empty states, and catalog search", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("OpenAI");
    await user.type(screen.getByRole("textbox", { name: /search providers/i }), "missing");
    expect(screen.getByText("No matching providers")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Credentials" }));
    expect(screen.getByText("No credentials connected")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Usage" }));
    expect(screen.getByText("No usage recorded")).toBeInTheDocument();
  });

  it("shows a retryable error without fabricating empty data", async () => {
    vi.mocked(aiProviderConfigurationService.listProviders).mockRejectedValue(new Error("offline"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Provider configuration unavailable"
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(aiProviderConfigurationService.listProviders).toHaveBeenCalledTimes(1)
    );
  });

  it("archives credentials through confirmation and filters credential search", async () => {
    const user = userEvent.setup();
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([credential]);
    vi.mocked(aiProviderConfigurationService.deleteCredential).mockResolvedValue(undefined);
    renderPage();

    await user.click(await screen.findByRole("tab", { name: "Credentials" }));
    expect(screen.getByText("Primary OpenAI key")).toBeInTheDocument();
    expect(screen.getByText(/key-hint-test/u)).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: /search credentials/i }), "missing");
    expect(screen.getByText("No credentials connected")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Credentials" }));

    await user.click(await screen.findByRole("button", { name: "Archive Primary OpenAI key" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Archive credential?");
    await user.click(screen.getByRole("button", { name: "Archive" }));

    await waitFor(() =>
      expect(aiProviderConfigurationService.deleteCredential).toHaveBeenCalledWith("credential-1")
    );
  }, 15_000);

  it("activates, pauses, and archives deployments while preserving error deployments fail-closed", async () => {
    const user = userEvent.setup();
    vi.mocked(aiProviderConfigurationService.listDeployments).mockResolvedValue([
      deployment,
      inactiveDeployment,
      errorDeployment,
    ]);
    vi.mocked(aiProviderConfigurationService.activateDeployment).mockResolvedValue(
      inactiveDeployment
    );
    vi.mocked(aiProviderConfigurationService.deactivateDeployment).mockResolvedValue(deployment);
    vi.mocked(aiProviderConfigurationService.deleteDeployment).mockResolvedValue(undefined);
    renderPage();

    await user.click(await screen.findByRole("tab", { name: "Deployments" }));
    expect(screen.getByText("Support primary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
    expect(screen.getAllByRole("button", { name: "Activate" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Activate" })[1]).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() =>
      expect(aiProviderConfigurationService.deactivateDeployment).toHaveBeenCalledWith(
        "deployment-1"
      )
    );

    await user.click(screen.getAllByRole("button", { name: "Activate" })[0]!);
    await waitFor(() =>
      expect(aiProviderConfigurationService.activateDeployment).toHaveBeenCalledWith("deployment-2")
    );

    await user.click(screen.getByRole("button", { name: "Archive Support primary" }));
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(aiProviderConfigurationService.deleteDeployment).toHaveBeenCalledWith("deployment-1")
    );
  }, 15_000);

  it("creates deployments with runtime defaults and only compatible credentials", async () => {
    const user = userEvent.setup();
    vi.mocked(aiProviderConfigurationService.listCredentials).mockResolvedValue([
      credential,
      { ...credential, id: "credential-2", provider: "provider-2", label: "Other provider key" },
    ]);
    vi.mocked(aiProviderConfigurationService.createDeployment).mockResolvedValue(deployment);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "New deployment" }));
    await user.type(screen.getByLabelText("Deployment name"), "  Governed default  ");
    await user.selectOptions(screen.getByLabelText("Model"), "model-1");
    expect(screen.getByRole("option", { name: "Primary OpenAI key" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Other provider key" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Temperature")).toHaveValue(0.3);
    expect(screen.getByLabelText("Maximum output tokens")).toHaveValue(2048);
    await user.selectOptions(screen.getByLabelText("Credential"), "credential-1");
    await user.click(screen.getByRole("button", { name: "Create deployment" }));

    await waitFor(() => expect(aiProviderConfigurationService.createDeployment).toHaveBeenCalled());
    expect(aiProviderConfigurationService.createDeployment).toHaveBeenCalledWith({
      model: "model-1",
      credential: "credential-1",
      deployment_name: "Governed default",
      config: { temperature: 0.3, max_tokens: 2048 },
    });
  }, 15_000);

  it("renders usage totals and health-unavailable evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(aiProviderConfigurationService.listUsageLogs).mockResolvedValue([usageLog]);
    vi.mocked(aiProviderConfigurationService.getHealth).mockRejectedValue(new Error("down"));
    renderPage();

    await waitFor(() => expect(screen.getByText("Health unavailable")).toBeInTheDocument(), {
      timeout: 3_000,
    });
    expect(screen.getByText("2,000")).toBeInTheDocument();
    expect(screen.getByText("$0.125")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Usage" }));
    expect(screen.getByText("req_123")).toBeInTheDocument();
    expect(screen.getByText("1,250")).toBeInTheDocument();
    expect(screen.getByText("750")).toBeInTheDocument();
    expect(screen.getAllByText("$0.125")).toHaveLength(2);
  });
});
