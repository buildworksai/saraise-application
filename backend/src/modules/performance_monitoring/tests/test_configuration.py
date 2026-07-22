import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.performance_monitoring.api import ConfigurationViewSet
from src.modules.performance_monitoring.models import (
    PerformanceMonitoringConfiguration,
    PerformanceMonitoringConfigurationAudit,
    PerformanceMonitoringConfigurationVersion,
)
from src.modules.performance_monitoring.services import ConfigurationService, ConfigurationValidationError


@pytest.fixture
def configuration_client(db, monkeypatch):
    tenant = Organization.objects.create(name="Monitoring configuration tenant")
    user = get_user_model().objects.create_user(username=f"config-{uuid.uuid4()}", password="test-password")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant.id
    profile.tenant_role = "tenant_admin"
    profile.save(update_fields=["tenant_id", "tenant_role"])
    monkeypatch.setattr(ConfigurationViewSet, "permission_classes", (IsAuthenticated,))
    client = APIClient()
    client.force_authenticate(user=get_user_model().objects.get(pk=user.pk))
    return client, tenant.id, user.id


@pytest.mark.django_db
def test_configuration_is_versioned_audited_and_rollback_creates_a_new_version():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    service.apply(
        tenant,
        "production",
        service.default_document(),
        actor_id=actor,
        correlation_id="req-create",
        change_reason="Initial configuration",
        expected_version=0,
        merge=False,
    )
    updated = service.apply(
        tenant,
        "production",
        {"defaults": {"dashboard": {"service_list_limit": 12}}},
        actor_id=actor,
        correlation_id="req-update",
        change_reason="Show more monitored services",
        expected_version=1,
    )
    assert updated.version == 2
    assert updated.document["defaults"]["dashboard"]["service_list_limit"] == 12
    rolled_back = service.rollback(
        tenant,
        "production",
        1,
        actor_id=actor,
        correlation_id="req-rollback",
        change_reason="Restore known-good limits",
        expected_version=2,
    )
    assert rolled_back.version == 3
    assert rolled_back.document["defaults"]["dashboard"]["service_list_limit"] == 6
    assert list(
        PerformanceMonitoringConfigurationVersion.objects.for_tenant(tenant)
        .order_by("version")
        .values_list("version", flat=True)
    ) == [1, 2, 3]
    assert list(
        PerformanceMonitoringConfigurationAudit.objects.for_tenant(tenant)
        .order_by("to_version")
        .values_list("action", flat=True)
    ) == ["create", "update", "rollback"]


@pytest.mark.django_db
def test_configuration_is_tenant_isolated_and_correlation_is_idempotent():
    first, second, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    first_config = service.apply(
        first,
        "default",
        service.default_document(),
        actor_id=actor,
        correlation_id="req-one",
        change_reason="Initialize tenant one",
        merge=False,
    )
    repeated = service.apply(
        first,
        "default",
        service.default_document(),
        actor_id=actor,
        correlation_id="req-one",
        change_reason="Initialize tenant one",
        merge=False,
    )
    second_document = service.default_document()
    second_document["defaults"]["service"]["namespace"] = "tenant-two"
    service.apply(
        second,
        "default",
        second_document,
        actor_id=actor,
        correlation_id="req-two",
        change_reason="Initialize tenant two",
        merge=False,
    )
    assert repeated.id == first_config.id
    assert PerformanceMonitoringConfiguration.objects.for_tenant(first).count() == 1
    assert service.effective_document(first)["defaults"]["service"]["namespace"] == "saraise"
    assert service.effective_document(second)["defaults"]["service"]["namespace"] == "tenant-two"
    assert not PerformanceMonitoringConfigurationAudit.objects.for_tenant(first).filter(tenant_id=second).exists()


@pytest.mark.django_db
def test_configuration_validation_enforces_platform_bounds_and_dependencies():
    service = ConfigurationService()
    unsafe = service.default_document()
    unsafe["limits"]["daily_event_quota_max"] = 100_000_001
    with pytest.raises(ConfigurationValidationError):
        service.validate_document(unsafe)

    invalid_dependency = service.default_document()
    invalid_dependency["defaults"]["alert_rule"]["cooldown_minutes"] = 1
    with pytest.raises(ConfigurationValidationError):
        service.validate_document(invalid_dependency)

    unsupported = service.default_document()
    unsupported["allowlists"]["notification_channels"].append("shell")
    with pytest.raises(ConfigurationValidationError):
        service.validate_document(unsupported)


@pytest.mark.django_db
def test_configuration_history_is_immutable_for_instances_and_querysets():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    service.apply(
        tenant,
        "default",
        service.default_document(),
        actor_id=actor,
        correlation_id="req-immutable",
        change_reason="Create immutable history",
        merge=False,
    )
    version = PerformanceMonitoringConfigurationVersion.objects.for_tenant(tenant).get()
    version.change_reason = "tampered"
    with pytest.raises(ValidationError):
        version.save()
    with pytest.raises(ValidationError):
        PerformanceMonitoringConfigurationVersion.objects.for_tenant(tenant).update(change_reason="tampered")
    with pytest.raises(ValidationError):
        PerformanceMonitoringConfigurationAudit.objects.for_tenant(tenant).delete()
    with pytest.raises(ValidationError):
        PerformanceMonitoringConfigurationAudit._base_manager.filter(tenant_id=tenant).update(change_reason="tampered")
    with pytest.raises(ValidationError):
        PerformanceMonitoringConfigurationVersion._base_manager.filter(tenant_id=tenant).delete()


@pytest.mark.django_db
def test_configuration_v2_api_exposes_preview_history_audit_export_and_import(configuration_client):
    client, tenant, _ = configuration_client
    current = client.get("/api/v2/performance-monitoring/configuration/current/")
    assert current.status_code == 200, current.data
    body = current.json()["data"]
    assert body["tenant_id"] == str(tenant)
    assert body["version"] == 1

    preview = client.post(
        "/api/v2/performance-monitoring/configuration/preview/",
        {"document": {"rollout": {"percentage": 25}}},
        format="json",
    )
    assert preview.status_code == 200, preview.data
    assert preview.json()["data"]["diff"] == [{"path": "rollout.percentage", "before": 100, "after": 25}]

    changed = client.patch(
        "/api/v2/performance-monitoring/configuration/current/",
        {"document": {"rollout": {"percentage": 25}}, "expected_version": 1, "change_reason": "Canary rollout"},
        format="json",
        HTTP_X_CORRELATION_ID="req-api-change",
    )
    assert changed.status_code == 200, changed.data
    assert changed.json()["data"]["version"] == 2
    assert client.get("/api/v2/performance-monitoring/configuration/history/").json()["data"][0]["version"] == 2
    assert (
        client.get("/api/v2/performance-monitoring/configuration/audit/").json()["data"][0]["correlation_id"]
        == "req-api-change"
    )
    exported = client.get("/api/v2/performance-monitoring/configuration/export/")
    assert exported.status_code == 200
    assert exported.json()["data"]["document"]["rollout"]["percentage"] == 25

    imported_document = exported.json()["data"]["document"]
    imported_document["rollout"]["percentage"] = 50
    imported = client.post(
        "/api/v2/performance-monitoring/configuration/import/",
        {
            "document": imported_document,
            "expected_version": 2,
            "change_reason": "Promote reviewed configuration",
        },
        format="json",
        HTTP_X_CORRELATION_ID="req-api-import",
    )
    assert imported.status_code == 201, imported.data
    assert imported.json()["data"]["document"]["rollout"]["percentage"] == 50
