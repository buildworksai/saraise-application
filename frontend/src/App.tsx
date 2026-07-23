import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { AnimatePresence } from "framer-motion";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ModuleLayout } from "./components/layout/ModuleLayout";
import { RoleBasedRedirect } from "./components/auth/RoleBasedRedirect";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ForgotPasswordForm } from "./components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "./components/auth/ResetPasswordForm";
import {
  getTenantRoutesForMode,
  tenantRoutes,
} from "./navigation/tenant-route-registry";
import { ROUTES as REGIONAL_ROUTES } from "./modules/regional/contracts";

const registryTenantRoutes = getTenantRoutesForMode(
  tenantRoutes,
  import.meta.env.VITE_SARAISE_MODE,
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
  import(
    "./modules/ai_provider_configuration/pages/AiProviderConfigurationListPage"
  ).then((m) => ({
    default: m.AiProviderConfigurationListPage,
  }))
);

const AiProviderConfigurationDetailPage = lazy(() =>
  import(
    "./modules/ai_provider_configuration/pages/AiProviderConfigurationDetailPage"
  ).then((m) => ({
    default: m.AiProviderConfigurationDetailPage,
  }))
);

const CreateAiProviderConfigurationResourcePage = lazy(() =>
  import(
    "./modules/ai_provider_configuration/pages/CreateAiProviderConfigurationResourcePage"
  ).then((m) => ({
    default: m.CreateAiProviderConfigurationResourcePage,
  }))
);

