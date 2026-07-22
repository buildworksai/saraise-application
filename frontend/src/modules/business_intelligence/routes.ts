import { lazy } from "react";
import { Activity, BarChart3, Database, FileBarChart, Search } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
const MODULE = "business_intelligence";
const modes = ["development", "self-hosted", "saas"] as const;
const contextual = (parentRouteId: string) => ({ type: "contextual" as const, parentRouteId });
export const tenantRoutes = [
  {
    id: "business_intelligence.datasets",
    module: MODULE,
    path: "/business-intelligence/datasets",
    sourceFile: "modules/business_intelligence/pages/DatasetCatalogPage.tsx",
    Page: lazy(() =>
      import("./pages/DatasetCatalogPage").then((m) => ({ default: m.DatasetCatalogPage }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Datasets", icon: Database, order: 500 },
  },
  {
    id: "business_intelligence.dashboards.list",
    module: MODULE,
    path: "/business-intelligence/dashboards",
    sourceFile: "modules/business_intelligence/pages/DashboardListPage.tsx",
    Page: lazy(() =>
      import("./pages/DashboardListPage").then((m) => ({ default: m.DashboardListPage }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Dashboards", icon: BarChart3, order: 510 },
  },
  {
    id: "business_intelligence.dashboards.create",
    module: MODULE,
    path: "/business-intelligence/dashboards/new",
    sourceFile: "modules/business_intelligence/pages/CreateDashboardPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateDashboardPage").then((m) => ({ default: m.CreateDashboardPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.dashboards.list"),
  },
  {
    id: "business_intelligence.dashboards.detail",
    module: MODULE,
    path: "/business-intelligence/dashboards/:id",
    sourceFile: "modules/business_intelligence/pages/DashboardDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/DashboardDetailPage").then((m) => ({ default: m.DashboardDetailPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.dashboards.list"),
  },
  {
    id: "business_intelligence.dashboards.edit",
    module: MODULE,
    path: "/business-intelligence/dashboards/:id/edit",
    sourceFile: "modules/business_intelligence/pages/EditDashboardPage.tsx",
    Page: lazy(() =>
      import("./pages/EditDashboardPage").then((m) => ({ default: m.EditDashboardPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.dashboards.list"),
  },
  {
    id: "business_intelligence.reports.list",
    module: MODULE,
    path: "/business-intelligence/reports",
    sourceFile: "modules/business_intelligence/pages/ReportListPage.tsx",
    Page: lazy(() => import("./pages/ReportListPage").then((m) => ({ default: m.ReportListPage }))),
    modes,
    navigation: { type: "sidebar", label: "Reports", icon: FileBarChart, order: 520 },
  },
  {
    id: "business_intelligence.reports.create",
    module: MODULE,
    path: "/business-intelligence/reports/new",
    sourceFile: "modules/business_intelligence/pages/CreateReportPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateReportPage").then((m) => ({ default: m.CreateReportPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.reports.list"),
  },
  {
    id: "business_intelligence.reports.detail",
    module: MODULE,
    path: "/business-intelligence/reports/:id",
    sourceFile: "modules/business_intelligence/pages/ReportDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/ReportDetailPage").then((m) => ({ default: m.ReportDetailPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.reports.list"),
  },
  {
    id: "business_intelligence.reports.edit",
    module: MODULE,
    path: "/business-intelligence/reports/:id/edit",
    sourceFile: "modules/business_intelligence/pages/EditReportPage.tsx",
    Page: lazy(() => import("./pages/EditReportPage").then((m) => ({ default: m.EditReportPage }))),
    modes,
    navigation: contextual("business_intelligence.reports.list"),
  },
  {
    id: "business_intelligence.queries.list",
    module: MODULE,
    path: "/business-intelligence/queries",
    sourceFile: "modules/business_intelligence/pages/QueryListPage.tsx",
    Page: lazy(() => import("./pages/QueryListPage").then((m) => ({ default: m.QueryListPage }))),
    modes,
    navigation: { type: "sidebar", label: "Queries", icon: Search, order: 530 },
  },
  {
    id: "business_intelligence.queries.create",
    module: MODULE,
    path: "/business-intelligence/queries/new",
    sourceFile: "modules/business_intelligence/pages/CreateQueryPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateQueryPage").then((m) => ({ default: m.CreateQueryPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.queries.list"),
  },
  {
    id: "business_intelligence.queries.detail",
    module: MODULE,
    path: "/business-intelligence/queries/:id",
    sourceFile: "modules/business_intelligence/pages/QueryDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/QueryDetailPage").then((m) => ({ default: m.QueryDetailPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.queries.list"),
  },
  {
    id: "business_intelligence.queries.edit",
    module: MODULE,
    path: "/business-intelligence/queries/:id/edit",
    sourceFile: "modules/business_intelligence/pages/EditQueryPage.tsx",
    Page: lazy(() => import("./pages/EditQueryPage").then((m) => ({ default: m.EditQueryPage }))),
    modes,
    navigation: contextual("business_intelligence.queries.list"),
  },
  {
    id: "business_intelligence.executions.list",
    module: MODULE,
    path: "/business-intelligence/executions",
    sourceFile: "modules/business_intelligence/pages/ExecutionListPage.tsx",
    Page: lazy(() =>
      import("./pages/ExecutionListPage").then((m) => ({ default: m.ExecutionListPage }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Executions", icon: Activity, order: 540 },
  },
  {
    id: "business_intelligence.executions.detail",
    module: MODULE,
    path: "/business-intelligence/executions/:id",
    sourceFile: "modules/business_intelligence/pages/ExecutionDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/ExecutionDetailPage").then((m) => ({ default: m.ExecutionDetailPage }))
    ),
    modes,
    navigation: contextual("business_intelligence.executions.list"),
  },
] satisfies readonly TenantRoute[];
export default tenantRoutes;
