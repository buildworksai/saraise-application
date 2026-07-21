"""Explicit tenancy-scope registry and Django model classification check."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum
from typing import Any

from django.apps import AppConfig, apps
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from .models import TenantScopedModel


class TenantScope(str, Enum):
    """Supported storage and access scopes for first-party models."""

    TENANT_SCOPED = "TENANT_SCOPED"
    PLATFORM_GLOBAL = "PLATFORM_GLOBAL"
    HYBRID = "HYBRID"


TENANT_SCOPED = TenantScope.TENANT_SCOPED
PLATFORM_GLOBAL = TenantScope.PLATFORM_GLOBAL
HYBRID = TenantScope.HYBRID


def _normalise_label(model_or_label: type[models.Model] | str) -> str:
    if isinstance(model_or_label, str):
        label = model_or_label
    else:
        label = model_or_label._meta.label_lower

    if "." not in label:
        raise ValueError("Model labels must use the 'app_label.ModelName' format.")
    return label.lower()


MODEL_SCOPE_REGISTRY: dict[str, TenantScope] = {}
"""Stable model-label to scope mapping; labels avoid early model imports."""

# Backward-friendly public name for callers that refer to the tenancy registry.
TENANCY_REGISTRY = MODEL_SCOPE_REGISTRY


def register_model_scope(model_or_label: type[models.Model] | str, scope: TenantScope) -> None:
    """Register one model exactly once, rejecting contradictory declarations."""
    label = _normalise_label(model_or_label)
    normalised_scope = TenantScope(scope)
    existing = MODEL_SCOPE_REGISTRY.get(label)
    if existing is not None and existing != normalised_scope:
        raise ImproperlyConfigured(
            f"Model '{label}' is already classified as {existing.value}; "
            f"it cannot also be classified as {normalised_scope.value}."
        )
    MODEL_SCOPE_REGISTRY[label] = normalised_scope


def get_model_scope(model_or_label: type[models.Model] | str) -> TenantScope | None:
    """Return a model's declared scope, including canonical-base adoption."""
    label = _normalise_label(model_or_label)
    declared_scope = MODEL_SCOPE_REGISTRY.get(label)

    if not isinstance(model_or_label, str) and issubclass(model_or_label, TenantScopedModel):
        if declared_scope not in (None, TENANT_SCOPED):
            raise ImproperlyConfigured(
                f"Canonical tenant model '{label}' contradicts its " f"{declared_scope.value} registry classification."
            )
        return TENANT_SCOPED

    return declared_scope


def tenancy_scope(scope: TenantScope) -> Callable[[type[models.Model]], type[models.Model]]:
    """Class decorator for an explicit model-scope declaration."""

    def decorator(model: type[models.Model]) -> type[models.Model]:
        register_model_scope(model, scope)
        return model

    return decorator


