import { lazy } from "react";
import { Building2, Eye } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const parentRouteId = "tenant-management.tenants.list";

export const tenantRoutes = [
  {
    id: parentRouteId,
    module: "tenant_management",
    path: "/tenant-management",
    title: "Tenant management",
    sourceFile: "modules/tenant_management/pages/TenantListPage.tsx",
    Page: lazy(() =>
      import("./pages/TenantListPage").then(({ TenantListPage }) => ({ default: TenantListPage }))
    ),
    modes,
    navigation: {
      type: "sidebar",
      label: "Tenant directory",
      icon: Building2,
      order: 120,
    },
  },
  {
    id: "tenant-management.tenants.detail",
    module: "tenant_management",
    path: "/tenant-management/:id",
    title: "Tenant detail",
    sourceFile: "modules/tenant_management/pages/TenantDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/TenantDetailPage").then(({ TenantDetailPage }) => ({
        default: TenantDetailPage,
      }))
    ),
    modes,
    navigation: { type: "contextual", parentRouteId, label: "Tenant detail", icon: Eye },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
