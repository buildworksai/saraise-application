import { fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "@/services/api-client";
import { InventoryEmpty, InventoryErrorState, InventorySkeleton } from "../../components/GovernedStates";

describe("inventory governed states", () => {
  it("renders an accessible skeleton", () => {
    render(<InventorySkeleton label="Loading balances" />);
    expect(screen.getByRole("status", { name: "Loading balances" })).toBeInTheDocument();
  });

  it("fails closed for 403 and surfaces correlation evidence without retry", () => {
    render(<InventoryErrorState error={new ApiError("denied", 403, undefined, "forbidden", "corr-denied")} onRetry={vi.fn()} />);
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
    render(<InventoryErrorState error={new ApiError("temporarily unavailable", 503, undefined, "unavailable", "corr-retry")} onRetry={retry} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("gives empty states a valid next action", () => {
    const action = vi.fn();
    render(<InventoryEmpty title="No warehouses" detail="Create one." action={{ label: "Create warehouse", onClick: action }} />);
    fireEvent.click(screen.getByRole("button", { name: "Create warehouse" }));
    expect(action).toHaveBeenCalledOnce();
  });
});
