import { BrowserRouter, Routes, Route, useLocation, Navigate, Outlet } from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";
import { AnimatePresence } from "framer-motion";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ModuleLayout } from "./components/layout/ModuleLayout";
import { RoleBasedRedirect } from "./components/auth/RoleBasedRedirect";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ForgotPasswordForm } from "./components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "./components/auth/ResetPasswordForm";
import { ModuleUnavailablePage } from "./components/modules/ModuleUnavailablePage";

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

// Lazy load Foundation module pages
const WorkflowAutomationListPage = lazy(() =>
  import("./modules/workflow_automation/pages/WorkflowAutomationListPage").then(
    (m) => ({
      default: m.WorkflowAutomationListPage,
    })
  )
);

const WorkflowAutomationDetailPage = lazy(() =>
  import(
    "./modules/workflow_automation/pages/WorkflowAutomationDetailPage"
  ).then((m) => ({
    default: m.WorkflowAutomationDetailPage,
  }))
);

const CreateWorkflowAutomationResourcePage = lazy(() =>
  import(
    "./modules/workflow_automation/pages/CreateWorkflowAutomationResourcePage"
  ).then((m) => ({
    default: m.CreateWorkflowAutomationResourcePage,
  }))
);




const IntegrationPlatformListPage = lazy(() =>
  import(
    "./modules/integration_platform/pages/IntegrationPlatformListPage"
  ).then((m) => ({
    default: m.IntegrationPlatformListPage,
  }))
);

const IntegrationPlatformDetailPage = lazy(() =>
  import(
    "./modules/integration_platform/pages/IntegrationPlatformDetailPage"
  ).then((m) => ({
    default: m.IntegrationPlatformDetailPage,
  }))
);

