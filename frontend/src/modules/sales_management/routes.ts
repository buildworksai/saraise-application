import { lazy } from "react";
import { Users } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

export const tenantRoutes = [
  {
    id: "sales-management.customers.list",
    module: "sales_management",
    path: "/sales-management/customers",
    sourceFile: "modules/sales_management/pages/CustomerListPage.tsx",
    Page: lazy(() =>
      import("./pages/CustomerListPage").then(({ CustomerListPage }) => ({
        default: CustomerListPage,
      })),
    ),
    navigation: { type: "sidebar", label: "Customers", icon: Users, order: 200 },
  },
  {
    id: "sales-management.customers.create",
    module: "sales_management",
    path: "/sales-management/customers/new",
    sourceFile: "modules/sales_management/pages/CreateCustomerPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateCustomerPage").then(({ CreateCustomerPage }) => ({
        default: CreateCustomerPage,
      })),
    ),
    navigation: {
      type: "contextual",
      parentRouteId: "sales-management.customers.list",
    },
  },
  {
    id: "sales-management.customers.detail",
    module: "sales_management",
    path: "/sales-management/customers/:id",
    sourceFile: "modules/sales_management/pages/CustomerDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/CustomerDetailPage").then(({ CustomerDetailPage }) => ({
        default: CustomerDetailPage,
      })),
    ),
    navigation: {
      type: "contextual",
      parentRouteId: "sales-management.customers.list",
    },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
