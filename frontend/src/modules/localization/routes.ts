import { lazy } from "react";
import { Globe2, Languages, Plus } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const parentRouteId = "localization.resources.list";

export const tenantRoutes = [
  {
    id: parentRouteId,
    module: "localization",
    path: "/localization",
    title: "Localization",
    sourceFile: "modules/localization/pages/LocalizationListPage.tsx",
    Page: lazy(() =>
      import("./pages/LocalizationListPage").then(({ LocalizationListPage }) => ({
        default: LocalizationListPage,
      }))
    ),
    modes,
    navigation: {
      type: "sidebar",
      label: "Localization resources",
      icon: Languages,
      order: 140,
    },
  },
  {
    id: "localization.resources.create",
    module: "localization",
    path: "/localization/create",
    title: "Create localization resource",
    sourceFile: "modules/localization/pages/CreateLocalizationResourcePage.tsx",
    Page: lazy(() =>
      import("./pages/CreateLocalizationResourcePage").then(
        ({ CreateLocalizationResourcePage }) => ({
          default: CreateLocalizationResourcePage,
        })
      )
    ),
    modes,
    navigation: { type: "contextual", parentRouteId, label: "Create resource", icon: Plus },
  },
  {
    id: "localization.resources.legacy-create",
    module: "localization",
    path: "/localization/new",
    title: "Create localization resource",
    sourceFile: "modules/localization/pages/CreateLocalizationResourcePage.tsx",
    Page: lazy(() =>
      import("./pages/CreateLocalizationResourcePage").then(
        ({ CreateLocalizationResourcePage }) => ({
          default: CreateLocalizationResourcePage,
        })
      )
    ),
    modes,
    navigation: { type: "contextual", parentRouteId, label: "Create resource", icon: Plus },
  },
  {
    id: "localization.resources.detail",
    module: "localization",
    path: "/localization/:id",
    title: "Localization detail",
    sourceFile: "modules/localization/pages/LocalizationDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/LocalizationDetailPage").then(({ LocalizationDetailPage }) => ({
        default: LocalizationDetailPage,
      }))
    ),
    modes,
    navigation: { type: "contextual", parentRouteId, icon: Globe2 },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
