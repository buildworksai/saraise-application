import { lazy } from "react";
import { BookOpen, CalendarDays, CircleDollarSign, FileText, Receipt } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;
const pages = () => import("./pages/ResourceListPages");
const detailPages = () => import("./pages/ResourceDetailPages");
const formPages = () => import("./pages/ResourceFormPages");

export const tenantRoutes = [
  {
    id: "accounting-finance.accounts.list",
    module: "accounting_finance",
    path: "/accounting-finance/accounts",
    title: "Accounting accounts",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() => pages().then(({ AccountListView }) => ({ default: AccountListView }))),
    modes,
    navigation: { type: "sidebar", label: "Chart of accounts", icon: BookOpen, order: 200 },
  },
  {
    id: "accounting-finance.periods.list",
    module: "accounting_finance",
    path: "/accounting-finance/periods",
    title: "Posting periods",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() =>
      pages().then(({ PostingPeriodListView }) => ({ default: PostingPeriodListView }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Posting periods", icon: CalendarDays, order: 201 },
  },
  {
    id: "accounting-finance.journal-entries.list",
    module: "accounting_finance",
    path: "/accounting-finance/journal-entries",
    title: "Journal entries",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() =>
      pages().then(({ JournalEntryListView }) => ({ default: JournalEntryListView }))
    ),
    modes,
    navigation: { type: "sidebar", label: "Journal entries", icon: FileText, order: 202 },
  },
  {
    id: "accounting-finance.ap-invoices.list",
    module: "accounting_finance",
    path: "/accounting-finance/ap-invoices",
    title: "AP invoices",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() => pages().then(({ APInvoiceListView }) => ({ default: APInvoiceListView }))),
    modes,
    navigation: { type: "sidebar", label: "AP invoices", icon: Receipt, order: 203 },
  },
  {
    id: "accounting-finance.ar-invoices.list",
    module: "accounting_finance",
    path: "/accounting-finance/ar-invoices",
    title: "AR invoices",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() => pages().then(({ ARInvoiceListView }) => ({ default: ARInvoiceListView }))),
    modes,
    navigation: { type: "sidebar", label: "AR invoices", icon: Receipt, order: 204 },
  },
  {
    id: "accounting-finance.payments.list",
    module: "accounting_finance",
    path: "/accounting-finance/payments",
    title: "Payments",
    sourceFile: "modules/accounting_finance/pages/ResourceListPages.tsx",
    Page: lazy(() => pages().then(({ PaymentListView }) => ({ default: PaymentListView }))),
    modes,
    navigation: { type: "sidebar", label: "Payments", icon: CircleDollarSign, order: 205 },
  },
  {
    id: "accounting-finance.accounts.create",
    module: "accounting_finance",
    path: "/accounting-finance/accounts/new",
    title: "Create accounting account",
    sourceFile: "modules/accounting_finance/pages/CreateAccountPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateAccountPage").then(({ CreateAccountPage }) => ({
        default: CreateAccountPage,
      }))
    ),
    modes,
    navigation: { type: "contextual", parentRouteId: "accounting-finance.accounts.list" },
  },
  {
    id: "accounting-finance.accounts.detail",
    module: "accounting_finance",
    path: "/accounting-finance/accounts/:id",
    title: "Accounting account detail",
    sourceFile: "modules/accounting_finance/pages/ResourceDetailPages.tsx",
    Page: lazy(() =>
      detailPages().then(({ AccountDetailView }) => ({ default: AccountDetailView }))
    ),
    modes,
    navigation: { type: "contextual", parentRouteId: "accounting-finance.accounts.list" },
  },
  {
    id: "accounting-finance.accounts.edit",
    module: "accounting_finance",
    path: "/accounting-finance/accounts/:id/edit",
    title: "Edit accounting account",
    sourceFile: "modules/accounting_finance/pages/ResourceFormPages.tsx",
    Page: lazy(() => formPages().then(({ AccountFormPage }) => ({ default: AccountFormPage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "accounting-finance.accounts.list" },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