# Existing first-party models are classified explicitly while each module
# incrementally adopts TenantScopedModel. Newly introduced models are absent
# from these declarations and therefore fail core.E005.
_TENANT_SCOPED_MODELS = (
    "accounting_finance.Account",
    "accounting_finance.APInvoice",
    "accounting_finance.ARInvoice",
    "accounting_finance.JournalEntry",
    "accounting_finance.JournalLine",
    "accounting_finance.Payment",
    "accounting_finance.PostingPeriod",
    "ai_agent_management.Agent",
    "ai_agent_management.AgentExecution",
    "ai_agent_management.AgentSchedulerTask",
    "ai_agent_management.ApprovalRequest",
    "ai_agent_management.AuditEvent",
    "ai_agent_management.AuditTrail",
    "ai_agent_management.CostRecord",
    "ai_agent_management.CostSummary",
    "ai_agent_management.EgressRequest",
    "ai_agent_management.EgressRule",
    "ai_agent_management.KillSwitch",
    "ai_agent_management.QuotaUsage",
    "ai_agent_management.Secret",
    "ai_agent_management.SecretAccess",
    "ai_agent_management.ShardSaturation",
    "ai_agent_management.SoDPolicy",
    "ai_agent_management.SoDViolation",
    "ai_agent_management.TenantQuota",
    "ai_agent_management.TokenUsage",
    "ai_agent_management.Tool",
    "ai_agent_management.ToolInvocation",
    "ai_provider_configuration.AIModelDeployment",
    "ai_provider_configuration.AIProviderCredential",
    "ai_provider_configuration.AIUsageLog",
    "api_management.ApiManagementResource",
    "asset_management.Asset",
    "asset_management.DepreciationEntry",
    "automation_orchestration.OrchestrationDefinition",
    "automation_orchestration.OrchestrationNode",
    "automation_orchestration.OrchestrationEdge",
    "automation_orchestration.OrchestrationSchedule",
    "automation_orchestration.OrchestrationRun",
    "automation_orchestration.OrchestrationTaskRun",
    "automation_orchestration.RetryAttempt",
    "automation_orchestration.OrchestrationEvent",
    "backup_disaster_recovery.BackupDisasterRecoveryResource",
    "backup_recovery.BackupArchive",
    "backup_recovery.BackupJob",
    "backup_recovery.BackupRetentionPolicy",
    "backup_recovery.BackupSchedule",
    "bank_reconciliation.BankAccount",
    "bank_reconciliation.BankStatement",
    "bank_reconciliation.BankTransaction",
    "billing_subscriptions.Invoice",
    "billing_subscriptions.InvoiceLineItem",
    "billing_subscriptions.Payment",
    "billing_subscriptions.Subscription",
    "billing_subscriptions.UsageRecord",
    "blockchain_traceability.BlockchainTraceabilityResource",
    "budget_management.Budget",
    "budget_management.BudgetLine",
    "business_intelligence.Dashboard",
    "business_intelligence.Report",
    "communication_hub.Channel",
    "communication_hub.Message",
    "compliance_management.CompliancePolicy",
    "compliance_management.ComplianceRequirement",
    "compliance_risk_management.ComplianceRisk",
    "core.Entitlement",
    "core.EntitlementCheck",
    "core.GuardrailViolation",
    "core.InstallationStep",
    "core.ModuleInstallation",
    "core.ModuleUpgrade",
    "core.Notification",
    "core.NotificationPreference",
    "core.PolicyBundleValidation",
    "core.PushNotificationToken",
    "core.Quota",
    "core.TenantModuleInstallation",
    "core.TenantSubscription",
    "core.UpgradeStep",
    "crm.Account",
    "crm.Activity",
    "crm.Contact",
    "crm.Lead",
    "crm.Opportunity",
    "customization_framework.CustomizationFrameworkResource",
    "data_migration.ExternalConnection",
    "data_migration.MigrationJob",
    "data_migration.MigrationLog",
    "data_migration.MigrationMapping",
    "data_migration.MigrationRollback",
    "data_migration.MigrationValidation",
    "dms.Document",
    "dms.DocumentPermission",
    "dms.DocumentShare",
    "dms.DocumentVersion",
    "dms.Folder",
    "document_intelligence.DocumentIntelligenceResource",
    "email_marketing.EmailCampaign",
    "email_marketing.EmailTemplate",
    "fixed_assets.FixedAsset",
    "human_resources.Attendance",
    "human_resources.Department",
    "human_resources.Employee",
    "human_resources.LeaveRequest",
    "integration_platform.DataMapping",
    "integration_platform.Integration",
    "integration_platform.IntegrationCredential",
    "integration_platform.Webhook",
    "integration_platform.WebhookDelivery",
    "inventory_management.Item",
    "inventory_management.StockBalance",
    "inventory_management.StockEntry",
    "inventory_management.StockEntryLine",
    "inventory_management.Warehouse",
    "localization.CurrencyConfig",
    "localization.LocaleConfig",
    "localization.RegionalSettings",
    "localization.Translation",
    "master_data_management.MasterDataEntity",
    "metadata_modeling.DynamicResource",
    "metadata_modeling.EntityDefinition",
    "metadata_modeling.FieldDefinition",
    "multi_company.Company",
    "notifications.Notification",
    "notifications.NotificationPreference",
    "performance_monitoring.PerformanceMonitoringResource",
    "process_mining.ProcessMiningResource",
    "project_management.Project",
    "project_management.ProjectMember",
    "project_management.ProjectMilestone",
    "project_management.Task",
    "project_management.TimeEntry",
    "purchase_management.PurchaseOrder",
    "purchase_management.PurchaseOrderLine",
    "purchase_management.PurchaseReceipt",
    "purchase_management.PurchaseReceiptLine",
    "purchase_management.PurchaseRequisition",
    "purchase_management.Supplier",
    "regional.RegionalResource",
    "sales_management.Customer",
    "sales_management.DeliveryNote",
    "sales_management.DeliveryNoteLine",
    "sales_management.Quotation",
    "sales_management.SalesOrder",
    "sales_management.SalesOrderLine",
    "security_access_control.FieldSecurity",
    "security_access_control.PermissionSet",
    "security_access_control.Role",
    "security_access_control.RolePermission",
    "security_access_control.RowSecurityRule",
    "security_access_control.SecurityProfile",
    "security_access_control.UserPermissionSet",
    "security_access_control.UserRole",
    "workflow_automation.Workflow",
    "workflow_automation.WorkflowInstance",
    "workflow_automation.WorkflowStep",
    "workflow_automation.WorkflowTask",
)

