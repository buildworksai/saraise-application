/* eslint-disable max-lines-per-function -- App route coverage is intentionally table-driven so route branches stay auditable beside their mocks. */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { formatRouteTitle } from "./route-title";

vi.mock("./components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("./components/layout/ModuleLayout", () => ({
  ModuleLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock("./modules/asset_management/pages/AssetListPage", () => ({
  AssetListPage: () => <h1>Registry asset register page</h1>,
}));

vi.mock("./modules/bank_reconciliation/pages/BankAccountListPage", () => ({
  BankAccountListPage: () => <h1>Registry bank accounts page</h1>,
}));

vi.mock("./modules/inventory_management/pages/InventoryPages", () => ({
  WarehouseListPage: () => <h1>Registry warehouses page</h1>,
}));

vi.mock("./modules/security_access_control/pages/RolesPage", () => ({
  RolesPage: () => <h1>Registry security roles page</h1>,
}));

vi.mock("./modules/security_access_control/pages/PermissionsPage", () => ({
  PermissionsPage: () => <h1>Registry security permissions page</h1>,
}));

vi.mock("./modules/security_access_control/pages/PermissionSetsPage", () => ({
  PermissionSetsPage: () => <h1>Registry permission sets page</h1>,
}));

vi.mock("./modules/security_access_control/pages/AuditLogPage", () => ({
  AuditLogPage: () => <h1>Registry security audit log page</h1>,
}));

vi.mock("./modules/human_resources/pages/CreateLeaveRequestPage", () => ({
  CreateLeaveRequestPage: () => <h1>Registry leave request create page</h1>,
}));

vi.mock("./modules/human_resources/pages/LeaveRequestDetailPage", () => ({
  LeaveRequestDetailPage: () => <h1>Registry leave request detail page</h1>,
}));

vi.mock("./modules/human_resources/pages/EditLeaveRequestPage", () => ({
  EditLeaveRequestPage: () => <h1>Registry leave request edit page</h1>,
}));

vi.mock("./modules/document_intelligence/pages/ExtractionDashboardPage", () => ({
  ExtractionDashboardPage: () => <h1>Registry document intelligence extractions page</h1>,
}));

vi.mock("./modules/accounting_finance/pages/ResourceListPages", () => ({
  PostingPeriodListView: () => <h1>Accounting posting periods list page</h1>,
  JournalEntryListView: () => <h1>Accounting journal entries list page</h1>,
  APInvoiceListView: () => <h1>Accounting AP invoices list page</h1>,
  ARInvoiceListView: () => <h1>Accounting AR invoices list page</h1>,
  PaymentListView: () => <h1>Accounting payments list page</h1>,
}));

vi.mock("./modules/accounting_finance/pages/ResourceDetailPages", () => ({
  AccountDetailView: () => <h1>Accounting account detail page</h1>,
  PostingPeriodDetailView: () => <h1>Accounting posting period detail page</h1>,
  JournalEntryDetailView: () => <h1>Accounting journal entry detail page</h1>,
  APInvoiceDetailView: () => <h1>Accounting AP invoice detail page</h1>,
  ARInvoiceDetailView: () => <h1>Accounting AR invoice detail page</h1>,
  PaymentDetailView: () => <h1>Accounting payment detail page</h1>,
}));

vi.mock("./modules/accounting_finance/pages/ResourceFormPages", () => ({
  AccountFormPage: ({ edit }: { edit?: boolean }) => (
    <h1>{edit ? "Accounting account edit page" : "Accounting account create page"}</h1>
  ),
  PostingPeriodFormPage: ({ edit }: { edit?: boolean }) => (
    <h1>
      {edit ? "Accounting posting period edit page" : "Accounting posting period create page"}
    </h1>
  ),
  JournalEntryFormPage: ({ edit }: { edit?: boolean }) => (
    <h1>{edit ? "Accounting journal entry edit page" : "Accounting journal entry create page"}</h1>
  ),
  InvoiceFormPage: ({ kind, edit }: { kind: "ap" | "ar"; edit?: boolean }) => (
    <h1>{`Accounting ${kind.toUpperCase()} invoice ${edit ? "edit" : "create"} page`}</h1>
  ),
  PaymentFormPage: ({ edit }: { edit?: boolean }) => (
    <h1>{edit ? "Accounting payment edit page" : "Accounting payment create page"}</h1>
  ),
}));

vi.mock("./modules/accounting_finance/pages/CreateAccountPage", () => ({
  CreateAccountPage: () => <h1>Accounting account create legacy page</h1>,
}));

vi.mock("./modules/budget_management/pages/BudgetListPage", () => ({
  BudgetListPage: () => <h1>Budget list route page</h1>,
}));

vi.mock("./modules/budget_management/pages/BudgetDetailPage", () => ({
  BudgetDetailPage: () => <h1>Budget detail route page</h1>,
}));

vi.mock("./modules/budget_management/pages/CreateBudgetPage", () => ({
  CreateBudgetPage: () => <h1>Budget create route page</h1>,
}));

vi.mock("./modules/compliance_management/pages/CompliancePolicyListPage", () => ({
  CompliancePolicyListPage: () => <h1>Compliance policy list route page</h1>,
}));

vi.mock("./modules/compliance_management/pages/CompliancePolicyDetailPage", () => ({
  CompliancePolicyDetailPage: () => <h1>Compliance policy detail route page</h1>,
}));

vi.mock("./modules/compliance_management/pages/CreateCompliancePolicyPage", () => ({
  CreateCompliancePolicyPage: () => <h1>Compliance policy create route page</h1>,
}));

vi.mock("./modules/compliance_risk_management/pages/ComplianceRiskListPage", () => ({
  ComplianceRiskListPage: () => <h1>Compliance risk list route page</h1>,
}));

vi.mock("./modules/compliance_risk_management/pages/ComplianceRiskDetailPage", () => ({
  ComplianceRiskDetailPage: () => <h1>Compliance risk detail route page</h1>,
}));

vi.mock("./modules/compliance_risk_management/pages/CreateComplianceRiskPage", () => ({
  CreateComplianceRiskPage: () => <h1>Compliance risk create route page</h1>,
}));

vi.mock("./modules/billing_subscriptions/pages/BillingSubscriptionsListPage", () => ({
  BillingSubscriptionsListPage: () => <h1>Billing subscriptions list page</h1>,
}));

vi.mock("./modules/billing_subscriptions/pages/BillingSubscriptionsDetailPage", () => ({
  BillingSubscriptionsDetailPage: () => <h1>Billing subscription detail page</h1>,
}));

vi.mock("./modules/billing_subscriptions/pages/CreateBillingSubscriptionsResourcePage", () => ({
  CreateBillingSubscriptionsResourcePage: () => <h1>Billing subscription create page</h1>,
}));

vi.mock("./modules/localization/pages/CreateLocalizationResourcePage", () => ({
  CreateLocalizationResourcePage: () => <h1>Localization create page</h1>,
}));

vi.mock("./modules/localization/pages/LocalizationListPage", () => ({
  LocalizationListPage: () => <h1>Localization list route page</h1>,
}));

vi.mock("./modules/localization/pages/LocalizationDetailPage", () => ({
  LocalizationDetailPage: () => <h1>Localization detail route page</h1>,
}));

vi.mock(
  "./modules/ai_provider_configuration/pages/CreateAiProviderConfigurationResourcePage",
  () => ({
    CreateAiProviderConfigurationResourcePage: () => <h1>AI provider create page</h1>,
  })
);

vi.mock("./modules/ai_provider_configuration/pages/AiProviderConfigurationListPage", () => ({
  AiProviderConfigurationListPage: () => <h1>AI provider list route page</h1>,
}));

vi.mock("./modules/ai_provider_configuration/pages/AiProviderConfigurationDetailPage", () => ({
  AiProviderConfigurationDetailPage: () => <h1>AI provider detail route page</h1>,
}));

vi.mock("./modules/ai_provider_configuration/pages/AiProviderRuntimeConfigurationPage", () => ({
  AiProviderRuntimeConfigurationPage: () => <h1>AI provider runtime route page</h1>,
}));

vi.mock("./modules/ai_provider_configuration/pages/SecretManagementPage", () => ({
  SecretManagementPage: () => <h1>AI provider secrets route page</h1>,
}));

vi.mock("./modules/notifications/pages/NotificationCenterPage", () => ({
  NotificationCenterPage: () => <h1>Notification center route page</h1>,
}));

vi.mock("./modules/data_migration/pages/DataMigrationListPage", () => ({
  DataMigrationListPage: () => <h1>Data migration list route page</h1>,
}));

vi.mock("./modules/data_migration/pages/DataMigrationDetailPage", () => ({
  DataMigrationDetailPage: () => <h1>Data migration detail route page</h1>,
}));

vi.mock("./modules/data_migration/pages/CreateDataMigrationResourcePage", () => ({
  CreateDataMigrationResourcePage: () => <h1>Data migration create route page</h1>,
}));

vi.mock("./modules/billing_subscriptions/pages/QuotaManagementPage", () => ({
  QuotaManagementPage: () => <h1>Billing quota route page</h1>,
}));

vi.mock("./modules/regional/pages/RegionalListPage", () => ({
  RegionalListPage: () => <h1>Regional list route page</h1>,
}));

vi.mock("./modules/regional/pages/RegionalDetailPage", () => ({
  RegionalDetailPage: () => <h1>Regional detail route page</h1>,
}));

vi.mock("./modules/regional/pages/CreateRegionalResourcePage", () => ({
  CreateRegionalResourcePage: () => <h1>Regional create route page</h1>,
}));

vi.mock("./modules/regional/pages/EditRegionalResourcePage", () => ({
  EditRegionalResourcePage: () => <h1>Regional edit route page</h1>,
}));

vi.mock("./modules/regional/pages/RegionalConfigurationPage", () => ({
  RegionalConfigurationPage: () => <h1>Regional configuration route page</h1>,
}));

vi.mock("./pages/user/SettingsPage", () => ({
  SettingsPage: () => <h1>User settings page</h1>,
}));

vi.mock("./modules/platform_management/pages/LicenseSettingsPage", () => ({
  LicenseSettingsPage: () => <h1>License settings page</h1>,
}));

vi.mock("./modules/tenant_management/pages/TenantListPage", () => ({
  TenantListPage: () => <h1>Tenant management list page</h1>,
}));

vi.mock("./modules/tenant_management/pages/TenantDetailPage", () => ({
  TenantDetailPage: () => <h1>Tenant management detail page</h1>,
}));

vi.mock("./pages/tenant/TenantDashboard", () => ({
  TenantDashboard: () => <h1>Tenant dashboard page</h1>,
}));

vi.mock("./pages/user/ProfilePage", () => ({
  ProfilePage: () => <h1>User profile page</h1>,
}));

class TestErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return <div role="alert">Route render failed</div>;
    return this.props.children;
  }
}

