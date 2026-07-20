import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MarketplacePage } from "../pages/MarketplacePage";
import type { MarketplaceDeployment } from "../contracts";

const CONNECTED_DEPLOYMENT: MarketplaceDeployment = {
  applicationMode: "saas",
  licenseMode: "connected",
};

function renderMarketplace(): void {
  render(
    <MemoryRouter>
      <MarketplacePage deployment={CONNECTED_DEPLOYMENT} />
    </MemoryRouter>
  );
}

describe("MarketplacePage", () => {
  it("lists free and paid capabilities in the same discoverable catalog", () => {
    renderMarketplace();

    expect(screen.getByRole("heading", { name: "Workflow Automation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Manufacturing Operations" })).toBeInTheDocument();
    expect(screen.getAllByText("Included").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Paid · Locked").length).toBeGreaterThan(0);
  });

  it("shows a locked paid feature and its upgrade CTA instead of hiding it", () => {
    renderMarketplace();

    const heading = screen.getByRole("heading", { name: "Manufacturing Operations" });
    const card = heading.closest("[data-access]");
    expect(card).not.toBeNull();
    expect(card).toHaveAttribute("data-access", "locked");
    expect(within(card as HTMLElement).getByText("Paid · Locked")).toBeVisible();
    expect(
      within(card as HTMLElement).getByRole("link", { name: /compare and upgrade/i })
    ).toHaveAttribute("href", "/marketplace/manufacturing-operations");
  });

  it("filters by category without applying entitlement-based visibility", async () => {
    const user = userEvent.setup();
    renderMarketplace();

    await user.click(screen.getByRole("button", { name: "Manufacturing" }));

    expect(screen.getByRole("heading", { name: "Manufacturing Operations" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Workflow Automation" })).not.toBeInTheDocument();
  });
});
