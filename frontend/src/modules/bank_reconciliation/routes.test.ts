import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement, Suspense } from "react";
import { describe, expect, it } from "vitest";
import { tenantRoutes } from "./routes";

vi.mock("./pages/BankAccountListPage", () => ({
  BankAccountListPage: () => "bank-reconciliation.accounts.list.page",
}));
vi.mock("./pages/CreateBankAccountPage", () => ({
  CreateBankAccountPage: () => "bank-reconciliation.accounts.create.page",
}));
vi.mock("./pages/BankAccountDetailPage", () => ({
  BankAccountDetailPage: () => "bank-reconciliation.accounts.detail.page",
}));
vi.mock("./pages/EditBankAccountPage", () => ({
  EditBankAccountPage: () => "bank-reconciliation.accounts.edit.page",
}));
vi.mock("./pages/StatementListPage", () => ({
  StatementListPage: () => "bank-reconciliation.statements.list.page",
}));
vi.mock("./pages/ImportStatementPage", () => ({
  ImportStatementPage: () => "bank-reconciliation.statements.import.page",
}));
vi.mock("./pages/CreateManualStatementPage", () => ({
  CreateManualStatementPage: () => "bank-reconciliation.statements.create.page",
}));
vi.mock("./pages/StatementDetailPage", () => ({
  StatementDetailPage: () => "bank-reconciliation.statements.detail.page",
}));
vi.mock("./pages/TransactionDetailPage", () => ({
  TransactionDetailPage: () => "bank-reconciliation.transactions.detail.page",
}));
vi.mock("./pages/EditTransactionPage", () => ({
  EditTransactionPage: () => "bank-reconciliation.transactions.edit.page",
}));
vi.mock("./pages/ReconciliationListPage", () => ({
  ReconciliationListPage: () => "bank-reconciliation.reconciliations.list.page",
}));
vi.mock("./pages/CreateReconciliationPage", () => ({
  CreateReconciliationPage: () => "bank-reconciliation.reconciliations.create.page",
}));
vi.mock("./pages/ReconciliationDetailPage", () => ({
  ReconciliationDetailPage: () => "bank-reconciliation.reconciliations.detail.page",
}));
vi.mock("./pages/ReconciliationWorkspacePage", () => ({
  ReconciliationWorkspacePage: () => "bank-reconciliation.reconciliations.workspace.page",
}));
vi.mock("./pages/MatchingRuleListPage", () => ({
  MatchingRuleListPage: () => "bank-reconciliation.rules.list.page",
}));
vi.mock("./pages/CreateMatchingRulePage", () => ({
  CreateMatchingRulePage: () => "bank-reconciliation.rules.create.page",
}));
vi.mock("./pages/MatchingRuleDetailPage", () => ({
  MatchingRuleDetailPage: () => "bank-reconciliation.rules.detail.page",
}));
vi.mock("./pages/EditMatchingRulePage", () => ({
  EditMatchingRulePage: () => "bank-reconciliation.rules.edit.page",
}));
vi.mock("./pages/ImportJobListPage", () => ({
  ImportJobListPage: () => "bank-reconciliation.imports.list.page",
}));
vi.mock("./pages/ImportJobDetailPage", () => ({
  ImportJobDetailPage: () => "bank-reconciliation.imports.detail.page",
}));

