/* eslint-disable max-lines-per-function -- Sidebar inventory tests intentionally cover the rendered navigation contract in cohesive flows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Shield } from "lucide-react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QUERY_KEYS } from "@/modules/api_management/contracts";
import { tenantItems } from "./contracts";
import { TenantSidebar } from "./TenantSidebar";
import { renderTenantItems } from "./sidebar-utils";
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
const originalTenantItemCount = tenantItems.length;

interface SidebarRenderOptions {
  initialPath?: string;
  user?: User;
  documentIntelligenceConfiguration?: unknown;
  customizationConfiguration?: unknown;
  traceabilityCapabilities?: unknown;
  apiManagementSchema?: unknown;
  integrationPlatformConfiguration?: unknown;
}

function renderSidebar({
  initialPath = "/fixed-assets/assets",
  user = tenantAdmin,
  documentIntelligenceConfiguration,
  customizationConfiguration,
  traceabilityCapabilities,
  apiManagementSchema,
  integrationPlatformConfiguration = { document: {} },
}: SidebarRenderOptions = {}) {
  if (documentIntelligenceConfiguration !== undefined) {
    mocks.useDocumentIntelligenceConfiguration.mockReturnValue({
      data: documentIntelligenceConfiguration,
    });
  }
  if (customizationConfiguration !== undefined) {
    mocks.useRuntimeConfiguration.mockReturnValue({ data: customizationConfiguration });
  }
  if (traceabilityCapabilities !== undefined) {
    mocks.useTraceabilityCapabilities.mockReturnValue({ data: traceabilityCapabilities });
  }

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (apiManagementSchema !== undefined) {
    client.setQueryData(QUERY_KEYS.CONFIGURATION_SCHEMA(), apiManagementSchema);
  }
  if (integrationPlatformConfiguration !== undefined) {
    client.setQueryData(
      ["integration-platform", "configuration"],
      integrationPlatformConfiguration
    );
  }

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TenantSidebar user={user} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const tenantUser: User = {
  ...tenantAdmin,
  id: "user-2",
  email: "user@buildworks.ai",
  username: "user",
  tenant_role: "user",
};

function renderSidebarForUser(user: User, initialPath = "/tenant/dashboard") {
  return renderSidebar({ user, initialPath });
}

function expectToRenderBefore(first: HTMLElement, second: HTMLElement) {
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING
  );
}

function getLinkByHref(name: RegExp, href: string): HTMLElement {
  const link = screen
    .getAllByRole("link", { name })
    .find((candidate) => candidate.getAttribute("href") === href);
  if (!link) throw new Error(`Expected ${href} link to be rendered.`);
  return link;
}

describe("TenantSidebar", () => {
  afterEach(() => {
    tenantItems.splice(originalTenantItemCount);
  });

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

    expectToRenderBefore(
      screen.getByRole("button", { name: /blockchain traceability/i }),
      getLinkByHref(/^dashboard$/i, "/tenant/dashboard")
    );
    expect(screen.getByRole("button", { name: /fixed assets/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^assets$/i })).toHaveAttribute(
      "href",
      "/fixed-assets/assets"
    );
    expect(screen.getByText("Admin Access")).toBeInTheDocument();
  });

  it("renders the governed static tenant navigation inventory with stable paths", async () => {
    renderSidebar({ initialPath: "/tenant/dashboard" });

    expect(screen.getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/tenant/dashboard"
    );
    expect(screen.getByRole("link", { name: /workflow automation/i })).toHaveAttribute(
      "href",
      "/workflow-automation/workflows"
    );
    expect(screen.getByRole("link", { name: /document management/i })).toHaveAttribute(
      "href",
      "/dms/documents"
    );

    await userEvent.click(screen.getByRole("button", { name: /regional/i }));
    expect(screen.getByRole("link", { name: /^resources$/i })).toHaveAttribute("href", "/regional");
    expect(screen.getByRole("link", { name: /create resource/i })).toHaveAttribute(
      "href",
      "/regional/create"
    );
    expect(screen.getByRole("link", { name: /^configuration$/i })).toHaveAttribute(
      "href",
      "/regional/configuration"
    );

    await userEvent.click(screen.getByRole("button", { name: /ai providers/i }));
    expect(screen.getByRole("link", { name: /provider console/i })).toHaveAttribute(
      "href",
      "/ai-provider-configuration"
    );
    expect(screen.getByRole("link", { name: /connect credential/i })).toHaveAttribute(
      "href",
      "/ai-provider-configuration/create"
    );
    expect(screen.getByRole("link", { name: /runtime configuration/i })).toHaveAttribute(
      "href",
      "/ai-provider-configuration/runtime-configuration"
    );
    expect(screen.getByRole("link", { name: /secret operations/i })).toHaveAttribute(
      "href",
      "/ai-providers/secrets"
    );
  });

  it("links document management to the governed documents route", () => {
    renderSidebar({ initialPath: "/tenant/dashboard" });

    expect(screen.getByRole("link", { name: /document management/i })).toHaveAttribute(
      "href",
      "/dms/documents"
    );
  });

  it("hides admin-only configuration links for non-admin tenant users", () => {
    renderSidebarForUser(tenantUser);

    expect(screen.queryByText("Admin Access")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /runtime configuration/i })).not.toBeInTheDocument();
  });

  it("renders a non-admin fallback user role when no tenant role is present", () => {
    renderSidebarForUser({ ...tenantUser, tenant_role: null });

    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.queryByText("Admin Access")).not.toBeInTheDocument();
  });

  it("requires the exact tenant_admin role before exposing admin status", () => {
    renderSidebarForUser({ ...tenantAdmin, tenant_role: "tenant_admin " });

    expect(screen.getByText("tenant_admin")).toBeInTheDocument();
    expect(screen.queryByText("Admin Access")).not.toBeInTheDocument();
  });

  it("uses the runtime service query functions when cached schemas are absent", async () => {
    const apiSchemaPromise = Promise.resolve({
      navigation: {
        resources_list: { order: 1 },
        resources_create: { order: 2 },
        resources_detail: { order: 3 },
        configuration: { order: 4 },
      },
    });
    const integrationConfigurationPromise = Promise.resolve({
      document: { navigation: { base_order: 5, route_order: {} } },
    });
    mocks.getConfigurationSchema.mockReturnValue(apiSchemaPromise);
    mocks.getIntegrationConfiguration.mockReturnValue(integrationConfigurationPromise);

    renderSidebar({
      initialPath: "/tenant/dashboard",
      integrationPlatformConfiguration: undefined,
    });

    await waitFor(() => {
      expect(mocks.getConfigurationSchema).toHaveBeenCalledTimes(1);
      expect(mocks.getIntegrationConfiguration).toHaveBeenCalledTimes(1);
    });
  });

  it("keeps the sidebar stable when every runtime query returns no data", () => {
    mocks.useDocumentIntelligenceConfiguration.mockReturnValue({ data: undefined });
    mocks.useRuntimeConfiguration.mockReturnValue({ data: undefined });
    mocks.useTraceabilityCapabilities.mockReturnValue({ data: undefined });

    renderSidebar({
      initialPath: "/tenant/dashboard",
      integrationPlatformConfiguration: undefined,
    });

    expect(screen.getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/tenant/dashboard"
    );
    expect(screen.getByRole("button", { name: /document intelligence/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /api management/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /integration platform/i })).toBeInTheDocument();
  });

  it("keeps the sidebar stable when runtime query data omits document payloads", () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      documentIntelligenceConfiguration: {},
      customizationConfiguration: {},
      traceabilityCapabilities: {},
      integrationPlatformConfiguration: {},
    });

    expect(screen.getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/tenant/dashboard"
    );
    expect(screen.getByRole("button", { name: /document intelligence/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /customization framework/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /integration platform/i })).toBeInTheDocument();
  });

  it("keeps integration navigation on default ordering when the document payload is missing", async () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      integrationPlatformConfiguration: { metadata: { version: 1 } },
    });

    await userEvent.click(screen.getByRole("button", { name: /integration platform/i }));

    expectToRenderBefore(
      screen.getByRole("link", { name: /^configuration$/i }),
      screen.getByRole("link", { name: /^connector catalog$/i })
    );
    expectToRenderBefore(
      screen.getByRole("link", { name: /^connector catalog$/i }),
      screen.getByRole("link", { name: /^data mappings$/i })
    );
    expect(screen.getByRole("link", { name: /^webhooks$/i })).toHaveAttribute(
      "href",
      "/integration-platform/webhooks"
    );
  });

  it("renders top-level links as links and grouped modules as expandable buttons", () => {
    renderSidebar({ initialPath: "/tenant/dashboard" });

    expect(screen.getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/tenant/dashboard"
    );
    expect(screen.queryByRole("button", { name: /^dashboard$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^regional$/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^regional$/i })).not.toBeInTheDocument();
  });

  it("keeps grouped children hidden until the operator expands the section", async () => {
    renderSidebar({ initialPath: "/tenant/dashboard" });

    expect(screen.queryByRole("link", { name: /^resources$/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^regional$/i }));
    expect(screen.getByRole("link", { name: /^resources$/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^regional$/i }));
    expect(screen.queryByRole("link", { name: /^resources$/i })).not.toBeInTheDocument();
  });

  it("renders items with empty child arrays as navigable links", () => {
    tenantItems.push({
      path: "/tenant/empty-child-list",
      label: "Empty Child List",
      icon: Shield,
      children: [],
    });

    renderSidebar({ initialPath: "/tenant/dashboard" });

    expect(screen.getByRole("link", { name: /empty child list/i })).toHaveAttribute(
      "href",
      "/tenant/empty-child-list"
    );
    expect(screen.queryByRole("button", { name: /empty child list/i })).not.toBeInTheDocument();
  });

  it("applies route-active classes only to exact parent dashboard links", () => {
    renderSidebar({ initialPath: "/tenant/dashboard/details" });

    const dashboard = screen.getByRole("link", { name: /^dashboard$/i });
    expect(dashboard).toHaveClass("text-muted-foreground");
    expect(dashboard).not.toHaveClass("bg-deepBlue/50");
  });

  it("renders icons and active styling for active grouped and leaf items", () => {
    renderSidebar({ initialPath: "/asset-management/assets" });

    const fixedAssets = screen.getByRole("button", { name: /asset management/i });
    const assets = screen.getByRole("link", { name: /^asset register$/i });

    expect(fixedAssets).toHaveClass("bg-deepBlue");
    expect(within(fixedAssets).getByText("Asset Management")).toBeInTheDocument();
    expect(fixedAssets.querySelector("svg")).toHaveClass("w-5", "h-5");
    expect(assets).toHaveClass("bg-deepBlue/50", "text-white", "font-medium");
    expect(assets.querySelector("svg")).toHaveClass("w-4", "h-4");
  });

  it("renders nested child groups recursively without flattening their descendants", async () => {
    tenantItems.push({
      path: "/tenant/nested",
      label: "Nested Module",
      icon: Shield,
      children: [
        {
          path: "/tenant/nested/group",
          label: "Nested Group",
          icon: Shield,
          children: [
            {
              path: "/tenant/nested/group/detail",
              label: "Nested Detail",
              icon: Shield,
            },
          ],
        },
      ],
    });

    renderSidebar({ initialPath: "/tenant/dashboard" });

    await userEvent.click(screen.getByRole("button", { name: /nested module/i }));
    expect(screen.getByRole("button", { name: /nested group/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /nested group/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /nested group/i }));
    expect(screen.getByRole("link", { name: /nested detail/i })).toHaveAttribute(
      "href",
      "/tenant/nested/group/detail"
    );
  });

  it("applies configured runtime module ordering before static tenant links", () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      traceabilityCapabilities: { document: { ui: { sidebar_order: -30 } } },
      apiManagementSchema: {
        navigation: {
          resources_list: { order: -10 },
          resources_create: { order: -9 },
          resources_detail: { order: -8 },
          configuration: { order: -7 },
        },
      },
      integrationPlatformConfiguration: {
        document: {
          navigation: {
            base_order: -20,
            route_order: {},
          },
        },
      },
    });

    const traceability = screen.getByRole("button", { name: /blockchain traceability/i });
    const integrationPlatform = screen.getByRole("button", { name: /integration platform/i });
    const apiManagement = screen.getByRole("button", { name: /api management/i });
    const dashboard = screen.getByRole("link", { name: /^dashboard$/i });

    expectToRenderBefore(traceability, integrationPlatform);
    expectToRenderBefore(integrationPlatform, apiManagement);
    expectToRenderBefore(apiManagement, dashboard);
  });

  it("orders document intelligence children from the runtime navigation configuration", async () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      documentIntelligenceConfiguration: {
        document: {
          ui: {
            navigation_order: {
              extractions: 30,
              classifications: 10,
              training: 40,
              templates: 20,
              health: 50,
              configuration: 60,
            },
          },
        },
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /document intelligence/i }));

    const classifications = screen.getByRole("link", { name: /^classifications$/i });
    const templates = screen.getByRole("link", { name: /^templates$/i });
    const extractions = screen.getByRole("link", { name: /^extractions$/i });

    expectToRenderBefore(classifications, templates);
    expectToRenderBefore(templates, extractions);
  });

  it("orders api management children from the query schema navigation map", async () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      apiManagementSchema: {
        navigation: {
          resources_list: { order: 30 },
          resources_create: { order: 10 },
          resources_detail: { order: 40 },
          configuration: { order: 20 },
        },
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /api management/i }));

    const createResource = screen.getByRole("link", { name: /^create resource$/i });
    const configuration = screen.getByRole("link", { name: /^configuration$/i });
    const resources = screen.getByRole("link", { name: /^resources$/i });

    expectToRenderBefore(createResource, configuration);
    expectToRenderBefore(configuration, resources);
  });

  it("leaves api management children renderable when the runtime schema omits a route key", async () => {
    renderSidebar({
      initialPath: "/tenant/dashboard",
      apiManagementSchema: {
        navigation: {
          resources_list: { order: 10 },
        },
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /api management/i }));

    expect(screen.getByRole("link", { name: /^resources$/i })).toHaveAttribute(
      "href",
      "/api-management"
    );
    expect(screen.getByRole("link", { name: /^configuration$/i })).toHaveAttribute(
      "href",
      "/api-management/configuration"
    );
  });

  it("orders customization framework children and keeps active child routes expanded", () => {
    renderSidebar({
      initialPath: "/customization-framework/forms/new",
      customizationConfiguration: {
        document: {
          navigation: {
            fields_order: 30,
            field_values_order: 20,
            forms_order: 10,
            rules_order: 40,
            executions_order: 50,
            configuration_order: 60,
          },
        },
      },
    });

    const forms = screen.getByRole("link", { name: /^forms$/i });
    const createForm = screen.getByRole("link", { name: /^create form$/i });
    const fieldValues = screen.getByRole("link", { name: /^field values$/i });
    const rules = screen.getByRole("link", { name: /^rules$/i });
    const fields = screen.getByRole("link", { name: /^fields$/i });
    const executions = screen.getByRole("link", { name: /^executions$/i });

    expect(createForm).toHaveAttribute("href", "/customization-framework/forms/new");
    expectToRenderBefore(forms, fieldValues);
    expectToRenderBefore(fieldValues, fields);
    expectToRenderBefore(fields, rules);
    expectToRenderBefore(rules, executions);
  });

  it("orders integration platform children from route_order while keeping active routes expanded", () => {
    renderSidebar({
      initialPath: "/integration-platform/connectors",
      integrationPlatformConfiguration: {
        document: {
          navigation: {
            base_order: 0,
            route_order: {
              "integration-platform.webhooks.list": -30,
              "integration-platform.connectors.list": -20,
              "integration-platform.integrations.list": -10,
            },
          },
        },
      },
    });

    const webhooks = screen.getByRole("link", { name: /^webhooks$/i });
    const connectorCatalog = screen.getByRole("link", { name: /^connector catalog$/i });
    const integrations = screen.getByRole("link", { name: /^integrations$/i });

    expect(connectorCatalog).toHaveAttribute("href", "/integration-platform/connectors");
    expectToRenderBefore(webhooks, connectorCatalog);
    expectToRenderBefore(connectorCatalog, integrations);
  });

  it("filters admin-only top-level entries for non-admin users", () => {
    tenantItems.push({
      path: "/tenant/admin-audit",
      label: "Tenant Admin Audit",
      icon: Shield,
      adminOnly: true,
    });

    renderSidebarForUser(tenantUser, "/tenant/dashboard");

    expect(screen.queryByRole("link", { name: /tenant admin audit/i })).not.toBeInTheDocument();
  });

  it("filters admin-only children without dropping visible siblings for non-admin users", () => {
    const rendered = renderTenantItems(tenantItems, [], { isAdmin: false });
    const regional = rendered.find((item) => item.label === "Regional");
    const aiProviders = rendered.find((item) => item.label === "AI Providers");

    expect(regional?.children).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "Resources", path: "/regional" }),
        expect.objectContaining({ label: "Create resource", path: "/regional/create" }),
      ])
    );
    expect(regional?.children?.some((child) => child.label === "Configuration")).toBe(false);
    expect(aiProviders?.children).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "Provider Console",
          path: "/ai-provider-configuration",
        }),
      ])
    );
    expect(aiProviders?.children?.some((child) => child.label === "Runtime Configuration")).toBe(
      false
    );
  });
});
