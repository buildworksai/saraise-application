import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantDetailPage } from "./TenantDetailPage";
import { tenantService, type Tenant } from "../services/tenant-service";
import type { TenantHealthScore, TenantModule, TenantResourceUsage } from "../contracts";

const navigate = vi.fn();

vi.mock("../services/tenant-service", () => ({
  tenantService: {
    tenants: {
      get: vi.fn(),
      getModules: vi.fn(),
      getResourceUsage: vi.fn(),
      getHealthScores: vi.fn(),
    },
  },
}));

vi.mock("react-router-dom", async () => ({
  ...(await vi.importActual("react-router-dom")),
  useNavigate: () => navigate,
  useParams: () => ({ id: "tenant-1" }),
}));

const tenant = {
  id: "tenant-1",
  name: "Northwind Manufacturing",
  slug: "northwind",
  status: "active",
  subdomain: "northwind",
  custom_domain: "erp.northwind.example",
  primary_contact_email: "owner@northwind.example",
  primary_contact_name: "Ada Lovelace",
  primary_contact_phone: "+1-555-0100",
  billing_email: "billing@northwind.example",
  technical_email: "ops@northwind.example",
} as Tenant;

const modules = [
  {
    id: "module-enabled",
    module_name: "Accounting",
    is_enabled: true,
    version: "2026.8",
  },
  {
    id: "module-disabled",
    module_name: "Warehouse",
    is_enabled: false,
  },
] as TenantModule[];

const resourceUsage = [
  {
    id: "usage-1",
    date: "2026-08-01",
    api_calls: 1200,
    storage_used_gb: "48.5",
    active_users: 42,
  },
] as TenantResourceUsage[];

const healthScores = [
  {
    id: "score-1",
    date: "2026-08-01",
    overall_score: 93,
    usage_score: 91,
    performance_score: 95,
    error_score: 99,
    churn_risk: "3.5",
  },
] as TenantHealthScore[];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TenantDetailPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TenantDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tenantService.tenants.get).mockResolvedValue(tenant);
    vi.mocked(tenantService.tenants.getModules).mockResolvedValue(modules);
    vi.mocked(tenantService.tenants.getResourceUsage).mockResolvedValue(resourceUsage);
    vi.mocked(tenantService.tenants.getHealthScores).mockResolvedValue(healthScores);
  });

  it("renders tenant identity, contacts, modules, usage, and health evidence", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Northwind Manufacturing" })).toBeVisible();
    expect(screen.getAllByText("northwind")).toHaveLength(3);
    expect(screen.getByText("erp.northwind.example")).toBeVisible();
    expect(screen.getByText("owner@northwind.example")).toBeVisible();
    expect(screen.getByText("Ada Lovelace")).toBeVisible();
    expect(screen.getByText("+1-555-0100")).toBeVisible();
    expect(screen.getByText("billing@northwind.example")).toBeVisible();
    expect(screen.getByText("ops@northwind.example")).toBeVisible();

    const modulesRegion = screen.getByRole("heading", { name: "Modules (2)" }).closest("div");
    expect(modulesRegion).not.toBeNull();
    expect(screen.getByText("Accounting")).toBeVisible();
    expect(screen.getByText("Enabled")).toBeVisible();
    expect(screen.getByText("Version: 2026.8")).toBeVisible();
    expect(screen.getByText("Warehouse")).toBeVisible();
    expect(screen.getByText("Disabled")).toBeVisible();

    const usageRow = screen.getByRole("row", { name: /2026-08-01 1200 48.5 42/u });
    expect(within(usageRow).getByText("1200")).toBeVisible();

    const healthRow = screen.getByRole("row", { name: /2026-08-01 93 91 95 99 3.5%/u });
    expect(within(healthRow).getByText("3.5%")).toBeVisible();
  });

  it("navigates back to the tenant list from the governed detail header", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /back to tenants/i }));
    expect(navigate).toHaveBeenCalledWith("/tenant-management");
  });

  it("renders empty module state while hiding optional telemetry sections", async () => {
    vi.mocked(tenantService.tenants.get).mockResolvedValue({
      id: "tenant-empty",
      name: "Trial Tenant",
      slug: "trial",
      status: "trial",
    } as Tenant);
    vi.mocked(tenantService.tenants.getModules).mockResolvedValue([]);
    vi.mocked(tenantService.tenants.getResourceUsage).mockResolvedValue([]);
    vi.mocked(tenantService.tenants.getHealthScores).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByRole("heading", { name: "Trial Tenant" })).toBeVisible();
    expect(screen.getByText("No modules installed")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Resource Usage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Health Scores" })).not.toBeInTheDocument();
  });

  it("renders a retryable error when tenant loading fails", async () => {
    vi.mocked(tenantService.tenants.get).mockRejectedValue(new Error("tenant unavailable"));

    renderPage();

    expect(
      await screen.findByText("Failed to load tenant. Please check your connection and try again.")
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(tenantService.tenants.get).toHaveBeenCalledTimes(2);
  });
});
