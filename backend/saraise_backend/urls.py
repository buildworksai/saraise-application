"""
URL configuration for SARAISE backend.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from src.core.metrics import metrics

urlpatterns = [
    # Health check endpoint
    path("health/", lambda request: __import__("django.http").http.JsonResponse({"status": "ok"})),
    path("metrics/", metrics),
    # OpenAPI Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # ===== Authentication Routes =====
    path("api/v1/auth/", include("src.core.auth_urls")),
    path("api/v1/licensing/", include("src.core.licensing.urls")),
    # ===== Core Services =====
    path("api/v1/notifications/", include("src.core.notifications.urls")),
    # ===== Module Routes =====
    # AI Agent Management
    path("api/v1/ai-agents/", include("src.modules.ai_agent_management.urls")),
    # Platform Management (mode-aware: Full CRUD in self-hosted, read-only in SaaS)
    path("api/v1/platform/", include("src.modules.platform_management.urls")),
    # Tenant Management
    path("api/v1/tenant-management/", include("src.modules.tenant_management.urls")),
    # Security & Access Control
    path("api/v1/security-access-control/", include("src.modules.security_access_control.urls")),
    path("api/v1/workflow-automation/", include("src.modules.workflow_automation.urls")),
    path("api/v1/api-management/", include("src.modules.api_management.urls")),
    path("api/v1/integration-platform/", include("src.modules.integration_platform.urls")),
    path("api/v1/customization-framework/", include("src.modules.customization_framework.urls")),
    path("api/v1/ai-provider-configuration/", include("src.modules.ai_provider_configuration.urls")),
    path("api/v1/automation-orchestration/", include("src.modules.automation_orchestration.urls")),
    path("api/v1/process-mining/", include("src.modules.process_mining.urls")),
    path("api/v1/document-intelligence/", include("src.modules.document_intelligence.urls")),
    path("api/v1/dms/", include("src.modules.dms.urls")),
    path("api/v1/data-migration/", include("src.modules.data_migration.urls")),
    path("api/v1/metadata-modeling/", include("src.modules.metadata_modeling.urls")),
    path("api/v1/blockchain-traceability/", include("src.modules.blockchain_traceability.urls")),
    path("api/v1/billing-subscriptions/", include("src.modules.billing_subscriptions.urls")),
    path("api/v1/backup-disaster-recovery/", include("src.modules.backup_disaster_recovery.urls")),
    path("api/v1/backup-recovery/", include("src.modules.backup_recovery.urls")),
    path("api/v1/performance-monitoring/", include("src.modules.performance_monitoring.urls")),
    path("api/v1/localization/", include("src.modules.localization.urls")),
    path("api/v1/regional/", include("src.modules.regional.urls")),
    # CRM Module
    path("api/v1/crm/", include("src.modules.crm.urls")),
    # Add other module routes here as they're implemented
]
