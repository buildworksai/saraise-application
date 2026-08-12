import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantListPage } from "./TenantListPage";
import { tenantService, type Tenant } from "../services/tenant-service";

const navigate = vi.fn();

vi.mock("../services/tenant-service", () => ({
  tenantService: {
    tenants: {
      list: vi.fn(),
    },
  },
}));

vi.mock("react-router-dom", async () => ({
  ...(await vi.importActual("react-router-dom")),
  useNavigate: () => navigate,
}));

const tenants: Tenant[] = [
  {
    id: "tenant-1",
    name: "Northwind Manufacturing",
    slug: "northwind",
    status: "active",
    primary_contact_email: "owner@northwind.example",
    industry: "Manufacturing",
    company_size: "201-500",
    created_at: "2026-08-01T00:00:00Z",
  } as Tenant,
  {
    id: "tenant-2",
    name: "Contoso Retail",
    slug: "contoso",
    status: "trial",
    primary_contact_email: "admin@contoso.example",
    industry: "Retail",
    company_size: "51-200",
    created_at: "2026-08-02T00:00:00Z",
  } as Tenant,
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TenantListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TenantListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tenantService.tenants.list).mockResolvedValue(tenants);
  });

  it("renders tenant cards with operational evidence and navigates to tenant detail", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Tenant Management" })).toBeVisible();
    expect(screen.getByText("Northwind Manufacturing")).toBeVisible();
    expect(screen.getByText("owner@northwind.example")).toBeVisible();
    expect(screen.getByText("Manufacturing")).toBeVisible();
    expect(screen.getByText("201-500")).toBeVisible();
    fireEvent.click(screen.getByText("Northwind Manufacturing").closest(".cursor-pointer")!);

    expect(navigate).toHaveBeenCalledWith("/tenant-management/tenant-1");
  });

  it("passes search filter payloads to the tenant service", async () => {
    renderPage();

    expect(await screen.findByText("Northwind Manufacturing")).toBeVisible();
    fireEvent.change(screen.getByPlaceholderText("Search tenants by name, slug, or email..."), {
      target: { value: "northwind" },
    });

    await waitFor(() =>
      expect(tenantService.tenants.list).toHaveBeenLastCalledWith({
        status: undefined,
        search: "northwind",
      })
    );
  });

  it("renders the filtered empty state without a local create escape hatch", async () => {
    vi.mocked(tenantService.tenants.list).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No tenants yet")).toBeVisible();
    expect(
      screen.getByText("No tenants found. Tenants must be created via the Control Plane.")
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /create/i })).not.toBeInTheDocument();
  });

  it("renders retryable load failures and refetches through the query client", async () => {
    vi.mocked(tenantService.tenants.list).mockRejectedValueOnce(new Error("tenant api down"));
    renderPage();

    expect(
      await screen.findByText("Failed to load tenants. Please check your connection and try again.")
    ).toBeVisible();
    vi.mocked(tenantService.tenants.list).mockResolvedValueOnce(tenants);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(tenantService.tenants.list).toHaveBeenCalledTimes(2));
  });
});
