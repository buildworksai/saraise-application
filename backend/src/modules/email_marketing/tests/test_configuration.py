"""Tenant isolation, validation, audit, and rollback proofs for module configuration."""

from __future__ import annotations

import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError

from src.core.user_models import UserProfile
from src.modules.email_marketing.models import (
    EmailMarketingConfiguration,
    EmailMarketingConfigurationVersion,
    ImmutableEvidenceError,
)
from src.modules.email_marketing.permissions import EmailMarketingAccessMixin
from src.modules.email_marketing.services import (
    ConfigurationService,
    _validate_tenant_json,
    get_platform_runtime_defaults,
    validate_configuration_document,
)

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_configuration_is_materialized_and_isolated_per_tenant() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    first_a = ConfigurationService.current(tenant_a)
    second_a = ConfigurationService.current(tenant_a)
    current_b = ConfigurationService.current(tenant_b)

    assert first_a.pk == second_a.pk
    assert first_a.tenant_id == tenant_a
    assert current_b.tenant_id == tenant_b
    assert current_b.pk != first_a.pk
    assert EmailMarketingConfiguration.objects.for_tenant(tenant_a).count() == 1
    assert EmailMarketingConfiguration.objects.for_tenant(tenant_b).count() == 1
    assert not EmailMarketingConfiguration.objects.for_tenant(tenant_a).filter(pk=current_b.pk).exists()
    assert first_a.versions.for_tenant(tenant_a).count() == 1
    assert not EmailMarketingConfigurationVersion.objects.for_tenant(tenant_a).filter(configuration=current_b).exists()


def test_configuration_update_preview_history_and_rollback_are_versioned() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    changed = deepcopy(current.document)
    changed["pagination"]["default_page_size"] = 50

    preview = ConfigurationService.preview(tenant, changed)
    assert preview["valid"] is True
    assert preview["changes"] == [{"path": "pagination.default_page_size", "before": 25, "after": 50}]

    updated = ConfigurationService.update(tenant, actor, changed, expected_version=1)
    assert updated.version == 2
    assert updated.document["pagination"]["default_page_size"] == 50
    assert list(ConfigurationService.history(tenant).values_list("version", flat=True)) == [2, 1]

    rolled_back = ConfigurationService.rollback(tenant, actor, target_version=1, expected_version=2)
    assert rolled_back.version == 3
    assert rolled_back.document["pagination"]["default_page_size"] == 25
    audit = rolled_back.versions.get(version=3)
    assert audit.change_type == "rollback"
    assert audit.rollback_source_version == 1
    assert audit.actor_id == actor
    assert audit.correlation_id


def test_invalid_configuration_is_unsavable_and_audit_is_immutable() -> None:
    invalid = get_platform_runtime_defaults()
    invalid["pagination"]["default_page_size"] = 101
    with pytest.raises(ValidationError):
        validate_configuration_document(invalid)
    invalid_role = get_platform_runtime_defaults()
    invalid_role["feature_flags"]["roles"] = [""]
    with pytest.raises(ValidationError):
        validate_configuration_document(invalid_role)

    tenant = uuid.uuid4()
    audit = ConfigurationService.current(tenant).versions.get(version=1)
    audit.change_type = "tampered"
    with pytest.raises(ImmutableEvidenceError):
        audit.save()
    with pytest.raises(ImmutableEvidenceError):
        EmailMarketingConfigurationVersion.objects.for_tenant(tenant).update(change_type="tampered")
    with pytest.raises(ImmutableEvidenceError):
        audit.delete()


