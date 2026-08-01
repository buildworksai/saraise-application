import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type React from "react";
import { MemoryRouter } from "react-router-dom";
import { ApiError } from "@/services/api-client";
import {
  InventoryEmpty,
  InventoryErrorState,
  InventorySkeleton,
} from "../../components/GovernedStates";
import {
  ItemCreatePage,
  ReservationCreatePage,
  StockEntryCreatePage,
  WarehouseCreatePage,
} from "../InventoryPages";

function renderInventoryPage(children: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("inventory governed states", () => {
  it("renders an accessible skeleton", () => {
    render(<InventorySkeleton label="Loading balances" />);
    expect(screen.getByRole("status", { name: "Loading balances" })).toBeInTheDocument();
  });

  it("fails closed for 403 and surfaces correlation evidence without retry", () => {
    render(
      <InventoryErrorState
        error={new ApiError("denied", 403, undefined, "forbidden", "corr-denied")}
        onRetry={vi.fn()}
      />
    );
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("does not disclose whether a 404 belongs to another tenant", () => {
    render(<InventoryErrorState error={new ApiError("secret object detail", 404)} />);
    expect(screen.getByText("Inventory record unavailable")).toBeInTheDocument();
    expect(screen.queryByText("secret object detail")).not.toBeInTheDocument();
  });

  it("offers retry only for retryable failures", () => {
    const retry = vi.fn();
    render(
      <InventoryErrorState
        error={new ApiError("temporarily unavailable", 503, undefined, "unavailable", "corr-retry")}
        onRetry={retry}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("gives empty states a valid next action", () => {
    const action = vi.fn();
    render(
      <InventoryEmpty
        title="No warehouses"
        detail="Create one."
        action={{ label: "Create warehouse", onClick: action }}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Create warehouse" }));
    expect(action).toHaveBeenCalledOnce();
  });

  it("marks inventory create pages with native required constraints", () => {
    const { container, unmount } = renderInventoryPage(<WarehouseCreatePage />);

    expect(container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Warehouse code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Warehouse name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Warehouse type/u)).toBeRequired();
    expect(screen.getByLabelText(/^Country code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Timezone/u)).toBeRequired();

    unmount();
    const item = renderInventoryPage(<ItemCreatePage />);

    expect(item.container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Item code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Item code/u)).not.toHaveAttribute("min");
    expect(screen.getByLabelText(/^Item name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Base unit of measure/u)).toBeRequired();
    expect(screen.getByLabelText(/^Tracking mode/u)).toBeRequired();
    expect(screen.getByLabelText(/^Valuation method/u)).toBeRequired();

    item.unmount();
    const stockEntry = renderInventoryPage(<StockEntryCreatePage />);

    expect(screen.getByLabelText(/^Quantity/u)).toBeRequired();
    expect(screen.getByLabelText(/^Quantity/u)).toHaveAttribute("min", "0.000001");
    expect(screen.getByLabelText(/^Entry number/u)).not.toHaveAttribute("min");
    expect(screen.getByLabelText(/^Unit cost/u)).not.toHaveAttribute("min");

    stockEntry.unmount();
    const reservation = renderInventoryPage(<ReservationCreatePage />);

    expect(reservation.container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Quantity/u)).toBeRequired();
    expect(screen.getByLabelText(/^Quantity/u)).toHaveAttribute("min", "0.000001");
  });
});