const accountingRouteCases = [
  [
    "/accounting-finance/accounts/new",
    "Create accounting account · SARAISE",
    "Accounting account create legacy page",
  ],
  [
    "/accounting-finance/accounts/account%2042",
    "Accounting account detail · SARAISE",
    "Accounting account detail page",
  ],
  [
    "/accounting-finance/periods",
    "Posting periods · SARAISE",
    "Accounting posting periods list page",
  ],
  [
    "/accounting-finance/journal-entries",
    "Journal entries · SARAISE",
    "Accounting journal entries list page",
  ],
  [
    "/accounting-finance/ap-invoices",
    "Accounts payable invoices · SARAISE",
    "Accounting AP invoices list page",
  ],
  [
    "/accounting-finance/ar-invoices",
    "Accounts receivable invoices · SARAISE",
    "Accounting AR invoices list page",
  ],
  ["/accounting-finance/payments", "Payments · SARAISE", "Accounting payments list page"],
  [
    "/accounting-finance/periods/period%2042",
    "Posting period detail · SARAISE",
    "Accounting posting period detail page",
  ],
  [
    "/accounting-finance/journal-entries/journal%2042",
    "Journal entry detail · SARAISE",
    "Accounting journal entry detail page",
  ],
  [
    "/accounting-finance/ap-invoices/invoice%2042",
    "AP invoice detail · SARAISE",
    "Accounting AP invoice detail page",
  ],
  [
    "/accounting-finance/ar-invoices/invoice%2042",
    "AR invoice detail · SARAISE",
    "Accounting AR invoice detail page",
  ],
  [
    "/accounting-finance/payments/payment%2042",
    "Payment detail · SARAISE",
    "Accounting payment detail page",
  ],
  [
    "/accounting-finance/accounts/account%2042/edit",
    "Edit accounting account · SARAISE",
    "Accounting account edit page",
  ],
  [
    "/accounting-finance/periods/new",
    "Create posting period · SARAISE",
    "Accounting posting period create page",
  ],
  [
    "/accounting-finance/periods/period%2042/edit",
    "Edit posting period · SARAISE",
    "Accounting posting period edit page",
  ],
  [
    "/accounting-finance/journal-entries/new",
    "Create journal entry · SARAISE",
    "Accounting journal entry create page",
  ],
  [
    "/accounting-finance/journal-entries/journal%2042/edit",
    "Edit journal entry · SARAISE",
    "Accounting journal entry edit page",
  ],
  [
    "/accounting-finance/ap-invoices/new",
    "Create AP invoice · SARAISE",
    "Accounting AP invoice create page",
  ],
  [
    "/accounting-finance/ap-invoices/invoice%2042/edit",
    "Edit AP invoice · SARAISE",
    "Accounting AP invoice edit page",
  ],
  [
    "/accounting-finance/ar-invoices/new",
    "Create AR invoice · SARAISE",
    "Accounting AR invoice create page",
  ],
  [
    "/accounting-finance/ar-invoices/invoice%2042/edit",
    "Edit AR invoice · SARAISE",
    "Accounting AR invoice edit page",
  ],
  [
    "/accounting-finance/payments/new",
    "Record payment · SARAISE",
    "Accounting payment create page",
  ],
  [
    "/accounting-finance/payments/payment%2042/edit",
    "Edit payment · SARAISE",
    "Accounting payment edit page",
  ],
] as const;

