/* eslint-disable @typescript-eslint/no-unused-vars -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { BrowserRouter, Navigate, Routes, Route, useLocation, useParams } from "react-router-dom";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { AnimatePresence } from "framer-motion";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ModuleLayout } from "./components/layout/ModuleLayout";
import { RoleBasedRedirect } from "./components/auth/RoleBasedRedirect";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ForgotPasswordForm } from "./components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "./components/auth/ResetPasswordForm";
import { getTenantRoutesForMode, tenantRoutes } from "./navigation/tenant-route-registry";
import { ROUTES as REGIONAL_ROUTES } from "./modules/regional/contracts";
import { formatRouteTitle } from "./route-title";

const registryTenantRoutes = getTenantRoutesForMode(
  tenantRoutes,
  import.meta.env.VITE_SARAISE_MODE
);

// Public legal/support pages
const TermsOfService = lazy(() =>
  import("./pages/TermsOfService").then((m) => ({
    default: m.TermsOfService,
  }))
);
const PrivacyPolicy = lazy(() =>
  import("./pages/PrivacyPolicy").then((m) => ({
    default: m.PrivacyPolicy,
  }))
);
const Security = lazy(() =>
  import("./pages/Security").then((m) => ({
    default: m.Security,
  }))
);
const Support = lazy(() =>
  import("./pages/Support").then((m) => ({
    default: m.Support,
  }))
);

const AiProviderConfigurationListPage = lazy(() =>
  import("./modules/ai_provider_configuration/pages/AiProviderConfigurationListPage").then((m) => ({
    default: m.AiProviderConfigurationListPage,
  }))
);

const AiProviderConfigurationDetailPage = lazy(() =>
  import("./modules/ai_provider_configuration/pages/AiProviderConfigurationDetailPage").then(
    (m) => ({
      default: m.AiProviderConfigurationDetailPage,
    })
  )
);

const CreateAiProviderConfigurationResourcePage = lazy(() =>
  import(
    "./modules/ai_provider_configuration/pages/CreateAiProviderConfigurationResourcePage"
  ).then((m) => ({
    default: m.CreateAiProviderConfigurationResourcePage,
  }))
);

const SecretManagementPage = lazy(() =>
  import("./modules/ai_provider_configuration/pages/SecretManagementPage").then((m) => ({
    default: m.SecretManagementPage,
  }))
);

const AiProviderRuntimeConfigurationPage = lazy(() =>
  import("./modules/ai_provider_configuration/pages/AiProviderRuntimeConfigurationPage").then(
    (m) => ({
      default: m.AiProviderRuntimeConfigurationPage,
    })
  )
);

const NotificationCenterPage = lazy(() =>
  import("./modules/notifications/pages/NotificationCenterPage").then((m) => ({
    default: m.NotificationCenterPage,
  }))
);

const DataMigrationListPage = lazy(() =>
  import("./modules/data_migration/pages/DataMigrationListPage").then((m) => ({
    default: m.DataMigrationListPage,
  }))
);

const DataMigrationDetailPage = lazy(() =>
  import("./modules/data_migration/pages/DataMigrationDetailPage").then((m) => ({
    default: m.DataMigrationDetailPage,
  }))
);

const CreateDataMigrationResourcePage = lazy(() =>
  import("./modules/data_migration/pages/CreateDataMigrationResourcePage").then((m) => ({
    default: m.CreateDataMigrationResourcePage,
  }))
);

const BillingSubscriptionsListPage = lazy(() =>
  import("./modules/billing_subscriptions/pages/BillingSubscriptionsListPage").then((m) => ({
    default: m.BillingSubscriptionsListPage,
  }))
);

const BillingSubscriptionsDetailPage = lazy(() =>
  import("./modules/billing_subscriptions/pages/BillingSubscriptionsDetailPage").then((m) => ({
    default: m.BillingSubscriptionsDetailPage,
  }))
);

const CreateBillingSubscriptionsResourcePage = lazy(() =>
  import("./modules/billing_subscriptions/pages/CreateBillingSubscriptionsResourcePage").then(
    (m) => ({
      default: m.CreateBillingSubscriptionsResourcePage,
    })
  )
);

const QuotaManagementPage = lazy(() =>
  import("./modules/billing_subscriptions/pages/QuotaManagementPage").then((m) => ({
    default: m.QuotaManagementPage,
  }))
);

const LocalizationListPage = lazy(() =>
  import("./modules/localization/pages/LocalizationListPage").then((m) => ({
    default: m.LocalizationListPage,
  }))
);

const LocalizationDetailPage = lazy(() =>
  import("./modules/localization/pages/LocalizationDetailPage").then((m) => ({
    default: m.LocalizationDetailPage,
  }))
);

const CreateLocalizationResourcePage = lazy(() =>
  import("./modules/localization/pages/CreateLocalizationResourcePage").then((m) => ({
    default: m.CreateLocalizationResourcePage,
  }))
);

const RegionalListPage = lazy(() =>
  import("./modules/regional/pages/RegionalListPage").then((m) => ({
    default: m.RegionalListPage,
  }))
);

const RegionalDetailPage = lazy(() =>
  import("./modules/regional/pages/RegionalDetailPage").then((m) => ({
    default: m.RegionalDetailPage,
  }))
);

const CreateRegionalResourcePage = lazy(() =>
  import("./modules/regional/pages/CreateRegionalResourcePage").then((m) => ({
    default: m.CreateRegionalResourcePage,
  }))
);

const EditRegionalResourcePage = lazy(() =>
  import("./modules/regional/pages/EditRegionalResourcePage").then((m) => ({
    default: m.EditRegionalResourcePage,
  }))
);

const RegionalConfigurationPage = lazy(() =>
  import("./modules/regional/pages/RegionalConfigurationPage").then((m) => ({
    default: m.RegionalConfigurationPage,
  }))
);

// CRM Module Pages
const LeadListPage = lazy(() =>
  import("./modules/crm/pages/LeadListPage").then((m) => ({
    default: m.LeadListPage,
  }))
);

const LeadDetailPage = lazy(() =>
  import("./modules/crm/pages/LeadDetailPage").then((m) => ({
    default: m.LeadDetailPage,
  }))
);

const OpportunityListPage = lazy(() =>
  import("./modules/crm/pages/OpportunityListPage").then((m) => ({
    default: m.OpportunityListPage,
  }))
);

const OpportunityKanbanPage = lazy(() =>
  import("./modules/crm/pages/OpportunityKanbanPage").then((m) => ({
    default: m.OpportunityKanbanPage,
  }))
);

const OpportunityDetailPage = lazy(() =>
  import("./modules/crm/pages/OpportunityDetailPage").then((m) => ({
    default: m.OpportunityDetailPage,
  }))
);

const AccountListPage = lazy(() =>
  import("./modules/crm/pages/AccountListPage").then((m) => ({
    default: m.AccountListPage,
  }))
);

const AccountDetailPage = lazy(() =>
  import("./modules/crm/pages/AccountDetailPage").then((m) => ({
    default: m.AccountDetailPage,
  }))
);

const ContactListPage = lazy(() =>
  import("./modules/crm/pages/ContactListPage").then((m) => ({
    default: m.ContactListPage,
  }))
);

const ContactDetailPage = lazy(() =>
  import("./modules/crm/pages/ContactDetailPage").then((m) => ({
    default: m.ContactDetailPage,
  }))
);

const SalesDashboardPage = lazy(() =>
  import("./modules/crm/pages/SalesDashboardPage").then((m) => ({
    default: m.SalesDashboardPage,
  }))
);

// Accounting & Finance
const AccountingAccountListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.AccountListView,
  }))
);
const AccountingPostingPeriodListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.PostingPeriodListView,
  }))
);
const AccountingJournalEntryListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.JournalEntryListView,
  }))
);
const AccountingAPInvoiceListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.APInvoiceListView,
  }))
);
const AccountingARInvoiceListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.ARInvoiceListView,
  }))
);
const AccountingPaymentListPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceListPages").then((m) => ({
    default: m.PaymentListView,
  }))
);
const AccountingAccountDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.AccountDetailView,
  }))
);
const AccountingPostingPeriodDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.PostingPeriodDetailView,
  }))
);
const AccountingJournalEntryDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.JournalEntryDetailView,
  }))
);
const AccountingAPInvoiceDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.APInvoiceDetailView,
  }))
);
const AccountingARInvoiceDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.ARInvoiceDetailView,
  }))
);
const AccountingPaymentDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceDetailPages").then((m) => ({
    default: m.PaymentDetailView,
  }))
);
const CreateAccountingAccountPage = lazy(() =>
  import("./modules/accounting_finance/pages/CreateAccountPage").then((m) => ({
    default: m.CreateAccountPage,
  }))
);
const AccountingAccountFormPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceFormPages").then((m) => ({
    default: m.AccountFormPage,
  }))
);
const AccountingPostingPeriodFormPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceFormPages").then((m) => ({
    default: m.PostingPeriodFormPage,
  }))
);
const AccountingJournalEntryFormPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceFormPages").then((m) => ({
    default: m.JournalEntryFormPage,
  }))
);
const AccountingInvoiceFormPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceFormPages").then((m) => ({
    default: m.InvoiceFormPage,
  }))
);
const AccountingPaymentFormPage = lazy(() =>
  import("./modules/accounting_finance/pages/ResourceFormPages").then((m) => ({
    default: m.PaymentFormPage,
  }))
);

// Budget Management
const BudgetListPage = lazy(() =>
  import("./modules/budget_management/pages/BudgetListPage").then((m) => ({
    default: m.BudgetListPage,
  }))
);
const BudgetDetailPage = lazy(() =>
  import("./modules/budget_management/pages/BudgetDetailPage").then((m) => ({
    default: m.BudgetDetailPage,
  }))
);
const CreateBudgetPage = lazy(() =>
  import("./modules/budget_management/pages/CreateBudgetPage").then((m) => ({
    default: m.CreateBudgetPage,
  }))
);

// Compliance Management
const CompliancePolicyListPage = lazy(() =>
  import("./modules/compliance_management/pages/CompliancePolicyListPage").then((m) => ({
    default: m.CompliancePolicyListPage,
  }))
);
const CompliancePolicyDetailPage = lazy(() =>
  import("./modules/compliance_management/pages/CompliancePolicyDetailPage").then((m) => ({
    default: m.CompliancePolicyDetailPage,
  }))
);
const CreateCompliancePolicyPage = lazy(() =>
  import("./modules/compliance_management/pages/CreateCompliancePolicyPage").then((m) => ({
    default: m.CreateCompliancePolicyPage,
  }))
);

// Compliance Risk Management
const ComplianceRiskListPage = lazy(() =>
  import("./modules/compliance_risk_management/pages/ComplianceRiskListPage").then((m) => ({
    default: m.ComplianceRiskListPage,
  }))
);
const ComplianceRiskDetailPage = lazy(() =>
  import("./modules/compliance_risk_management/pages/ComplianceRiskDetailPage").then((m) => ({
    default: m.ComplianceRiskDetailPage,
  }))
);
const CreateComplianceRiskPage = lazy(() =>
  import("./modules/compliance_risk_management/pages/CreateComplianceRiskPage").then((m) => ({
    default: m.CreateComplianceRiskPage,
  }))
);

// Control Plane dashboards, settings, and feature flags are intentionally absent.
// Self-hosted license management remains as a runtime-plane exception.

// Tenant Management Pages (READ-ONLY - for display only)
// Tenant lifecycle operations MUST be performed via Control Plane APIs
const TenantListPage = lazy(() =>
  import("./modules/tenant_management/pages/TenantListPage").then((m) => ({
    default: m.TenantListPage,
  }))
);

const TenantDetailPage = lazy(() =>
  import("./modules/tenant_management/pages/TenantDetailPage").then((m) => ({
    default: m.TenantDetailPage,
  }))
);

// Tenant Dashboard (Home)
const TenantDashboard = lazy(() =>
  import("./pages/tenant/TenantDashboard").then((m) => ({
    default: m.TenantDashboard,
  }))
);

// User Profile and Settings Pages
const ProfilePage = lazy(() =>
  import("./pages/user/ProfilePage").then((m) => ({
    default: m.ProfilePage,
  }))
);

const SettingsPage = lazy(() =>
  import("./pages/user/SettingsPage").then((m) => ({
    default: m.SettingsPage,
  }))
);

const LicenseSettingsPage = lazy(() =>
  import("./modules/platform_management/pages/LicenseSettingsPage").then((m) => ({
    default: m.LicenseSettingsPage,
  }))
);

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-muted-foreground">Loading...</div>
    </div>
  );
}

function RouteTitle({ title, children }: { title?: string; children: ReactNode }) {
  useEffect(() => {
    document.title = formatRouteTitle(title);
    return undefined;
  }, [title]);

  return children;
}

function LegacyEmailMarketingRedirect({ target }: { target: "recipients" | "attempts" }) {
  const { id } = useParams();
  return (
    <Navigate to={`/email-marketing/delivery/${target}/${encodeURIComponent(id ?? "")}`} replace />
  );
}

function LegacyHumanResourcesLeaveRequestRedirect({ edit = false }: { edit?: boolean }) {
  const { id } = useParams();
  return (
    <Navigate
      to={`/human-resources/leave/requests/${encodeURIComponent(id!)}${edit ? "/edit" : ""}`}
      replace
    />
  );
}

function LegacyPostingPeriodRedirect({ edit = false }: { edit?: boolean }) {
  const { id } = useParams();
  return (
    <Navigate
      to={`/accounting-finance/periods/${encodeURIComponent(id!)}${edit ? "/edit" : ""}`}
      replace
    />
  );
}

function LegacyBillingSubscriptionRedirect() {
  const { id } = useParams();
  return <Navigate to={`/billing-subscriptions/${encodeURIComponent(id!)}`} replace />;
}

// Legacy route inventory is being migrated module-by-module into the typed registry.
// eslint-disable-next-line max-lines-per-function
function AnimatedRoutes() {
  const location = useLocation();

  return (
    <>
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
      >
        Skip to main content
      </a>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* Public routes */}
          <Route path="/login" element={<LoginForm />} />
          <Route path="/register" element={<RegisterForm />} />
          <Route path="/forgot-password" element={<ForgotPasswordForm />} />
          <Route path="/reset-password" element={<ResetPasswordForm />} />
          <Route path="/terms" element={<TermsOfService />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/security" element={<Security />} />
          <Route path="/support" element={<Support />} />

          {/* ⚠️ ARCHITECTURAL ENFORCEMENT: Platform Management UI removed
              Platform dashboards and management UI MUST be in a separate
              platform frontend (saraise-platform/frontend/), not here.
              The application frontend serves tenant-scoped users only. */}

          {/* Protected routes with ModuleLayout */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RoleBasedRedirect />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Tenant Dashboard (tenant-scoped users) */}
          <Route
            path="/tenant/dashboard"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Dashboard">
                    <TenantDashboard />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Control Plane platform routes are intentionally absent. */}

          {/* Tenant Management routes (READ-ONLY - for display only)
              ⚠️ Tenant lifecycle operations (create, update, delete) MUST be
              performed via Control Plane APIs (saraise-platform/saraise-control-plane/) */}
          <Route
            path="/tenant-management"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Tenant management">
                    <TenantListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/tenant-management/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Tenant detail">
                    <TenantDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* User Profile and Settings routes */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="User profile">
                    <ProfilePage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="User settings">
                    <SettingsPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/license/settings"
            element={
              import.meta.env.VITE_SARAISE_MODE === "self-hosted" ? (
                <ProtectedRoute>
                  <ModuleLayout>
                    <RouteTitle title="License settings">
                      <LicenseSettingsPage />
                    </RouteTitle>
                  </ModuleLayout>
                </ProtectedRoute>
              ) : (
                <Navigate to="/settings" replace />
              )
            }
          />
          <Route
            path="/settings/license"
            element={
              import.meta.env.VITE_SARAISE_MODE === "self-hosted" ? (
                <ProtectedRoute>
                  <ModuleLayout>
                    <RouteTitle title="License settings">
                      <LicenseSettingsPage />
                    </RouteTitle>
                  </ModuleLayout>
                </ProtectedRoute>
              ) : (
                <Navigate to="/settings" replace />
              )
            }
          />

          {/* Accounting & Finance */}
          <Route
            path="/accounting-finance/accounts"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Accounting accounts">
                    <AccountingAccountListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/accounts/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create accounting account">
                    <CreateAccountingAccountPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/accounts/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Accounting account detail">
                    <AccountingAccountDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/accounts/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit accounting account">
                    <AccountingAccountFormPage edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/posting-periods"
            element={<Navigate to="/accounting-finance/periods" replace />}
          />
          <Route
            path="/accounting-finance/posting-periods/new"
            element={<Navigate to="/accounting-finance/periods/new" replace />}
          />
          <Route
            path="/accounting-finance/posting-periods/:id"
            element={<LegacyPostingPeriodRedirect />}
          />
          <Route
            path="/accounting-finance/posting-periods/:id/edit"
            element={<LegacyPostingPeriodRedirect edit />}
          />
          <Route
            path="/accounting-finance/periods"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Posting periods">
                    <AccountingPostingPeriodListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/periods/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create posting period">
                    <AccountingPostingPeriodFormPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/periods/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Posting period detail">
                    <AccountingPostingPeriodDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/periods/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit posting period">
                    <AccountingPostingPeriodFormPage edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/journal-entries"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Journal entries">
                    <AccountingJournalEntryListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/journal-entries/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create journal entry">
                    <AccountingJournalEntryFormPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/journal-entries/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Journal entry detail">
                    <AccountingJournalEntryDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/journal-entries/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit journal entry">
                    <AccountingJournalEntryFormPage edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ap-invoices"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Accounts payable invoices">
                    <AccountingAPInvoiceListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ap-invoices/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create AP invoice">
                    <AccountingInvoiceFormPage kind="ap" />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ap-invoices/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="AP invoice detail">
                    <AccountingAPInvoiceDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ap-invoices/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit AP invoice">
                    <AccountingInvoiceFormPage kind="ap" edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ar-invoices"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Accounts receivable invoices">
                    <AccountingARInvoiceListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ar-invoices/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create AR invoice">
                    <AccountingInvoiceFormPage kind="ar" />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ar-invoices/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="AR invoice detail">
                    <AccountingARInvoiceDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/ar-invoices/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit AR invoice">
                    <AccountingInvoiceFormPage kind="ar" edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/payments"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Payments">
                    <AccountingPaymentListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/payments/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Record payment">
                    <AccountingPaymentFormPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/payments/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Payment detail">
                    <AccountingPaymentDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/payments/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Edit payment">
                    <AccountingPaymentFormPage edit />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Budget Management */}
          <Route
            path="/budget-management/budgets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BudgetListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/budget-management/budgets/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBudgetPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/budget-management/budgets/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BudgetDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Compliance Management */}
          <Route
            path="/compliance-management/policies"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CompliancePolicyListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/compliance-management/policies/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateCompliancePolicyPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/compliance-management/policies/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CompliancePolicyDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Compliance Risk Management */}
          <Route
            path="/compliance-risk-management/risks"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ComplianceRiskListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/compliance-risk-management/risks/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateComplianceRiskPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/compliance-risk-management/risks/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ComplianceRiskDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* AiProviderConfiguration routes */}
          <Route
            path="/ai-provider-configuration"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AiProviderConfigurationListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-provider-configuration/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAiProviderConfigurationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-provider-configuration/runtime-configuration"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AiProviderRuntimeConfigurationPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-provider-configuration/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AiProviderConfigurationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-providers/secrets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SecretManagementPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/notifications"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Notification inbox">
                    <NotificationCenterPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* DataMigration routes */}
          <Route
            path="/data-migration"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DataMigrationListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data-migration/jobs/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateDataMigrationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data-migration/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateDataMigrationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data-migration/jobs/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DataMigrationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data-migration/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DataMigrationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/document-intelligence"
            element={<Navigate to="/document-intelligence/extractions" replace />}
          />

          {/* BillingSubscriptions routes */}
          <Route
            path="/billing/subscriptions"
            element={<Navigate to="/billing-subscriptions" replace />}
          />
          <Route
            path="/billing/subscriptions/new"
            element={<Navigate to="/billing-subscriptions/create" replace />}
          />
          <Route
            path="/billing/subscriptions/:id"
            element={<LegacyBillingSubscriptionRedirect />}
          />
          <Route
            path="/billing-subscriptions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Billing subscriptions">
                    <BillingSubscriptionsListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing-subscriptions/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create billing subscription">
                    <CreateBillingSubscriptionsResourcePage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing-subscriptions/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Billing subscription detail">
                    <BillingSubscriptionsDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing/quotas"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Billing quotas">
                    <QuotaManagementPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Localization routes */}
          <Route
            path="/localization/new"
            element={<Navigate to="/localization/create" replace />}
          />
          <Route
            path="/localization"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Localization">
                    <LocalizationListPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/localization/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Create localization resource">
                    <CreateLocalizationResourcePage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/localization/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RouteTitle title="Localization detail">
                    <LocalizationDetailPage />
                  </RouteTitle>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Regional routes */}
          <Route
            path="/regional/currencies"
            element={<Navigate to={REGIONAL_ROUTES.ROOT} replace />}
          />
          <Route path="/regional/taxes" element={<Navigate to={REGIONAL_ROUTES.ROOT} replace />} />
          <Route
            path="/regional/calendars"
            element={<Navigate to={REGIONAL_ROUTES.ROOT} replace />}
          />
          <Route
            path={REGIONAL_ROUTES.ROOT}
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RegionalListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path={REGIONAL_ROUTES.CREATE}
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateRegionalResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path={REGIONAL_ROUTES.CONFIGURATION}
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RegionalConfigurationPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path={REGIONAL_ROUTES.EDIT_PATTERN}
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <EditRegionalResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path={REGIONAL_ROUTES.DETAIL_PATTERN}
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RegionalDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          <Route path="/notifications/inbox" element={<Navigate to="/notifications" replace />} />

          {/* Migration shim: module-owned routes are rendered from the typed registry. */}
          {registryTenantRoutes.map(({ id, path, title, Page }) => (
            <Route
              key={`registry:${id}`}
              path={path}
              element={
                <ProtectedRoute>
                  <ModuleLayout>
                    <RouteTitle title={title}>
                      <Page />
                    </RouteTitle>
                  </ModuleLayout>
                </ProtectedRoute>
              }
            />
          ))}
          <Route
            path="/performance-monitoring/overview"
            element={<Navigate to="/performance-monitoring/dashboard" replace />}
          />
          <Route
            path="/performance-monitoring/alert-rules"
            element={<Navigate to="/performance-monitoring/alerts/rules" replace />}
          />
          <Route
            path="/performance-monitoring/slos"
            element={<Navigate to="/performance-monitoring/sla" replace />}
          />
          <Route path="/dms" element={<Navigate to="/dms/documents" replace />} />
          <Route
            path="/inventory-management/dashboard"
            element={<Navigate to="/inventory-management" replace />}
          />
          <Route
            path="/api-management/resources"
            element={<Navigate to="/api-management" replace />}
          />
          <Route
            path="/accounting-finance"
            element={<Navigate to="/accounting-finance/accounts" replace />}
          />
          <Route
            path="/purchase-management"
            element={<Navigate to="/purchase-management/suppliers" replace />}
          />
          <Route
            path="/human-resources/leave-requests/new"
            element={<Navigate to="/human-resources/leave/requests/new" replace />}
          />
          <Route
            path="/human-resources/leave-requests/:id"
            element={<LegacyHumanResourcesLeaveRequestRedirect />}
          />
          <Route
            path="/human-resources/leave-requests/:id/edit"
            element={<LegacyHumanResourcesLeaveRequestRedirect edit />}
          />
          <Route
            path="/email-marketing/recipients/:id"
            element={<LegacyEmailMarketingRedirect target="recipients" />}
          />
          <Route
            path="/email-marketing/deliveries/:id"
            element={<LegacyEmailMarketingRedirect target="attempts" />}
          />
          <Route
            path="*"
            element={
              <RouteTitle title="Page not found">
                <div className="p-8">Page not found</div>
              </RouteTitle>
            }
          />
        </Routes>
      </AnimatePresence>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<LoadingFallback />}>
        <AnimatedRoutes />
      </Suspense>
    </BrowserRouter>
  );
}
