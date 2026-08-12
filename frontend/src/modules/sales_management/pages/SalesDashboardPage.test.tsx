import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SalesDashboardSummary, SalesExtensionCapability } from "../contracts";
import { SalesDashboardPage } from "./SalesDashboardPage";
import { salesService } from "../services/sales-service";

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: {
    dashboard: () => ["sales-management", "dashboard"],
  },
  salesService: {
    getSummary: vi.fn(),
    getCapabilities: vi.fn(),
  },
}));

const summary: SalesDashboardSummary = {
  open_quotations: 7,
  confirmed_orders: 11,
  fulfillment_stages: {
    picking: 3,
    packing: 4,
    shipped: 2,
  },
  recent_deliveries: [
    {
      id: "delivery-1",
      delivery_number: "DN-1001",
      delivery_date: "2026-08-03",
      status: "completed",
    },
    {
      id: "delivery-2",
      delivery_number: "DN-1002",
      delivery_date: "2026-08-04",
      status: "cancelled",
    },
  ],
};

const capabilities: SalesExtensionCapability[] = [
  {
    capability: "inventory_reservation",
    status: "available",
    reason_code: "configured",
    provider_id: "inventory-core",
    provider_version: "2.1.0",
  },
  {
    capability: "tax_quote",
    status: "not_configured",
    reason_code: "missing_credentials",
    provider_id: null,
    provider_version: null,
  },
];

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname}</p>;
}

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/sales-management"]}>
        <Routes>
          <Route path="/sales-management" element={<SalesDashboardPage />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SalesDashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(salesService.getSummary).mockResolvedValue(summary);
    vi.mocked(salesService.getCapabilities).mockResolvedValue(capabilities);
  });

  it("renders the governed loading state while sales summary evidence is pending", () => {
    vi.mocked(salesService.getSummary).mockImplementation(() => new Promise(() => undefined));
    vi.mocked(salesService.getCapabilities).mockImplementation(() => new Promise(() => undefined));

    renderDashboard();

    expect(screen.getByLabelText("Loading sales summary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create quote" })).toHaveAttribute(
      "href",
      "/sales-management/quotations/new"
    );
  });

  it("renders server metrics, fulfillment totals, delivery links, and extension capability evidence", async () => {
    const user = userEvent.setup();
    renderDashboard();

    expect(await screen.findByText("Open quotations")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Confirmed orders")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("In fulfillment")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getAllByText("Recent deliveries")).toHaveLength(2);
    expect(screen.getAllByText("2")).toHaveLength(2);

    expect(screen.getByText("picking")).toBeInTheDocument();
    expect(screen.getByText("packing")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "DN-1001" })).toHaveAttribute(
      "href",
      "/sales-management/deliveries/delivery-1"
    );
    expect(screen.getByText("inventory reservation")).toBeInTheDocument();
    expect(screen.getByText("Reason: configured")).toBeInTheDocument();
    expect(screen.getByText("Provider: inventory-core 2.1.0")).toBeInTheDocument();
    expect(screen.getByText("tax quote")).toBeInTheDocument();
    expect(screen.getByText("Reason: missing_credentials")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Create order/iu }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/sales-management/sales-orders/new"
    );
  });

  it("keeps empty server sections explicit instead of fabricating zero capability data", async () => {
    vi.mocked(salesService.getSummary).mockResolvedValue({
      ...summary,
      fulfillment_stages: {},
      recent_deliveries: [],
    });
    vi.mocked(salesService.getCapabilities).mockResolvedValue([]);

    renderDashboard();

    expect(await screen.findByText("No orders are currently in fulfillment.")).toBeInTheDocument();
    expect(screen.getByText("No recent deliveries.")).toBeInTheDocument();
    expect(
      screen.getByText("The server reported no optional extension capabilities.")
    ).toBeInTheDocument();
  });

  it("fails closed and retries both dashboard queries when either governed response fails", async () => {
    const user = userEvent.setup();
    vi.mocked(salesService.getSummary)
      .mockRejectedValueOnce(new Error("summary unavailable"))
      .mockResolvedValue(summary);

    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Sales data unavailable");
    await user.click(screen.getByRole("button", { name: /try again/iu }));

    await waitFor(() => expect(salesService.getSummary).toHaveBeenCalledTimes(2));
    expect(salesService.getCapabilities).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Open quotations")).toBeInTheDocument();
  });
});