describe("App", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it("renders the app with router", () => {
    window.history.pushState(null, "", "/login");

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    // App renders BrowserRouter, so check for a link or route element
    // The login page should be accessible
    expect(screen.getByRole("link", { name: /forgot password/i })).toBeInTheDocument();
  });

  it.each([
    ["Inventory", "Inventory · SARAISE"],
    ["  Inventory  ", "Inventory · SARAISE"],
    ["Already branded · SARAISE", "Already branded · SARAISE"],
    [undefined, "SARAISE · SARAISE"],
    ["   ", "SARAISE · SARAISE"],
  ])("formats route title %s", (title, expected) => {
    expect(formatRouteTitle(title)).toBe(expected);
  });

  it.each([
    ["/asset-management/assets", "Asset register · SARAISE", "Registry asset register page"],
    ["/bank-reconciliation/accounts", "Bank accounts · SARAISE", "Registry bank accounts page"],
    ["/inventory-management/warehouses", "Warehouses · SARAISE", "Registry warehouses page"],
    [
      "/security-access-control/roles",
      "Security administration · SARAISE",
      "Registry security roles page",
    ],
    [
      "/security-access-control/permissions",
      "Permissions · SARAISE",
      "Registry security permissions page",
    ],
    [
      "/security-access-control/permission-sets",
      "Permission sets · SARAISE",
      "Registry permission sets page",
    ],
    [
      "/security-access-control/audit-logs",
      "Security audit trail · SARAISE",
      "Registry security audit log page",
    ],
    [
      "/human-resources/leave-requests/new",
      "Request leave · SARAISE",
      "Registry leave request create page",
    ],
  ])(
    "renders %s through the migrated route registry title wrapper",
    async (path, title, heading) => {
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(document.title).toBe(title));
    }
  );

  it("renders the AI provider create route", async () => {
    window.history.pushState(null, "", "/ai-provider-configuration/create");

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    expect(
      await screen.findByRole("heading", { name: "AI provider create page" })
    ).toBeInTheDocument();
  });

  it.each([
    ["/tenant/dashboard", "Dashboard · SARAISE", "Tenant dashboard page"],
    ["/tenant-management", "Tenant management · SARAISE", "Tenant management list page"],
    ["/tenant-management/tenant%2042", "Tenant detail · SARAISE", "Tenant management detail page"],
    ["/profile", "User profile · SARAISE", "User profile page"],
    ["/settings", "User settings · SARAISE", "User settings page"],
  ])(
    "renders protected shell route %s with the expected route title",
    async (path, title, heading) => {
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(document.title).toBe(title));
    }
  );

  it.each([
    ["/budget-management/budgets", "Budget list route page"],
    ["/budget-management/budgets/new", "Budget create route page"],
    ["/budget-management/budgets/budget%2042", "Budget detail route page"],
    ["/compliance-management/policies", "Compliance policy list route page"],
    ["/compliance-management/policies/new", "Compliance policy create route page"],
    ["/compliance-management/policies/policy%2042", "Compliance policy detail route page"],
    ["/compliance-risk-management/risks", "Compliance risk list route page"],
    ["/compliance-risk-management/risks/new", "Compliance risk create route page"],
    ["/compliance-risk-management/risks/risk%2042", "Compliance risk detail route page"],
    ["/ai-provider-configuration", "AI provider list route page"],
    ["/ai-provider-configuration/runtime-configuration", "AI provider runtime route page"],
    ["/ai-provider-configuration/provider%2042", "AI provider detail route page"],
    ["/ai-providers/secrets", "AI provider secrets route page"],
    ["/notifications", "Notification center route page"],
    ["/data-migration", "Data migration list route page"],
    ["/data-migration/jobs/new", "Data migration create route page"],
    ["/data-migration/create", "Data migration create route page"],
    ["/data-migration/jobs/job%2042", "Data migration detail route page"],
    ["/data-migration/job%2042", "Data migration detail route page"],
    ["/billing/quotas", "Billing quota route page"],
    ["/localization", "Localization list route page"],
    ["/localization/resource%2042", "Localization detail route page"],
    ["/regional", "Regional list route page"],
    ["/regional/create", "Regional create route page"],
    ["/regional/configuration", "Regional configuration route page"],
    ["/regional/resource%2042/edit", "Regional edit route page"],
    ["/regional/resource%2042", "Regional detail route page"],
  ])("renders protected non-registry route %s", async (path, heading) => {
    window.history.pushState(null, "", path);

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });
});

