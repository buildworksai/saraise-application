import { AreaChart, BarChart, LineChart, PieChart, Sparkline } from "@/components/charts";
import * as marketplace from "../index";
import { tenantRoutes } from "../routes";

describe("marketplace barrel exports", () => {
  it("exposes the catalog contracts, routes, and display components", () => {
    expect(tenantRoutes.map((route) => route.id)).toEqual([
      "marketplace.catalog",
      "marketplace.compare",
      "marketplace.capability.detail",
    ]);
    expect(marketplace.BUILT_IN_CAPABILITIES.length).toBeGreaterThan(0);
    expect(marketplace.MarketplacePage).toEqual(expect.any(Function));
    expect(marketplace.MarketplaceComparisonPage).toEqual(expect.any(Function));
    expect(marketplace.CapabilityDetailPage).toEqual(expect.any(Function));
    expect(marketplace.CapabilityCard).toEqual(expect.any(Function));
    expect(marketplace.ComparisonView).toEqual(expect.any(Function));
    expect(marketplace.TrialEntry).toEqual(expect.any(Function));
    expect(marketplace.UpgradePrompt).toEqual(expect.any(Function));
  });
});

describe("chart barrel exports", () => {
  it("exposes every chart component through the shared index", () => {
    expect([LineChart, BarChart, PieChart, AreaChart, Sparkline]).toEqual([
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    ]);
  });
});
