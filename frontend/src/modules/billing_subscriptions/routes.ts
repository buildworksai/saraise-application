import { lazy } from "react";
import { Gauge, Plus, ReceiptText } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const parentRouteId = "billing-subscriptions.subscriptions.list";

export const tenantRoutes = [
  {
    id: parentRouteId,
    module: "billing_subscriptions",
    path: "/billing-subscriptions",
    title: "Billing subscriptions",
    sourceFile: "modules/billing_subscriptions/pages/BillingSubscriptionsListPage.tsx",
    Page: lazy(() =>
      import("./pages/BillingSubscriptionsListPage").then(({ BillingSubscriptionsListPage }) => ({
        default: BillingSubscriptionsListPage,
      }))
    ),
    modes,
    navigation: {
      type: "sidebar",
      label: "Subscriptions",
      icon: ReceiptText,
      order: 130,
    },
  },
  {
    id: "billing-subscriptions.subscriptions.create",
    module: "billing_subscriptions",
    path: "/billing-subscriptions/create",
    title: "Create billing subscription",
    sourceFile: "modules/billing_subscriptions/pages/CreateBillingSubscriptionsResourcePage.tsx",
    Page: lazy(() =>
      import("./pages/CreateBillingSubscriptionsResourcePage").then(
        ({ CreateBillingSubscriptionsResourcePage }) => ({
          default: CreateBillingSubscriptionsResourcePage,
        })
      )
    ),
    modes,
    navigation: { type: "contextual", parentRouteId, label: "Create subscription", icon: Plus },
  },
  {
    id: "billing-subscriptions.subscriptions.detail",
    module: "billing_subscriptions",
    path: "/billing-subscriptions/:id",
    title: "Billing subscription detail",
    sourceFile: "modules/billing_subscriptions/pages/BillingSubscriptionsDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BillingSubscriptionsDetailPage").then(
        ({ BillingSubscriptionsDetailPage }) => ({
          default: BillingSubscriptionsDetailPage,
        })
      )
    ),
    modes,
    navigation: { type: "contextual", parentRouteId },
  },
  {
    id: "billing-subscriptions.quotas",
    module: "billing_subscriptions",
    path: "/billing-subscriptions/quotas",
    title: "Quota management",
    sourceFile: "modules/billing_subscriptions/pages/QuotaManagementPage.tsx",
    Page: lazy(() =>
      import("./pages/QuotaManagementPage").then(({ QuotaManagementPage }) => ({
        default: QuotaManagementPage,
      }))
    ),
    modes,
    navigation: {
      type: "sidebar",
      label: "Quota management",
      icon: Gauge,
      order: 131,
    },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