describe("App accounting routes", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it.each(accountingRouteCases)(
    "renders accounting route %s through the route title wrapper",
    async (path, title, heading) => {
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(document.title).toBe(title));
    }
  );
});

describe("App legacy redirects and fallback routes", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it.each([
    [
      "/human-resources/leave-requests/request%2042",
      "/human-resources/leave/requests/request%2042",
      "Leave request detail · SARAISE",
      "Registry leave request detail page",
    ],
    [
      "/human-resources/leave-requests/request%2042/edit",
      "/human-resources/leave/requests/request%2042/edit",
      "Edit leave request · SARAISE",
      "Registry leave request edit page",
    ],
    [
      "/document-intelligence",
      "/document-intelligence/extractions",
      "Extraction evidence · SARAISE",
      "Registry document intelligence extractions page",
    ],
    [
      "/accounting-finance/posting-periods/period%2042",
      "/accounting-finance/periods/period%2042",
      "Posting period detail · SARAISE",
      "Accounting posting period detail page",
    ],
    [
      "/accounting-finance/posting-periods/period%2042/edit",
      "/accounting-finance/periods/period%2042/edit",
      "Edit posting period · SARAISE",
      "Accounting posting period edit page",
    ],
    [
      "/billing/subscriptions/subscription%2042",
      "/billing-subscriptions/subscription%2042",
      "Billing subscription detail · SARAISE",
      "Billing subscription detail page",
    ],
    [
      "/billing/subscriptions",
      "/billing-subscriptions",
      "Billing subscriptions · SARAISE",
      "Billing subscriptions list page",
    ],
    [
      "/billing/subscriptions/new",
      "/billing-subscriptions/create",
      "Create billing subscription · SARAISE",
      "Billing subscription create page",
    ],
    [
      "/localization/new",
      "/localization/create",
      "Create localization resource · SARAISE",
      "Localization create page",
    ],
    [
      "/notifications/inbox",
      "/notifications",
      "Notification inbox · SARAISE",
      "Notification center route page",
    ],
    ["/regional/currencies", "/regional", "", "Regional list route page"],
    ["/regional/taxes", "/regional", "", "Regional list route page"],
    ["/regional/calendars", "/regional", "", "Regional list route page"],
  ])(
    "redirects legacy or module root route %s into the migrated registry route",
    async (legacyPath, expectedPath, title, heading) => {
      window.history.pushState(null, "", legacyPath);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(window.location.pathname).toBe(expectedPath));
      await waitFor(() => expect(document.title).toBe(title));
    }
  );

  it("sets a human-readable title for unmatched routes", async () => {
    window.history.pushState(null, "", "/missing-route");

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    expect(screen.getByText("Page not found")).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Page not found · SARAISE"));
  });
});

