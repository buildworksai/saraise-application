import { lazy } from "react";
import { Building2, FolderTree, Gauge, LineChart } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const contextual = (parentRouteId: string) => ({ type: "contextual" as const, parentRouteId });

export const tenantRoutes = [
  {
    id: "fixed_assets.dashboard",
    module: "fixed_assets",
    path: "/fixed-assets/dashboard",
    title: "Fixed assets dashboard",
    sourceFile: "modules/fixed_assets/pages/FixedAssetDashboardPage.tsx",
    Page: lazy(() =>
      import("./pages/FixedAssetDashboardPage").then(({ FixedAssetDashboardPage }) => ({
        default: FixedAssetDashboardPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Dashboard", icon: Gauge, order: 520 },
  },
  {
    id: "fixed_assets.assets.list",
    module: "fixed_assets",
    path: "/fixed-assets/assets",
    title: "Fixed assets",
    sourceFile: "modules/fixed_assets/pages/FixedAssetListPage.tsx",
    Page: lazy(() =>
      import("./pages/FixedAssetListPage").then(({ FixedAssetListPage }) => ({
        default: FixedAssetListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Assets", icon: Building2, order: 521 },
  },
  {
    id: "fixed_assets.assets.create",
    module: "fixed_assets",
    path: "/fixed-assets/assets/new",
    title: "Create fixed asset",
    sourceFile: "modules/fixed_assets/pages/CreateFixedAssetPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateFixedAssetPage").then(({ CreateFixedAssetPage }) => ({
        default: CreateFixedAssetPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.assets.list"),
  },
  {
    id: "fixed_assets.assets.detail",
    module: "fixed_assets",
    path: "/fixed-assets/assets/:id",
    title: "Fixed asset details",
    sourceFile: "modules/fixed_assets/pages/FixedAssetDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/FixedAssetDetailPage").then(({ FixedAssetDetailPage }) => ({
        default: FixedAssetDetailPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.assets.list"),
  },
  {
    id: "fixed_assets.assets.edit",
    module: "fixed_assets",
    path: "/fixed-assets/assets/:id/edit",
    title: "Edit fixed asset",
    sourceFile: "modules/fixed_assets/pages/EditFixedAssetPage.tsx",
    Page: lazy(() =>
      import("./pages/EditFixedAssetPage").then(({ EditFixedAssetPage }) => ({
        default: EditFixedAssetPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.assets.list"),
  },
  {
    id: "fixed_assets.categories.list",
    module: "fixed_assets",
    path: "/fixed-assets/categories",
    title: "Asset categories",
    sourceFile: "modules/fixed_assets/pages/AssetCategoryListPage.tsx",
    Page: lazy(() =>
      import("./pages/AssetCategoryListPage").then(({ AssetCategoryListPage }) => ({
        default: AssetCategoryListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Categories", icon: FolderTree, order: 522 },
  },
  {
    id: "fixed_assets.categories.create",
    module: "fixed_assets",
    path: "/fixed-assets/categories/new",
    title: "Create asset category",
    sourceFile: "modules/fixed_assets/pages/CreateAssetCategoryPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateAssetCategoryPage").then(({ CreateAssetCategoryPage }) => ({
        default: CreateAssetCategoryPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.categories.list"),
  },
  {
    id: "fixed_assets.categories.detail",
    module: "fixed_assets",
    path: "/fixed-assets/categories/:id",
    title: "Asset category details",
    sourceFile: "modules/fixed_assets/pages/AssetCategoryDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/AssetCategoryDetailPage").then(({ AssetCategoryDetailPage }) => ({
        default: AssetCategoryDetailPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.categories.list"),
  },
  {
    id: "fixed_assets.categories.edit",
    module: "fixed_assets",
    path: "/fixed-assets/categories/:id/edit",
    title: "Edit asset category",
    sourceFile: "modules/fixed_assets/pages/EditAssetCategoryPage.tsx",
    Page: lazy(() =>
      import("./pages/EditAssetCategoryPage").then(({ EditAssetCategoryPage }) => ({
        default: EditAssetCategoryPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.categories.list"),
  },
  {
    id: "fixed_assets.schedules.list",
    module: "fixed_assets",
    path: "/fixed-assets/depreciation-schedules",
    title: "Depreciation schedules",
    sourceFile: "modules/fixed_assets/pages/DepreciationScheduleListPage.tsx",
    Page: lazy(() =>
      import("./pages/DepreciationScheduleListPage").then(({ DepreciationScheduleListPage }) => ({
        default: DepreciationScheduleListPage,
      }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Depreciation schedules", icon: LineChart, order: 523 },
  },
  {
    id: "fixed_assets.schedules.create",
    module: "fixed_assets",
    path: "/fixed-assets/depreciation-schedules/new",
    title: "Create depreciation schedule",
    sourceFile: "modules/fixed_assets/pages/CreateDepreciationSchedulePage.tsx",
    Page: lazy(() =>
      import("./pages/CreateDepreciationSchedulePage").then(
        ({ CreateDepreciationSchedulePage }) => ({ default: CreateDepreciationSchedulePage })
      )
    ),
    modes,
    navigation: contextual("fixed_assets.schedules.list"),
  },
  {
    id: "fixed_assets.schedules.detail",
    module: "fixed_assets",
    path: "/fixed-assets/depreciation-schedules/:id",
    title: "Depreciation schedule details",
    sourceFile: "modules/fixed_assets/pages/DepreciationScheduleDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/DepreciationScheduleDetailPage").then(
        ({ DepreciationScheduleDetailPage }) => ({ default: DepreciationScheduleDetailPage })
      )
    ),
    modes,
    navigation: contextual("fixed_assets.schedules.list"),
  },
  {
    id: "fixed_assets.schedules.edit",
    module: "fixed_assets",
    path: "/fixed-assets/depreciation-schedules/:id/edit",
    title: "Edit depreciation schedule",
    sourceFile: "modules/fixed_assets/pages/EditDepreciationSchedulePage.tsx",
    Page: lazy(() =>
      import("./pages/EditDepreciationSchedulePage").then(({ EditDepreciationSchedulePage }) => ({
        default: EditDepreciationSchedulePage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.schedules.list"),
  },
  {
    id: "fixed_assets.lines.detail",
    module: "fixed_assets",
    path: "/fixed-assets/depreciation-lines/:id",
    title: "Depreciation line details",
    sourceFile: "modules/fixed_assets/pages/DepreciationLineDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/DepreciationLineDetailPage").then(({ DepreciationLineDetailPage }) => ({
        default: DepreciationLineDetailPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.schedules.list"),
  },
  {
    id: "fixed_assets.transactions.detail",
    module: "fixed_assets",
    path: "/fixed-assets/transactions/:id",
    title: "Asset transaction details",
    sourceFile: "modules/fixed_assets/pages/AssetTransactionDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/AssetTransactionDetailPage").then(({ AssetTransactionDetailPage }) => ({
        default: AssetTransactionDetailPage,
      }))
    ),
    modes,
    navigation: contextual("fixed_assets.assets.list"),
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