_PLATFORM_GLOBAL_MODELS = (
    "ai_provider_configuration.AIModel",
    "ai_provider_configuration.AIProvider",
    "billing_subscriptions.SubscriptionPlan",
    "core.GuardrailRule",
    "core.License",
    "core.LicenseValidationLog",
    "core.ModuleRegistryEntry",
    "core.Organization",
    "core.PlanEntitlement",
    "core.SubscriptionPlan",
    "integration_platform.Connector",
    "localization.Language",
    "platform_management.PlatformMetrics",
    "platform_management.SystemHealth",
    "security_access_control.Permission",
    "tenant_management.Tenant",
    "tenant_management.TenantHealthScore",
    "tenant_management.TenantModule",
    "tenant_management.TenantResourceUsage",
    "tenant_management.TenantSettings",
)

_HYBRID_MODELS = (
    "core.ComplianceCheck",
    "core.ResidencyRule",
    "core.UserProfile",
    "platform_management.FeatureFlag",
    "platform_management.PlatformAuditEvent",
    "platform_management.PlatformSetting",
    "security_access_control.SecurityAuditLog",
)

for _model_label in _TENANT_SCOPED_MODELS:
    register_model_scope(_model_label, TENANT_SCOPED)
for _model_label in _PLATFORM_GLOBAL_MODELS:
    register_model_scope(_model_label, PLATFORM_GLOBAL)
for _model_label in _HYBRID_MODELS:
    register_model_scope(_model_label, HYBRID)


def _is_first_party_app(app_config: AppConfig) -> bool:
    return bool(app_config.name == "src.core" or app_config.name.startswith("src.modules."))


@checks.register(checks.Tags.models)
def check_model_tenancy_scopes(
    app_configs: Iterable[AppConfig] | None = None, **kwargs: Any
) -> list[checks.CheckMessage]:
    """Fail when a concrete first-party model has no scope classification."""
    del kwargs
    if app_configs is None:
        selected_apps = [app_config for app_config in apps.get_app_configs() if _is_first_party_app(app_config)]
    else:
        # Explicit subsets are used by Django and isolate_apps tests. They are
        # already caller-selected, so do not silently discard non-production labels.
        selected_apps = list(app_configs)

    errors: list[checks.CheckMessage] = []
    for app_config in selected_apps:
        for model in app_config.get_models(include_auto_created=False):
            options = model._meta
            if options.abstract or options.proxy or options.swapped:
                continue

            try:
                scope = get_model_scope(model)
            except ImproperlyConfigured as exc:
                scope = None
                detail = str(exc)
            else:
                detail = f"Model '{options.label}' has no tenancy scope classification."

            if scope is None:
                errors.append(
                    checks.Error(
                        detail,
                        hint=(
                            "Inherit TenantScopedModel or declare this model as "
                            "TENANT_SCOPED, PLATFORM_GLOBAL, or HYBRID in "
                            "src.core.tenancy.registry."
                        ),
                        obj=model,
                        id="core.E005",
                    )
                )
    return errors


# Concise aliases for extension modules and tests.
register = register_model_scope
get_scope = get_model_scope
check_tenancy_registry = check_model_tenancy_scopes


__all__ = [
    "HYBRID",
    "MODEL_SCOPE_REGISTRY",
    "PLATFORM_GLOBAL",
    "TENANCY_REGISTRY",
    "TENANT_SCOPED",
    "TenantScope",
    "check_model_tenancy_scopes",
    "check_tenancy_registry",
    "get_model_scope",
    "get_scope",
    "register",
    "register_model_scope",
    "tenancy_scope",
]
