import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { lazy, Suspense } from "react";
import { AnimatePresence } from "framer-motion";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ModuleLayout } from "./components/layout/ModuleLayout";
import { RoleBasedRedirect } from "./components/auth/RoleBasedRedirect";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ForgotPasswordForm } from "./components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "./components/auth/ResetPasswordForm";

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

const ApiManagementListPage = lazy(() =>
  import("./modules/api_management/pages/ApiManagementListPage").then((m) => ({
    default: m.ApiManagementListPage,
  }))
);

const ApiManagementDetailPage = lazy(() =>
  import("./modules/api_management/pages/ApiManagementDetailPage").then(
    (m) => ({
      default: m.ApiManagementDetailPage,
    })
  )
);

const CreateApiManagementResourcePage = lazy(() =>
  import("./modules/api_management/pages/CreateApiManagementResourcePage").then(
    (m) => ({
      default: m.CreateApiManagementResourcePage,
    })
  )
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

const CustomizationFrameworkListPage = lazy(() =>
  import(
    "./modules/customization_framework/pages/CustomizationFrameworkListPage"
  ).then((m) => ({
    default: m.CustomizationFrameworkListPage,
  }))
);

const CustomizationFrameworkDetailPage = lazy(() =>
  import(
    "./modules/customization_framework/pages/CustomizationFrameworkDetailPage"
  ).then((m) => ({
    default: m.CustomizationFrameworkDetailPage,
  }))
);

const CreateCustomizationFrameworkResourcePage = lazy(() =>
  import(
    "./modules/customization_framework/pages/CreateCustomizationFrameworkResourcePage"
  ).then((m) => ({
    default: m.CreateCustomizationFrameworkResourcePage,
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

const AutomationOrchestrationListPage = lazy(() =>
  import(
    "./modules/automation_orchestration/pages/AutomationOrchestrationListPage"
  ).then((m) => ({
    default: m.AutomationOrchestrationListPage,
  }))
);

const AutomationOrchestrationDetailPage = lazy(() =>
  import(
    "./modules/automation_orchestration/pages/AutomationOrchestrationDetailPage"
  ).then((m) => ({
    default: m.AutomationOrchestrationDetailPage,
  }))
);

const CreateAutomationOrchestrationResourcePage = lazy(() =>
  import(
    "./modules/automation_orchestration/pages/CreateAutomationOrchestrationResourcePage"
  ).then((m) => ({
    default: m.CreateAutomationOrchestrationResourcePage,
  }))
);

const ProcessMiningListPage = lazy(() =>
  import("./modules/process_mining/pages/ProcessMiningListPage").then((m) => ({
    default: m.ProcessMiningListPage,
  }))
);

const ProcessMiningDetailPage = lazy(() =>
  import("./modules/process_mining/pages/ProcessMiningDetailPage").then(
    (m) => ({
      default: m.ProcessMiningDetailPage,
    })
  )
);

const CreateProcessMiningResourcePage = lazy(() =>
  import("./modules/process_mining/pages/CreateProcessMiningResourcePage").then(
    (m) => ({
      default: m.CreateProcessMiningResourcePage,
    })
  )
);

const DocumentIntelligenceListPage = lazy(() =>
  import(
    "./modules/document_intelligence/pages/DocumentIntelligenceListPage"
  ).then((m) => ({
    default: m.DocumentIntelligenceListPage,
  }))
);

const DocumentIntelligenceDetailPage = lazy(() =>
  import(
    "./modules/document_intelligence/pages/DocumentIntelligenceDetailPage"
  ).then((m) => ({
    default: m.DocumentIntelligenceDetailPage,
  }))
);

const CreateDocumentIntelligenceResourcePage = lazy(() =>
  import(
    "./modules/document_intelligence/pages/CreateDocumentIntelligenceResourcePage"
  ).then((m) => ({
    default: m.CreateDocumentIntelligenceResourcePage,
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

const BlockchainTraceabilityListPage = lazy(() =>
  import(
    "./modules/blockchain_traceability/pages/BlockchainTraceabilityListPage"
  ).then((m) => ({
    default: m.BlockchainTraceabilityListPage,
  }))
);

const BlockchainTraceabilityDetailPage = lazy(() =>
  import(
    "./modules/blockchain_traceability/pages/BlockchainTraceabilityDetailPage"
  ).then((m) => ({
    default: m.BlockchainTraceabilityDetailPage,
  }))
);

const CreateBlockchainTraceabilityResourcePage = lazy(() =>
  import(
    "./modules/blockchain_traceability/pages/CreateBlockchainTraceabilityResourcePage"
  ).then((m) => ({
    default: m.CreateBlockchainTraceabilityResourcePage,
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

const BackupDisasterRecoveryListPage = lazy(() =>
  import(
    "./modules/backup_disaster_recovery/pages/BackupDisasterRecoveryListPage"
  ).then((m) => ({
    default: m.BackupDisasterRecoveryListPage,
  }))
);

const BackupDisasterRecoveryDetailPage = lazy(() =>
  import(
    "./modules/backup_disaster_recovery/pages/BackupDisasterRecoveryDetailPage"
  ).then((m) => ({
    default: m.BackupDisasterRecoveryDetailPage,
  }))
);

const CreateBackupDisasterRecoveryResourcePage = lazy(() =>
  import(
    "./modules/backup_disaster_recovery/pages/CreateBackupDisasterRecoveryResourcePage"
  ).then((m) => ({
    default: m.CreateBackupDisasterRecoveryResourcePage,
  }))
);

const PerformanceMonitoringListPage = lazy(() =>
  import(
    "./modules/performance_monitoring/pages/PerformanceMonitoringListPage"
  ).then((m) => ({
    default: m.PerformanceMonitoringListPage,
  }))
);

const PerformanceMonitoringDetailPage = lazy(() =>
  import(
    "./modules/performance_monitoring/pages/PerformanceMonitoringDetailPage"
  ).then((m) => ({
    default: m.PerformanceMonitoringDetailPage,
  }))
);

const CreatePerformanceMonitoringResourcePage = lazy(() =>
  import(
    "./modules/performance_monitoring/pages/CreatePerformanceMonitoringResourcePage"
  ).then((m) => ({
    default: m.CreatePerformanceMonitoringResourcePage,
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

          {/* AI Agent Management routes */}
          <Route
            path="/ai-agents"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AgentListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAgentPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AgentDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <div className="p-8">
                    <p>Edit page coming soon</p>
                  </div>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/executions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ExecutionMonitorPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/approvals"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ApprovalQueuePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* ⚠️ ARCHITECTURAL ENFORCEMENT: Platform Management routes removed
              Platform settings, feature flags, health, and audit logs MUST be
              in a separate platform frontend (saraise-platform/frontend/). */}

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
                  <WorkflowBuilder />
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

          {/* Human Resources */}
          <Route
            path="/human-resources/employees"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <HrEmployeeListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/human-resources/employees/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateHrEmployeePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/human-resources/employees/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <HrEmployeeDetailPage />
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

          {/* Business Intelligence */}
          <Route
            path="/business-intelligence/reports"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BiReportListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/business-intelligence/reports/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBiReportPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/business-intelligence/reports/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BiReportDetailPage />
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

          {/* Fixed Assets */}
          <Route
            path="/fixed-assets/assets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <FixedAssetListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/fixed-assets/assets/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateFixedAssetPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/fixed-assets/assets/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <FixedAssetDetailPage />
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

          {/* Email Marketing */}
          <Route
            path="/email-marketing/campaigns"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <EmailCampaignListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/email-marketing/campaigns/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateEmailCampaignPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/email-marketing/campaigns/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <EmailCampaignDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Master Data Management */}
          <Route
            path="/master-data/entities"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MasterDataEntityListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/master-data/entities/new"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateMasterDataEntityPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/master-data/entities/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <MasterDataEntityDetailPage />
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

          {/* WorkflowAutomation routes */}
          <Route
            path="/workflow-automation"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <WorkflowAutomationListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-automation/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateWorkflowAutomationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-automation/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <WorkflowAutomationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* ApiManagement routes */}
          <Route
            path="/api-management"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ApiManagementListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/api-management/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateApiManagementResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/api-management/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ApiManagementDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* IntegrationPlatform routes */}
          <Route
            path="/integration-platform"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <IntegrationPlatformListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integration-platform/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateIntegrationPlatformResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integration-platform/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <IntegrationPlatformDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* CustomizationFramework routes */}
          <Route
            path="/customization-framework"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CustomizationFrameworkListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/customization-framework/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateCustomizationFrameworkResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/customization-framework/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CustomizationFrameworkDetailPage />
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

          {/* AutomationOrchestration routes */}
          <Route
            path="/automation-orchestration"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AutomationOrchestrationListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/automation-orchestration/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAutomationOrchestrationResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/automation-orchestration/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AutomationOrchestrationDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* ProcessMining routes */}
          <Route
            path="/process-mining"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ProcessMiningListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/process-mining/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateProcessMiningResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/process-mining/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ProcessMiningDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* DocumentIntelligence routes */}
          <Route
            path="/document-intelligence"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DocumentIntelligenceListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/document-intelligence/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateDocumentIntelligenceResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/document-intelligence/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DocumentIntelligenceDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Dms routes */}
          <Route
            path="/dms"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DmsListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dms/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateDmsResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dms/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <DmsDetailPage />
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

          {/* BlockchainTraceability routes */}
          <Route
            path="/blockchain-traceability"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BlockchainTraceabilityListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/blockchain-traceability/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBlockchainTraceabilityResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/blockchain-traceability/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BlockchainTraceabilityDetailPage />
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

          {/* BackupDisasterRecovery routes */}
          <Route
            path="/backup-disaster-recovery"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BackupDisasterRecoveryListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/backup-disaster-recovery/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateBackupDisasterRecoveryResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/backup-disaster-recovery/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BackupDisasterRecoveryDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* PerformanceMonitoring routes */}
          <Route
            path="/performance-monitoring"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PerformanceMonitoringListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/performance-monitoring/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreatePerformanceMonitoringResourcePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/performance-monitoring/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PerformanceMonitoringDetailPage />
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