const SecretManagementPage = lazy(() =>
  import("./modules/ai_provider_configuration/pages/SecretManagementPage").then(
    (m) => ({
      default: m.SecretManagementPage,
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
  import("./modules/data_migration/pages/DataMigrationDetailPage").then(
    (m) => ({
      default: m.DataMigrationDetailPage,
    })
  )
);

const CreateDataMigrationResourcePage = lazy(() =>
  import("./modules/data_migration/pages/CreateDataMigrationResourcePage").then(
    (m) => ({
      default: m.CreateDataMigrationResourcePage,
    })
  )
);

const BillingSubscriptionsListPage = lazy(() =>
  import(
    "./modules/billing_subscriptions/pages/BillingSubscriptionsListPage"
  ).then((m) => ({
    default: m.BillingSubscriptionsListPage,
  }))
);

const BillingSubscriptionsDetailPage = lazy(() =>
  import(
    "./modules/billing_subscriptions/pages/BillingSubscriptionsDetailPage"
  ).then((m) => ({
    default: m.BillingSubscriptionsDetailPage,
  }))
);

const CreateBillingSubscriptionsResourcePage = lazy(() =>
  import(
    "./modules/billing_subscriptions/pages/CreateBillingSubscriptionsResourcePage"
  ).then((m) => ({
    default: m.CreateBillingSubscriptionsResourcePage,
  }))
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
  import("./modules/localization/pages/CreateLocalizationResourcePage").then(
    (m) => ({
      default: m.CreateLocalizationResourcePage,
    })
  )
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
  import("./modules/accounting_finance/pages/AccountListPage").then((m) => ({
    default: m.AccountListPage,
  }))
);
const AccountingAccountDetailPage = lazy(() =>
  import("./modules/accounting_finance/pages/AccountDetailPage").then((m) => ({
    default: m.AccountDetailPage,
  }))
);
const CreateAccountingAccountPage = lazy(() =>
  import("./modules/accounting_finance/pages/CreateAccountPage").then((m) => ({
    default: m.CreateAccountPage,
  }))
);

// Inventory Management
const InventoryWarehouseListPage = lazy(() =>
  import("./modules/inventory_management/pages/WarehouseListPage").then((m) => ({
    default: m.WarehouseListPage,
  }))
);
const InventoryWarehouseDetailPage = lazy(() =>
  import("./modules/inventory_management/pages/WarehouseDetailPage").then((m) => ({
    default: m.WarehouseDetailPage,
  }))
);
const CreateInventoryWarehousePage = lazy(() =>
  import("./modules/inventory_management/pages/CreateWarehousePage").then((m) => ({
    default: m.CreateWarehousePage,
  }))
);
// Bank Reconciliation
const BankAccountListPage = lazy(() =>
  import("./modules/bank_reconciliation/pages/BankAccountListPage").then((m) => ({
    default: m.BankAccountListPage,
  }))
);
const BankAccountDetailPage = lazy(() =>
  import("./modules/bank_reconciliation/pages/BankAccountDetailPage").then((m) => ({
    default: m.BankAccountDetailPage,
  }))
);
const CreateBankAccountPage = lazy(() =>
  import("./modules/bank_reconciliation/pages/CreateBankAccountPage").then((m) => ({
    default: m.CreateBankAccountPage,
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

// Asset Management
const AssetListPage = lazy(() =>
  import("./modules/asset_management/pages/AssetListPage").then((m) => ({
    default: m.AssetListPage,
  }))
);
const AssetDetailPage = lazy(() =>
  import("./modules/asset_management/pages/AssetDetailPage").then((m) => ({
    default: m.AssetDetailPage,
  }))
);
const CreateAssetPage = lazy(() =>
  import("./modules/asset_management/pages/CreateAssetPage").then((m) => ({
    default: m.CreateAssetPage,
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

// Workflow Automation Components
const WorkflowListPage = lazy(() =>
  import("./modules/workflow_automation/pages/WorkflowListPage").then((m) => ({
    default: m.WorkflowListPage,
  }))
);
const WorkflowCreatePage = lazy(() =>
  import("./modules/workflow_automation/pages/WorkflowCreatePage").then((m) => ({
    default: m.WorkflowCreatePage,
  }))
);
const TaskInboxPage = lazy(() =>
  import("./modules/workflow_automation/pages/TaskInboxPage").then((m) => ({
    default: m.TaskInboxPage,
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

// Security & Access Control Pages
const RolesPage = lazy(() =>
  import("./modules/security_access_control/pages/RolesPage").then((m) => ({
    default: m.RolesPage,
  }))
);

const PermissionsPage = lazy(() =>
  import("./modules/security_access_control/pages/PermissionsPage").then(
    (m) => ({
      default: m.PermissionsPage,
    })
  )
);

const PermissionSetsPage = lazy(() =>
  import("./modules/security_access_control/pages/PermissionSetsPage").then(
    (m) => ({
      default: m.PermissionSetsPage,
    })
  )
);

const SecurityAuditLogPage = lazy(() =>
  import("./modules/security_access_control/pages/AuditLogPage").then((m) => ({
    default: m.AuditLogPage,
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
  import("./modules/platform_management/pages/LicenseSettingsPage").then(
    (m) => ({
      default: m.LicenseSettingsPage,
    })
  )
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
    if (!title) return undefined;
    const previousTitle = document.title;
    document.title = title.endsWith("· SARAISE") ? title : `${title} · SARAISE`;
    return () => {
      document.title = previousTitle;
    };
  }, [title]);

  return children;
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
                  <TenantDashboard />
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
                  <TenantListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/tenant-management/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantDetailPage />
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
                  <ProfilePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SettingsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {import.meta.env.VITE_SARAISE_MODE === "self-hosted" && (
            <Route
              path="/settings/license"
              element={
                <ProtectedRoute>
                  <ModuleLayout>
                    <LicenseSettingsPage />
                  </ModuleLayout>
                </ProtectedRoute>
              }
            />
          )}

          {/* Workflow Automation Routes */}
          <Route
            path="/workflow-automation/workflows"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <WorkflowListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-automation/workflows/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <WorkflowCreatePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-automation/tasks"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TaskInboxPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Security & Access Control routes */}
          <Route
            path="/security-access-control/roles"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RolesPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/permissions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PermissionsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/permission-sets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PermissionSetsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/audit-logs"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SecurityAuditLogPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Accounting & Finance */}
          <Route
            path="/accounting-finance/accounts"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountingAccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/accounts/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAccountingAccountPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting-finance/accounts/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountingAccountDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Inventory Management */}
          <Route
            path="/inventory-management/warehouses"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <InventoryWarehouseListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/inventory-management/warehouses/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateInventoryWarehousePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/inventory-management/warehouses/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <InventoryWarehouseDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Bank Reconciliation */}
          <Route
            path="/bank-reconciliation/accounts"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BankAccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/bank-reconciliation/accounts/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBankAccountPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/bank-reconciliation/accounts/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BankAccountDetailPage />
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

          {/* Asset Management */}
          <Route
            path="/asset-management/assets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AssetListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/asset-management/assets/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAssetPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/asset-management/assets/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AssetDetailPage />
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

          {/* 404 */}
          <Route path="*" element={<div className="p-8">Page not found</div>} />

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
                  <NotificationCenterPage />
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

          {/* BillingSubscriptions routes */}
          <Route
            path="/billing-subscriptions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BillingSubscriptionsListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing-subscriptions/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBillingSubscriptionsResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing-subscriptions/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BillingSubscriptionsDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/billing/quotas"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <QuotaManagementPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Localization routes */}
          <Route
            path="/localization"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LocalizationListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/localization/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateLocalizationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/localization/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LocalizationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Regional routes */}
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

          {/* Migration shim: module-owned routes coexist with the legacy inventory.
              Remove matching legacy declarations as each module completes migration. */}
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