describe("bank reconciliation tenant routes", () => {
  afterEach(() => {
    cleanup();
  });

  it("has unique route IDs and paths", () => {
    expect(new Set(tenantRoutes.map(({ id }) => id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map(({ path }) => path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes.map(({ module }) => module)).toEqual(
      Array.from({ length: tenantRoutes.length }, () => "bank_reconciliation")
    );
    expect(tenantRoutes.map(({ sourceFile }) => sourceFile)).toEqual([
      "modules/bank_reconciliation/pages/BankAccountListPage.tsx",
      "modules/bank_reconciliation/pages/CreateBankAccountPage.tsx",
      "modules/bank_reconciliation/pages/BankAccountDetailPage.tsx",
      "modules/bank_reconciliation/pages/EditBankAccountPage.tsx",
      "modules/bank_reconciliation/pages/StatementListPage.tsx",
      "modules/bank_reconciliation/pages/ImportStatementPage.tsx",
      "modules/bank_reconciliation/pages/CreateManualStatementPage.tsx",
      "modules/bank_reconciliation/pages/StatementDetailPage.tsx",
      "modules/bank_reconciliation/pages/TransactionDetailPage.tsx",
      "modules/bank_reconciliation/pages/EditTransactionPage.tsx",
      "modules/bank_reconciliation/pages/ReconciliationListPage.tsx",
      "modules/bank_reconciliation/pages/CreateReconciliationPage.tsx",
      "modules/bank_reconciliation/pages/ReconciliationDetailPage.tsx",
      "modules/bank_reconciliation/pages/ReconciliationWorkspacePage.tsx",
      "modules/bank_reconciliation/pages/MatchingRuleListPage.tsx",
      "modules/bank_reconciliation/pages/CreateMatchingRulePage.tsx",
      "modules/bank_reconciliation/pages/MatchingRuleDetailPage.tsx",
      "modules/bank_reconciliation/pages/EditMatchingRulePage.tsx",
      "modules/bank_reconciliation/pages/ImportJobListPage.tsx",
      "modules/bank_reconciliation/pages/ImportJobDetailPage.tsx",
    ]);
  });

  it("resolves every contextual parent to a sidebar route", () => {
    const byId = new Map(tenantRoutes.map((route) => [route.id, route]));
    for (const route of tenantRoutes) {
      if (route.navigation.type === "contextual") {
        expect(byId.get(route.navigation.parentRouteId)?.navigation.type).toBe("sidebar");
      }
    }
  });

  it("publishes the five ordered sidebar leaves", () => {
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");
    expect(sidebar.map((route) => route.path)).toEqual([
      "/bank-reconciliation/accounts",
      "/bank-reconciliation/statements",
      "/bank-reconciliation/reconciliations",
      "/bank-reconciliation/rules",
      "/bank-reconciliation/imports",
    ]);
    expect(
      sidebar.map((route) => (route.navigation.type === "sidebar" ? route.navigation.order : 0))
    ).toEqual([600, 610, 620, 630, 640]);
    expect(
      sidebar.map((route) => (route.navigation.type === "sidebar" ? route.navigation.label : ""))
    ).toEqual(["Bank accounts", "Statements", "Reconciliations", "Matching rules", "Import jobs"]);
  });

  it("publishes browser titles for every migrated route", () => {
    expect(tenantRoutes.map((route) => [route.path, route.title])).toEqual([
      ["/bank-reconciliation/accounts", "Bank accounts"],
      ["/bank-reconciliation/accounts/new", "Create bank account"],
      ["/bank-reconciliation/accounts/:id", "Bank account details"],
      ["/bank-reconciliation/accounts/:id/edit", "Edit bank account"],
      ["/bank-reconciliation/statements", "Bank statements"],
      ["/bank-reconciliation/statements/import", "Import statement"],
      ["/bank-reconciliation/statements/new", "Create statement"],
      ["/bank-reconciliation/statements/:id", "Statement details"],
      ["/bank-reconciliation/transactions/:id", "Transaction details"],
      ["/bank-reconciliation/transactions/:id/edit", "Edit transaction"],
      ["/bank-reconciliation/reconciliations", "Reconciliations"],
      ["/bank-reconciliation/reconciliations/new", "Create reconciliation"],
      ["/bank-reconciliation/reconciliations/:id", "Reconciliation details"],
      ["/bank-reconciliation/reconciliations/:id/workspace", "Reconciliation workspace"],
      ["/bank-reconciliation/rules", "Matching rules"],
      ["/bank-reconciliation/rules/new", "Create matching rule"],
      ["/bank-reconciliation/rules/:id", "Matching rule details"],
      ["/bank-reconciliation/rules/:id/edit", "Edit matching rule"],
      ["/bank-reconciliation/imports", "Import jobs"],
      ["/bank-reconciliation/imports/:id", "Import job details"],
    ]);
  });

  it("loads the exact registered lazy page for every migrated route", async () => {
    for (const route of tenantRoutes) {
      cleanup();
      const Page = route.Page;

      render(createElement(Suspense, { fallback: "loading route" }, createElement(Page)));

      await waitFor(() => expect(screen.getByText(`${route.id}.page`)).toBeInTheDocument());
    }
  });
});