describe("App email marketing legacy redirects", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it.each([
    ["/email-marketing/recipients/person%2042", "/email-marketing/delivery/recipients/person%2042"],
    ["/email-marketing/deliveries/attempt%2042", "/email-marketing/delivery/attempts/attempt%2042"],
  ])("redirects legacy email marketing delivery route %s", async (legacyPath, expectedPath) => {
    window.history.pushState(null, "", legacyPath);

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    await waitFor(() => expect(window.location.pathname).toBe(expectedPath));
  });
});

describe("App license settings routes", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
    vi.unstubAllEnvs();
  });

  it.each(["/license/settings", "/settings/license"])(
    "redirects non-self-hosted license route %s to user settings",
    async (path) => {
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(
        await screen.findByRole("heading", { name: "User settings page" })
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: "License settings page" })
      ).not.toBeInTheDocument();
      await waitFor(() => expect(window.location.pathname).toBe("/settings"));
      await waitFor(() => expect(document.title).toBe("User settings · SARAISE"));
    }
  );

  it.each(["/license/settings", "/settings/license"])(
    "renders self-hosted license route %s",
    async (path) => {
      vi.stubEnv("VITE_SARAISE_MODE", "self-hosted");
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(
        await screen.findByRole("heading", { name: "License settings page" })
      ).toBeInTheDocument();
      await waitFor(() => expect(window.location.pathname).toBe(path));
      await waitFor(() => expect(document.title).toBe("License settings · SARAISE"));
    }
  );
});