const CreateIntegrationPlatformResourcePage = lazy(() =>
  import(
    "./modules/integration_platform/pages/CreateIntegrationPlatformResourcePage"
  ).then((m) => ({
    default: m.CreateIntegrationPlatformResourcePage,
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










const DmsListPage = lazy(() =>
  import("./modules/dms/pages/DmsListPage").then((m) => ({
    default: m.DmsListPage,
  }))
);

const DmsDetailPage = lazy(() =>
  import("./modules/dms/pages/DmsDetailPage").then((m) => ({
    default: m.DmsDetailPage,
  }))
);

const CreateDmsResourcePage = lazy(() =>
  import("./modules/dms/pages/CreateDmsResourcePage").then((m) => ({
    default: m.CreateDmsResourcePage,
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

// Human Resources
const HrEmployeeListPage = lazy(() =>
  import("./modules/human_resources/pages/EmployeeListPage").then((m) => ({
    default: m.EmployeeListPage,
  }))
);
const HrEmployeeDetailPage = lazy(() =>
  import("./modules/human_resources/pages/EmployeeDetailPage").then((m) => ({
    default: m.EmployeeDetailPage,
  }))
);
const CreateHrEmployeePage = lazy(() =>
  import("./modules/human_resources/pages/CreateEmployeePage").then((m) => ({
    default: m.CreateEmployeePage,
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

// Business Intelligence
const BiReportListPage = lazy(() =>
  import("./modules/business_intelligence/pages/ReportListPage").then((m) => ({
    default: m.ReportListPage,
  }))
);
const BiReportDetailPage = lazy(() =>
  import("./modules/business_intelligence/pages/ReportDetailPage").then((m) => ({
    default: m.ReportDetailPage,
  }))
);
const CreateBiReportPage = lazy(() =>
  import("./modules/business_intelligence/pages/CreateReportPage").then((m) => ({
    default: m.CreateReportPage,
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

// Fixed Assets
const FixedAssetListPage = lazy(() =>
  import("./modules/fixed_assets/pages/FixedAssetListPage").then((m) => ({
    default: m.FixedAssetListPage,
  }))
);
const FixedAssetDetailPage = lazy(() =>
  import("./modules/fixed_assets/pages/FixedAssetDetailPage").then((m) => ({
    default: m.FixedAssetDetailPage,
  }))
);
const CreateFixedAssetPage = lazy(() =>
  import("./modules/fixed_assets/pages/CreateFixedAssetPage").then((m) => ({
    default: m.CreateFixedAssetPage,
  }))
);

// Compliance Management

// Compliance Risk Management

// Email Marketing
const EmailCampaignListPage = lazy(() =>
  import("./modules/email_marketing/pages/EmailCampaignListPage").then((m) => ({
    default: m.EmailCampaignListPage,
  }))
);
const EmailCampaignDetailPage = lazy(() =>
  import("./modules/email_marketing/pages/EmailCampaignDetailPage").then((m) => ({
    default: m.EmailCampaignDetailPage,
  }))
);
const CreateEmailCampaignPage = lazy(() =>
  import("./modules/email_marketing/pages/CreateEmailCampaignPage").then((m) => ({
    default: m.CreateEmailCampaignPage,
  }))
);

// Master Data Management
const MasterDataEntityListPage = lazy(() =>
  import("./modules/master_data_management/pages/MasterDataEntityListPage").then((m) => ({
    default: m.MasterDataEntityListPage,
  }))
);
const MasterDataEntityDetailPage = lazy(() =>
  import("./modules/master_data_management/pages/MasterDataEntityDetailPage").then((m) => ({
    default: m.MasterDataEntityDetailPage,
  }))
);
const CreateMasterDataEntityPage = lazy(() =>
  import("./modules/master_data_management/pages/CreateMasterDataEntityPage").then((m) => ({
    default: m.CreateMasterDataEntityPage,
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

// Lazy load pages for code splitting
const AgentListPage = lazy(() =>
  import("./modules/ai_agent_management/pages/AgentListPage").then((m) => ({
    default: m.AgentListPage,
  }))
);

const AgentDetailPage = lazy(() =>
  import("./modules/ai_agent_management/pages/AgentDetailPage").then((m) => ({
    default: m.AgentDetailPage,
  }))
);

const CreateAgentPage = lazy(() =>
  import("./modules/ai_agent_management/pages/CreateAgentPage").then((m) => ({
    default: m.CreateAgentPage,
  }))
);

const ExecutionMonitorPage = lazy(() =>
  import("./modules/ai_agent_management/pages/ExecutionMonitorPage").then(
    (m) => ({
      default: m.ExecutionMonitorPage,
    })
  )
);

const ApprovalQueuePage = lazy(() =>
  import("./modules/ai_agent_management/pages/ApprovalQueuePage").then((m) => ({
    default: m.ApprovalQueuePage,
  }))
);

// Workflow Automation Components
const WorkflowListPage = lazy(() =>
  import("./modules/workflow_automation/pages/WorkflowListPage").then((m) => ({
    default: m.WorkflowListPage,
  }))
);
const WorkflowBuilder = lazy(() =>
  import("./modules/workflow_automation/components/WorkflowBuilder").then(
    (m) => ({
      default: m.WorkflowBuilder,
    })
  )
);
const TaskInboxPage = lazy(() =>
  import("./modules/workflow_automation/pages/TaskInboxPage").then((m) => ({
    default: m.TaskInboxPage,
  }))
);

// ⚠️ ARCHITECTURAL NOTE: Platform Management UI removed
// Platform dashboards, settings, and feature flags MUST be in a separate
// platform frontend (saraise-platform/frontend/), not in the application frontend.
// The application frontend serves tenant-scoped users only.

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


interface ProtectedRouteDefinition {
  path: string;
  element: ReactNode;
}

const protectedRoutes: ProtectedRouteDefinition[] = [
  { path: "/", element: (<RoleBasedRedirect />) },
  { path: "/tenant/dashboard", element: (<TenantDashboard />) },
  { path: "/ai-agents", element: (<AgentListPage />) },
  { path: "/ai-agents/create", element: (<CreateAgentPage />) },
  { path: "/ai-agents/:id", element: (<AgentDetailPage />) },
  { path: "/ai-agents/executions", element: (<ExecutionMonitorPage />) },
  { path: "/ai-agents/approvals", element: (<ApprovalQueuePage />) },
  { path: "/tenant-management", element: (<TenantListPage />) },
  { path: "/tenant-management/:id", element: (<TenantDetailPage />) },
  { path: "/profile", element: (<ProfilePage />) },
  { path: "/settings", element: (<SettingsPage />) },
  { path: "/settings/license", element: (<LicenseSettingsPage />) },
  { path: "/metadata", element: (<SchemaEditorPage />) },
  { path: "/workflow-automation/workflows", element: (<WorkflowListPage />) },
  { path: "/workflow-automation/workflows/new", element: (<WorkflowBuilder />) },
  { path: "/workflow-automation/tasks", element: (<TaskInboxPage />) },
  { path: "/security-access-control/roles", element: (<RolesPage />) },
  { path: "/security-access-control/permissions", element: (<PermissionsPage />) },
  { path: "/security-access-control/permission-sets", element: (<PermissionSetsPage />) },
  { path: "/security-access-control/audit-logs", element: (<SecurityAuditLogPage />) },
  { path: "/accounting-finance/accounts", element: (<AccountingAccountListPage />) },
  { path: "/accounting-finance/accounts/new", element: (<CreateAccountingAccountPage />) },
  { path: "/accounting-finance/accounts/:id", element: (<AccountingAccountDetailPage />) },
  { path: "/sales-management/customers", element: (<SalesCustomerListPage />) },
  { path: "/sales-management/customers/new", element: (<CreateSalesCustomerPage />) },
  { path: "/sales-management/customers/:id", element: (<SalesCustomerDetailPage />) },
  { path: "/purchase-management/suppliers", element: (<PurchaseSupplierListPage />) },
  { path: "/purchase-management/suppliers/new", element: (<CreatePurchaseSupplierPage />) },
  { path: "/purchase-management/suppliers/:id", element: (<PurchaseSupplierDetailPage />) },
  { path: "/inventory-management/warehouses", element: (<InventoryWarehouseListPage />) },
  { path: "/inventory-management/warehouses/new", element: (<CreateInventoryWarehousePage />) },
  { path: "/inventory-management/warehouses/:id", element: (<InventoryWarehouseDetailPage />) },
  { path: "/human-resources/employees", element: (<HrEmployeeListPage />) },
  { path: "/human-resources/employees/new", element: (<CreateHrEmployeePage />) },
  { path: "/human-resources/employees/:id", element: (<HrEmployeeDetailPage />) },
  { path: "/project-management/projects", element: (<ProjectListPage />) },
  { path: "/project-management/projects/new", element: (<CreateProjectPage />) },
  { path: "/project-management/projects/:id", element: (<ProjectDetailPage />) },
  { path: "/business-intelligence/reports", element: (<BiReportListPage />) },
  { path: "/business-intelligence/reports/new", element: (<CreateBiReportPage />) },
  { path: "/business-intelligence/reports/:id", element: (<BiReportDetailPage />) },
  { path: "/bank-reconciliation/accounts", element: (<BankAccountListPage />) },
  { path: "/bank-reconciliation/accounts/new", element: (<CreateBankAccountPage />) },
  { path: "/bank-reconciliation/accounts/:id", element: (<BankAccountDetailPage />) },
  { path: "/budget-management/budgets", element: (<BudgetListPage />) },
  { path: "/budget-management/budgets/new", element: (<CreateBudgetPage />) },
  { path: "/budget-management/budgets/:id", element: (<BudgetDetailPage />) },
  { path: "/asset-management/assets", element: (<AssetListPage />) },
  { path: "/asset-management/assets/new", element: (<CreateAssetPage />) },
  { path: "/asset-management/assets/:id", element: (<AssetDetailPage />) },
  { path: "/fixed-assets/assets", element: (<FixedAssetListPage />) },
  { path: "/fixed-assets/assets/new", element: (<CreateFixedAssetPage />) },
  { path: "/fixed-assets/assets/:id", element: (<FixedAssetDetailPage />) },
  { path: "/email-marketing/campaigns", element: (<EmailCampaignListPage />) },
  { path: "/email-marketing/campaigns/new", element: (<CreateEmailCampaignPage />) },
  { path: "/email-marketing/campaigns/:id", element: (<EmailCampaignDetailPage />) },
  { path: "/master-data/entities", element: (<MasterDataEntityListPage />) },
  { path: "/master-data/entities/new", element: (<CreateMasterDataEntityPage />) },
  { path: "/master-data/entities/:id", element: (<MasterDataEntityDetailPage />) },
  { path: "/multi-company/companies", element: (<MultiCompanyListPage />) },
  { path: "/multi-company/companies/new", element: (<CreateMultiCompanyPage />) },
  { path: "/multi-company/companies/:id", element: (<MultiCompanyDetailPage />) },
  { path: "/workflow-automation", element: (<WorkflowAutomationListPage />) },
  { path: "/workflow-automation/create", element: (<CreateWorkflowAutomationResourcePage />) },
  { path: "/workflow-automation/:id", element: (<WorkflowAutomationDetailPage />) },
  { path: "/integration-platform", element: (<IntegrationPlatformListPage />) },
  { path: "/integration-platform/create", element: (<CreateIntegrationPlatformResourcePage />) },
  { path: "/integration-platform/:id", element: (<IntegrationPlatformDetailPage />) },
  { path: "/ai-provider-configuration", element: (<AiProviderConfigurationListPage />) },
  { path: "/ai-provider-configuration/create", element: (<CreateAiProviderConfigurationResourcePage />) },
  { path: "/ai-provider-configuration/:id", element: (<AiProviderConfigurationDetailPage />) },
  { path: "/ai-providers/secrets", element: (<SecretManagementPage />) },
  { path: "/notifications", element: (<NotificationCenterPage />) },
  { path: "/dms", element: (<DmsListPage />) },
  { path: "/dms/create", element: (<CreateDmsResourcePage />) },
  { path: "/dms/:id", element: (<DmsDetailPage />) },
  { path: "/data-migration", element: (<DataMigrationListPage />) },
  { path: "/data-migration/jobs/new", element: (<CreateDataMigrationResourcePage />) },
  { path: "/data-migration/create", element: (<CreateDataMigrationResourcePage />) },
  { path: "/data-migration/jobs/:id", element: (<DataMigrationDetailPage />) },
  { path: "/data-migration/:id", element: (<DataMigrationDetailPage />) },
  { path: "/metadata-modeling", element: (<MetadataModelingListPage />) },
  { path: "/metadata-modeling/create", element: (<CreateMetadataModelingResourcePage />) },
  { path: "/metadata-modeling/:id", element: (<MetadataModelingDetailPage />) },
  { path: "/billing-subscriptions", element: (<BillingSubscriptionsListPage />) },
  { path: "/billing-subscriptions/create", element: (<CreateBillingSubscriptionsResourcePage />) },
  { path: "/billing-subscriptions/:id", element: (<BillingSubscriptionsDetailPage />) },
  { path: "/billing/quotas", element: (<QuotaManagementPage />) },
  { path: "/localization", element: (<LocalizationListPage />) },
  { path: "/localization/create", element: (<CreateLocalizationResourcePage />) },
  { path: "/localization/:id", element: (<LocalizationDetailPage />) },
  { path: "/crm/dashboard", element: (<SalesDashboardPage />) },
  { path: "/crm/leads", element: (<LeadListPage />) },
  { path: "/crm/leads/new", element: (<LeadListPage />) },
  { path: "/crm/leads/qualified", element: (<LeadListPage />) },
  { path: "/crm/leads/converted", element: (<LeadListPage />) },
  { path: "/crm/leads/:id", element: (<LeadDetailPage />) },
  { path: "/crm/contacts", element: (<ContactListPage />) },
  { path: "/crm/contacts/:id", element: (<ContactDetailPage />) },
  { path: "/crm/accounts", element: (<AccountListPage />) },
  { path: "/crm/accounts/customers", element: (<AccountListPage />) },
  { path: "/crm/accounts/prospects", element: (<AccountListPage />) },
  { path: "/crm/accounts/hierarchy", element: (<AccountListPage />) },
  { path: "/crm/accounts/:id", element: (<AccountDetailPage />) },
  { path: "/crm/opportunities", element: (<OpportunityListPage />) },
  { path: "/crm/opportunities/pipeline", element: (<OpportunityKanbanPage />) },
  { path: "/crm/opportunities/my", element: (<OpportunityListPage />) },
  { path: "/crm/opportunities/closed", element: (<OpportunityListPage />) },
  { path: "/crm/opportunities/:id", element: (<OpportunityDetailPage />) },
  { path: "/crm", element: (<Navigate to="/crm/dashboard" replace />) },
  { path: "/api-management/*", element: (<ModuleUnavailablePage moduleName="API Management" />) },
  { path: "/automation-orchestration/*", element: (<ModuleUnavailablePage moduleName="Automation Orchestration" />) },
  { path: "/backup-disaster-recovery/*", element: (<ModuleUnavailablePage moduleName="Backup and Disaster Recovery" />) },
  { path: "/backup-recovery/*", element: (<ModuleUnavailablePage moduleName="Backup and Recovery" />) },
  { path: "/blockchain-traceability/*", element: (<ModuleUnavailablePage moduleName="Blockchain Traceability" />) },
  { path: "/communication-hub/*", element: (<ModuleUnavailablePage moduleName="Communication Hub" />) },
  { path: "/compliance-management/*", element: (<ModuleUnavailablePage moduleName="Compliance Management" />) },
  { path: "/compliance-risk-management/*", element: (<ModuleUnavailablePage moduleName="Compliance and Risk Management" />) },
  { path: "/customization-framework/*", element: (<ModuleUnavailablePage moduleName="Customization Framework" />) },
  { path: "/document-intelligence/*", element: (<ModuleUnavailablePage moduleName="Document Intelligence" />) },
  { path: "/performance-monitoring/*", element: (<ModuleUnavailablePage moduleName="Performance Monitoring" />) },
  { path: "/process-mining/*", element: (<ModuleUnavailablePage moduleName="Process Mining" />) },
  { path: "/regional/*", element: (<ModuleUnavailablePage moduleName="Regional" />) },
];

function ProtectedModuleRoute() {
  return (
    <ProtectedRoute>
      <ModuleLayout>
        <Outlet />
      </ModuleLayout>
    </ProtectedRoute>
  );
}

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
          <Route element={<ProtectedModuleRoute />}>
            {protectedRoutes.map(({ path, element }) => (
              <Route key={path} path={path} element={element} />
            ))}
          </Route>
          <Route path="*" element={<div className="p-8">Page not found</div>} />
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
