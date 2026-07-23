import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
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

const MetadataModelingListPage = lazy(() =>
  import("./modules/metadata_modeling/pages/MetadataModelingListPage").then(
    (m) => ({
      default: m.MetadataModelingListPage,
    })
  )
);

const MetadataModelingDetailPage = lazy(() =>
  import("./modules/metadata_modeling/pages/MetadataModelingDetailPage").then(
    (m) => ({
      default: m.MetadataModelingDetailPage,
    })
  )
);

const CreateMetadataModelingResourcePage = lazy(() =>
  import(
    "./modules/metadata_modeling/pages/CreateMetadataModelingResourcePage"
  ).then((m) => ({
    default: m.CreateMetadataModelingResourcePage,
  }))
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

// Sales Management
const SalesCustomerListPage = lazy(() =>
  import("./modules/sales_management/pages/CustomerListPage").then((m) => ({
    default: m.CustomerListPage,
  }))
);
const SalesCustomerDetailPage = lazy(() =>
  import("./modules/sales_management/pages/CustomerDetailPage").then((m) => ({
    default: m.CustomerDetailPage,
  }))
);
const CreateSalesCustomerPage = lazy(() =>
  import("./modules/sales_management/pages/CreateCustomerPage").then((m) => ({
    default: m.CreateCustomerPage,
  }))
);

// Purchase Management
const PurchaseSupplierListPage = lazy(() =>
  import("./modules/purchase_management/pages/SupplierListPage").then((m) => ({
    default: m.SupplierListPage,
  }))
);
const PurchaseSupplierDetailPage = lazy(() =>
  import("./modules/purchase_management/pages/SupplierDetailPage").then((m) => ({
    default: m.SupplierDetailPage,
  }))
);
const CreatePurchaseSupplierPage = lazy(() =>
  import("./modules/purchase_management/pages/CreateSupplierPage").then((m) => ({
    default: m.CreateSupplierPage,
  }))
);

// Project Management
const ProjectListPage = lazy(() =>
  import("./modules/project_management/pages/ProjectListPage").then((m) => ({
    default: m.ProjectListPage,
  }))
);
const ProjectDetailPage = lazy(() =>
  import("./modules/project_management/pages/ProjectDetailPage").then((m) => ({
    default: m.ProjectDetailPage,
  }))
);
const CreateProjectPage = lazy(() =>
  import("./modules/project_management/pages/CreateProjectPage").then((m) => ({
    default: m.CreateProjectPage,
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

// Multi-Company
const MultiCompanyListPage = lazy(() =>
  import("./modules/multi_company/pages/CompanyListPage").then((m) => ({
    default: m.CompanyListPage,
  }))
);
const MultiCompanyDetailPage = lazy(() =>
  import("./modules/multi_company/pages/CompanyDetailPage").then((m) => ({
    default: m.CompanyDetailPage,
  }))
);
const CreateMultiCompanyPage = lazy(() =>
  import("./modules/multi_company/pages/CreateCompanyPage").then((m) => ({
    default: m.CreateCompanyPage,
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

const SchemaEditorPage = lazy(() =>
  import("./modules/metadata_modeling/pages/SchemaEditorPage").then((m) => ({
    default: m.SchemaEditorPage,
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
    if (!title) return undefined;
    const previousTitle = document.title;
    document.title = `${title} · SARAISE`;
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

          {/* Metadata Modeling Routes */}
          <Route
            path="/metadata"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SchemaEditorPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

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

          {/* Sales Management */}
          <Route
            path="/sales-management/customers"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SalesCustomerListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/sales-management/customers/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateSalesCustomerPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/sales-management/customers/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SalesCustomerDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Purchase Management */}
          <Route
            path="/purchase-management/suppliers"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PurchaseSupplierListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/purchase-management/suppliers/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreatePurchaseSupplierPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/purchase-management/suppliers/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PurchaseSupplierDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Project Management */}
          <Route
            path="/project-management/projects"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ProjectListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/project-management/projects/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateProjectPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/project-management/projects/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ProjectDetailPage />
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

          {/* Multi-Company */}
          <Route
            path="/multi-company/companies"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MultiCompanyListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/multi-company/companies/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateMultiCompanyPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/multi-company/companies/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MultiCompanyDetailPage />
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
          {/* MetadataModeling routes */}
          <Route
            path="/metadata-modeling"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MetadataModelingListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/metadata-modeling/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateMetadataModelingResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/metadata-modeling/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MetadataModelingDetailPage />
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
            path="/regional"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RegionalListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/regional/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateRegionalResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/regional/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RegionalDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* CRM Module Routes */}
          <Route
            path="/crm"
            element={
              <Navigate to="/crm/dashboard" replace />
            }
          />
          <Route
            path="/crm/dashboard"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SalesDashboardPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Leads Routes */}
          <Route
            path="/crm/leads"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LeadListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/leads/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LeadListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/leads/qualified"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LeadListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/leads/converted"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LeadListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/leads/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <LeadDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Contacts Routes */}
          <Route
            path="/crm/contacts"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ContactListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/contacts/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ContactDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Accounts Routes */}
          <Route
            path="/crm/accounts"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/accounts/customers"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/accounts/prospects"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/accounts/hierarchy"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/accounts/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AccountDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Opportunities Routes */}
          <Route
            path="/crm/opportunities"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OpportunityListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/opportunities/pipeline"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OpportunityKanbanPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/opportunities/my"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OpportunityListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/opportunities/closed"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OpportunityListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/opportunities/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OpportunityDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          {/* Activities Routes */}
          <Route
            path="/crm/activities"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <div className="p-8">
                    <h1 className="text-3xl font-bold mb-4">Activity Log</h1>
                    <p className="text-muted-foreground">Activity log coming soon...</p>
                  </div>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/crm/activities/tasks"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <div className="p-8">
                    <h1 className="text-3xl font-bold mb-4">My Tasks</h1>
                    <p className="text-muted-foreground">Task management coming soon...</p>
                  </div>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Module-owned tenant routes are discovered once and rendered consistently. */}
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
