import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MarketplaceComparisonPage } from "../pages/MarketplaceComparisonPage";

describe("MarketplaceComparisonPage", () => {
  it("renders included and locked capabilities side by side", () => {
    render(
      <MemoryRouter>
        <MarketplaceComparisonPage />
      </MemoryRouter>
    );

    const table = screen.getByRole("table", {
      name: /compare included and paid SARAISE capabilities/i,
    });
    const freeRow = within(table).getByRole("row", { name: /Workflow Automation/i });
    const paidRow = within(table).getByRole("row", { name: /Manufacturing Operations/i });

    expect(within(freeRow).getByText("Available")).toBeVisible();
    expect(within(paidRow).getByText("Upgrade required")).toBeVisible();
    expect(within(paidRow).getByLabelText("Available")).toBeVisible();
  });
});