@pytest.mark.parametrize(
    ("path", "mutator", "expected_key"),
    [
        (
            "retry delay ordering",
            lambda document: document["resilience"].update(
                {"retry_base_delay_seconds": 10, "retry_max_delay_seconds": 1}
            ),
            "resilience",
        ),
        (
            "protected sent evidence",
            lambda document: document["workflows"].update({"campaign_physical_delete_protected_states": ["cancelled"]}),
            "workflows.campaign_physical_delete_protected_states",
        ),
        (
            "acknowledgement completeness",
            lambda document: document["workflows"]["provider_acknowledgement_mapping"].pop("failed"),
            "workflows.provider_acknowledgement_mapping",
        ),
        (
            "mandatory suppression scope",
            lambda document: document["compliance"].update({"suppression_scopes": ["marketing"]}),
            "compliance.suppression_scopes",
        ),
        (
            "invalid delivery backend",
            lambda document: document["integrations"].update({"allowed_delivery_backends": ["unsafe.Backend"]}),
            "integrations",
        ),
        (
            "invalid status semantic",
            lambda document: document["display"]["status_semantics"].update({"draft": "purple"}),
            "display.status_semantics",
        ),
        (
            "public rate limit",
            lambda document: document["rate_limits"].update({"public_per_minute": 0}),
            "rate_limits.public_per_minute",
        ),
    ],
)
def test_configuration_validation_rejects_unsafe_runtime_policy_edges(
    path: str,
    mutator: object,
    expected_key: str,
) -> None:
    document = get_platform_runtime_defaults()
    mutator(document)

    with pytest.raises(ValidationError) as exc_info:
        validate_configuration_document(document)

    assert expected_key in exc_info.value.detail or f"document.{expected_key}" in exc_info.value.detail, path


def test_tenant_json_validation_enforces_configured_serialization_limits() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    document = deepcopy(current.document)
    document["limits"]["serializer_json_max_depth"] = 2
    document["limits"]["serializer_json_max_keys"] = 2
    document["limits"]["template_design_max_bytes"] = 20
    ConfigurationService.update(tenant, uuid.uuid4(), document, expected_version=current.version)

    _validate_tenant_json(tenant, {"a": 1, "b": 2}, "template_design_max_bytes", "design_json")
    with pytest.raises(ValidationError, match="byte limit"):
        _validate_tenant_json(tenant, {"long": "x" * 30}, "template_design_max_bytes", "design_json")
    with pytest.raises(ValidationError, match="nesting limit"):
        _validate_tenant_json(tenant, {"a": {"b": {"c": 1}}}, "template_design_max_bytes", "design_json")
    with pytest.raises(ValidationError, match="key limit"):
        _validate_tenant_json(tenant, {"a": 1, "b": 2, "c": 3}, "template_design_max_bytes", "design_json")
    with pytest.raises(ValidationError, match="invalid or oversized key"):
        _validate_tenant_json(tenant, {1: "bad"}, "template_design_max_bytes", "design_json")
    with pytest.raises(ValidationError, match="valid JSON"):
        _validate_tenant_json(tenant, {"bad": object()}, "template_design_max_bytes", "design_json")


def test_cross_tenant_configuration_relationship_is_rejected() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    config_b = ConfigurationService.current(tenant_b)
    with pytest.raises(DjangoValidationError):
        EmailMarketingConfigurationVersion.objects.create(
            tenant_id=tenant_a,
            configuration=config_b,
            version=2,
            previous_version=1,
            change_type="spoofed",
            actor_id=uuid.uuid4(),
            correlation_id="cross-tenant",
            previous_document={},
            document=get_platform_runtime_defaults(),
        )


def test_disabled_feature_flag_fails_closed_but_configuration_remains_recoverable() -> None:
    tenant = uuid.uuid4()
    user = User.objects.create_user(username=f"feature-{tenant}", password="test-password")
    with patch.object(UserProfile, "clean"):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"tenant_id": str(tenant), "tenant_role": "tenant_admin"},
        )
    current = ConfigurationService.current(tenant)
    disabled = deepcopy(current.document)
    disabled["feature_flags"]["enabled"] = False
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(
        tenant,
        actor_id,
        disabled,
        expected_version=current.version,
    )

    ordinary = EmailMarketingAccessMixin()
    ordinary.action = "list"
    ordinary.action_permissions = {"list": "email_marketing.campaign:read"}
    ordinary.request = SimpleNamespace(user=User.objects.get(pk=user.pk))
    with pytest.raises(PermissionDenied):
        ordinary.get_permissions()

    configuration = EmailMarketingAccessMixin()
    configuration.action = "current"
    configuration.action_permissions = {"current": "email_marketing.configuration:manage"}
    configuration.request = SimpleNamespace(user=User.objects.get(pk=user.pk))
    assert len(configuration.get_permissions()) == 2
