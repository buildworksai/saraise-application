import { lazy } from "react";
import { Store } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
import { ENDPOINTS } from "./contracts";

export const tenantRoutes = [
  {
    id: "marketplace.catalog",
    module: "marketplace",
    path: ENDPOINTS.MARKETPLACE.LIST,
    sourceFile: "features/marketplace/pages/MarketplacePage.tsx",
    Page: lazy(() =>
      import("./pages/MarketplacePage").then(({ MarketplacePage }) => ({
        default: MarketplacePage,
      }))
    ),
    navigation: { type: "sidebar", label: "Marketplace", icon: Store, order: 9000 },
  },
  {
    id: "marketplace.compare",
    module: "marketplace",
    path: ENDPOINTS.MARKETPLACE.COMPARE,
    sourceFile: "features/marketplace/pages/MarketplaceComparisonPage.tsx",
    Page: lazy(() =>
      import("./pages/MarketplaceComparisonPage").then(({ MarketplaceComparisonPage }) => ({
        default: MarketplaceComparisonPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "marketplace.catalog" },
  },
  {
    id: "marketplace.capability.detail",
    module: "marketplace",
    path: ENDPOINTS.MARKETPLACE.DETAIL_PATTERN,
    sourceFile: "features/marketplace/pages/CapabilityDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/CapabilityDetailPage").then(({ CapabilityDetailPage }) => ({
        default: CapabilityDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "marketplace.catalog" },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
