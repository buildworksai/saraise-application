import { lazy } from "react";
import { FileInput, Landmark, ListChecks, Scale, ScrollText } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

export const tenantRoutes = [
  {
    id: "bank-reconciliation.accounts.list",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/accounts",
    sourceFile: "modules/bank_reconciliation/pages/BankAccountListPage.tsx",
    Page: lazy(() =>
      import("./pages/BankAccountListPage").then(({ BankAccountListPage }) => ({
        default: BankAccountListPage,
      }))
    ),
    navigation: { type: "sidebar", label: "Bank accounts", icon: Landmark, order: 600 },
  },
  {
    id: "bank-reconciliation.accounts.create",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/accounts/new",
    sourceFile: "modules/bank_reconciliation/pages/CreateBankAccountPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateBankAccountPage").then(({ CreateBankAccountPage }) => ({
        default: CreateBankAccountPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.accounts.list" },
  },
  {
    id: "bank-reconciliation.accounts.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/accounts/:id",
    sourceFile: "modules/bank_reconciliation/pages/BankAccountDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/BankAccountDetailPage").then(({ BankAccountDetailPage }) => ({
        default: BankAccountDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.accounts.list" },
  },
  {
    id: "bank-reconciliation.accounts.edit",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/accounts/:id/edit",
    sourceFile: "modules/bank_reconciliation/pages/EditBankAccountPage.tsx",
    Page: lazy(() =>
      import("./pages/EditBankAccountPage").then(({ EditBankAccountPage }) => ({
        default: EditBankAccountPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.accounts.list" },
  },
  {
    id: "bank-reconciliation.statements.list",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/statements",
    sourceFile: "modules/bank_reconciliation/pages/StatementListPage.tsx",
    Page: lazy(() =>
      import("./pages/StatementListPage").then(({ StatementListPage }) => ({
        default: StatementListPage,
      }))
    ),
    navigation: { type: "sidebar", label: "Statements", icon: ScrollText, order: 610 },
  },
  {
    id: "bank-reconciliation.statements.import",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/statements/import",
    sourceFile: "modules/bank_reconciliation/pages/ImportStatementPage.tsx",
    Page: lazy(() =>
      import("./pages/ImportStatementPage").then(({ ImportStatementPage }) => ({
        default: ImportStatementPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.statements.list" },
  },
  {
    id: "bank-reconciliation.statements.create",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/statements/new",
    sourceFile: "modules/bank_reconciliation/pages/CreateManualStatementPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateManualStatementPage").then(({ CreateManualStatementPage }) => ({
        default: CreateManualStatementPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.statements.list" },
  },
  {
    id: "bank-reconciliation.statements.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/statements/:id",
    sourceFile: "modules/bank_reconciliation/pages/StatementDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/StatementDetailPage").then(({ StatementDetailPage }) => ({
        default: StatementDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.statements.list" },
  },
  {
    id: "bank-reconciliation.transactions.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/transactions/:id",
    sourceFile: "modules/bank_reconciliation/pages/TransactionDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/TransactionDetailPage").then(({ TransactionDetailPage }) => ({
        default: TransactionDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.statements.list" },
  },
  {
    id: "bank-reconciliation.transactions.edit",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/transactions/:id/edit",
    sourceFile: "modules/bank_reconciliation/pages/EditTransactionPage.tsx",
    Page: lazy(() =>
      import("./pages/EditTransactionPage").then(({ EditTransactionPage }) => ({
        default: EditTransactionPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.statements.list" },
  },
  {
    id: "bank-reconciliation.reconciliations.list",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/reconciliations",
    sourceFile: "modules/bank_reconciliation/pages/ReconciliationListPage.tsx",
    Page: lazy(() =>
      import("./pages/ReconciliationListPage").then(({ ReconciliationListPage }) => ({
        default: ReconciliationListPage,
      }))
    ),
    navigation: { type: "sidebar", label: "Reconciliations", icon: Scale, order: 620 },
  },
  {
    id: "bank-reconciliation.reconciliations.create",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/reconciliations/new",
    sourceFile: "modules/bank_reconciliation/pages/CreateReconciliationPage.tsx",
    Page: lazy(() =>
      import("./pages/CreateReconciliationPage").then(({ CreateReconciliationPage }) => ({
        default: CreateReconciliationPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.reconciliations.list" },
  },
  {
    id: "bank-reconciliation.reconciliations.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/reconciliations/:id",
    sourceFile: "modules/bank_reconciliation/pages/ReconciliationDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/ReconciliationDetailPage").then(({ ReconciliationDetailPage }) => ({
        default: ReconciliationDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.reconciliations.list" },
  },
  {
    id: "bank-reconciliation.reconciliations.workspace",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/reconciliations/:id/workspace",
    sourceFile: "modules/bank_reconciliation/pages/ReconciliationWorkspacePage.tsx",
    Page: lazy(() =>
      import("./pages/ReconciliationWorkspacePage").then(({ ReconciliationWorkspacePage }) => ({
        default: ReconciliationWorkspacePage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.reconciliations.list" },
  },
  {
    id: "bank-reconciliation.rules.list",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/rules",
    sourceFile: "modules/bank_reconciliation/pages/MatchingRuleListPage.tsx",
    Page: lazy(() =>
      import("./pages/MatchingRuleListPage").then(({ MatchingRuleListPage }) => ({
        default: MatchingRuleListPage,
      }))
    ),
    navigation: { type: "sidebar", label: "Matching rules", icon: ListChecks, order: 630 },
  },
  {
    id: "bank-reconciliation.rules.create",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/rules/new",
    sourceFile: "modules/bank_reconciliation/pages/CreateMatchingRulePage.tsx",
    Page: lazy(() =>
      import("./pages/CreateMatchingRulePage").then(({ CreateMatchingRulePage }) => ({
        default: CreateMatchingRulePage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.rules.list" },
  },
  {
    id: "bank-reconciliation.rules.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/rules/:id",
    sourceFile: "modules/bank_reconciliation/pages/MatchingRuleDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/MatchingRuleDetailPage").then(({ MatchingRuleDetailPage }) => ({
        default: MatchingRuleDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.rules.list" },
  },
  {
    id: "bank-reconciliation.rules.edit",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/rules/:id/edit",
    sourceFile: "modules/bank_reconciliation/pages/EditMatchingRulePage.tsx",
    Page: lazy(() =>
      import("./pages/EditMatchingRulePage").then(({ EditMatchingRulePage }) => ({
        default: EditMatchingRulePage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.rules.list" },
  },
  {
    id: "bank-reconciliation.imports.list",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/imports",
    sourceFile: "modules/bank_reconciliation/pages/ImportJobListPage.tsx",
    Page: lazy(() =>
      import("./pages/ImportJobListPage").then(({ ImportJobListPage }) => ({
        default: ImportJobListPage,
      }))
    ),
    navigation: { type: "sidebar", label: "Import jobs", icon: FileInput, order: 640 },
  },
  {
    id: "bank-reconciliation.imports.detail",
    module: "bank_reconciliation",
    path: "/bank-reconciliation/imports/:id",
    sourceFile: "modules/bank_reconciliation/pages/ImportJobDetailPage.tsx",
    Page: lazy(() =>
      import("./pages/ImportJobDetailPage").then(({ ImportJobDetailPage }) => ({
        default: ImportJobDetailPage,
      }))
    ),
    navigation: { type: "contextual", parentRouteId: "bank-reconciliation.imports.list" },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
