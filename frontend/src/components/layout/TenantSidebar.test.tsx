import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantSidebar } from "./TenantSidebar";
import type { User } from "@/stores/auth-store";

const mocks = vi.hoisted(() => ({
  useDocumentIntelligenceConfiguration: vi.fn(),
  useRuntimeConfiguration: vi.fn(),
  useTraceabilityCapabilities: vi.fn(),
  getConfigurationSchema: vi.fn(),
  getIntegrationConfiguration: vi.fn(),
}));

vi.mock("@/modules/document_intelligence/hooks/use-document-intelligence-configuration", () => ({
  useDocumentIntelligenceConfiguration: mocks.useDocumentIntelligenceConfiguration,
}));

vi.mock("@/modules/customization_framework/components/useRuntimeConfiguration", () => ({
  useRuntimeConfiguration: mocks.useRuntimeConfiguration,
}));

vi.mock("@/modules/blockchain_traceability/hooks/use-traceability-configuration", () => ({
  useTraceabilityCapabilities: mocks.useTraceabilityCapabilities,
}));

vi.mock("@/modules/api_management/services/api_management-service", () => ({
  api_managementService: { getConfigurationSchema: mocks.getConfigurationSchema },
}));

vi.mock("@/modules/integration_platform/services/integration-platform-service", () => ({
  integrationPlatformService: { getConfiguration: mocks.getIntegrationConfiguration },
}));

const tenantAdmin: User = {
  id: "user-1",
  email: "admin@buildworks.ai",
  username: "admin",
  is_staff: false,
  is_superuser: false,
  tenant_id: "tenant-1",
  platform_role: null,
  tenant_role: "tenant_admin",
};

function renderSidebar(initialPath = "/fixed-assets/assets") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["integration-platform", "configuration"], { document: {} });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TenantSidebar user={tenantAdmin} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TenantSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useDocumentIntelligenceConfiguration.mockReturnValue({ data: { document: {} } });
    mocks.useRuntimeConfiguration.mockReturnValue({ data: { document: {} } });
    mocks.useTraceabilityCapabilities.mockReturnValue({ data: { document: {} } });
    mocks.getConfigurationSchema.mockReturnValue(new Promise(() => undefined));
    mocks.getIntegrationConfiguration.mockReturnValue(new Promise(() => undefined));
  });

  it("keeps registered module navigation available when optional configuration payloads lack ui sections", () => {
    renderSidebar();

    expect(screen.getByRole("button", { name: /fixed assets/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^assets$/i })).toHaveAttribute(
      "href",
      "/fixed-assets/assets"
    );
    expect(screen.getByText("Admin Access")).toBeInTheDocument();
  });
});
