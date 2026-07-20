import { lazy } from "react";
import { Briefcase, Building2, LayoutDashboard, TrendingUp, Users } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

export const tenantRoutes = [
  {
    id: "crm.dashboard",
    module: "crm",
    path: "/crm/dashboard",
    sourceFile: "modules/crm/pages/SalesDashboardPage.tsx",
    Page: lazy(() =>
      import("./pages/SalesDashboardPage").then(({ SalesDashboardPage }) => ({
        default: SalesDashboardPage,
      })),
    ),
    navigation: { type: "sidebar", label: "Dashboard", icon: LayoutDashboard, order: 100 },
  },
  {
    id: "crm.leads.list",
    module: "crm",
    path: "/crm/leads",
    sourceFile: "modules/crm/pages/LeadListPage.tsx",
    Page: lazy(() =>
      import("./pages/LeadListPage").then(({ LeadListPage }) => ({ default: LeadListPage })),
    ),
    navigation: { type: "sidebar", label: "Leads", icon: TrendingUp, order: 110 },
  },
  {
    id: "crm.leads.detail",
    module: "crm",
    path: "/crm/leads/:id",
    sourceFile: "modules/crm/pages/LeadDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/LeadDetailPage").then(({ LeadDetailPage }) => ({ default: LeadDetailPage })),
    ),
    navigation: { type: "contextual", parentRouteId: "crm.leads.list" },
  },
  {
    id: "crm.contacts.list",
    module: "crm",
    path: "/crm/contacts",
    sourceFile: "modules/crm/pages/ContactListPage.tsx",
    Page: lazy(() =>
      import("./pages/ContactListPage").then(({ ContactListPage }) => ({ default: ContactListPage })),
    ),
    navigation: { type: "sidebar", label: "Contacts", icon: Users, order: 120 },
  },
  {
    id: "crm.contacts.detail",
    module: "crm",
    path: "/crm/contacts/:id",
    sourceFile: "modules/crm/pages/ContactDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/ContactDetailPage").then(({ ContactDetailPage }) => ({
        default: ContactDetailPage,
      })),
    ),
    navigation: { type: "contextual", parentRouteId: "crm.contacts.list" },
  },
  {
    id: "crm.accounts.list",
    module: "crm",
    path: "/crm/accounts",
    sourceFile: "modules/crm/pages/AccountListPage.tsx",
    Page: lazy(() =>
      import("./pages/AccountListPage").then(({ AccountListPage }) => ({ default: AccountListPage })),
    ),
    navigation: { type: "sidebar", label: "Accounts", icon: Building2, order: 130 },
  },
  {
    id: "crm.accounts.detail",
    module: "crm",
    path: "/crm/accounts/:id",
    sourceFile: "modules/crm/pages/AccountDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/AccountDetailPage").then(({ AccountDetailPage }) => ({
        default: AccountDetailPage,
      })),
    ),
    navigation: { type: "contextual", parentRouteId: "crm.accounts.list" },
  },
  {
    id: "crm.opportunities.list",
    module: "crm",
    path: "/crm/opportunities",
    sourceFile: "modules/crm/pages/OpportunityListPage.tsx",
    Page: lazy(() =>
      import("./pages/OpportunityListPage").then(({ OpportunityListPage }) => ({
        default: OpportunityListPage,
      })),
    ),
    navigation: { type: "sidebar", label: "Opportunities", icon: Briefcase, order: 140 },
  },
  {
    id: "crm.opportunities.pipeline",
    module: "crm",
    path: "/crm/opportunities/pipeline",
    sourceFile: "modules/crm/pages/OpportunityKanbanPage.tsx",
    Page: lazy(() =>
      import("./pages/OpportunityKanbanPage").then(({ OpportunityKanbanPage }) => ({
        default: OpportunityKanbanPage,
      })),
    ),
    navigation: { type: "sidebar", label: "Pipeline", icon: Briefcase, order: 141 },
  },
  {
    id: "crm.opportunities.detail",
    module: "crm",
    path: "/crm/opportunities/:id",
    sourceFile: "modules/crm/pages/OpportunityDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/OpportunityDetailPage").then(({ OpportunityDetailPage }) => ({
        default: OpportunityDetailPage,
      })),
    ),
    navigation: { type: "contextual", parentRouteId: "crm.opportunities.list" },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
