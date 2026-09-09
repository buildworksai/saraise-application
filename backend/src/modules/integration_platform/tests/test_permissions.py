"""Executable authorization metadata and signed-transport boundary tests."""

from __future__ import annotations

import dataclasses
import time
from types import SimpleNamespace

import pytest
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from src.core.access import RequiresAccess

from ..api import CanonicalSessionAuthentication, GovernedAccessMixin
from ..permissions import (
    ACTION_ACCESS_MAPS,
    CONFIGURATION_ACTIONS,
    CONFIGURATION_MANAGE,
    CONFIGURATION_READ,
    CONNECTOR_ACTIONS,
    CONNECTOR_READ,
    CREDENTIAL_ACTIONS,
    CREDENTIAL_CREATE,
    CREDENTIAL_READ,
    CREDENTIAL_REVOKE,
    CREDENTIAL_ROTATE,
    DELIVERY_ACTIONS,
    DELIVERY_READ,
    DELIVERY_REDRIVE,
    HEALTH_ACTIONS,
    HEALTH_READ,
    INTEGRATION_ACTIONS,
    INTEGRATION_ACTIVATE,
    INTEGRATION_CREATE,
    INTEGRATION_CREDENTIAL_ACTIONS,
    INTEGRATION_DEACTIVATE,
    INTEGRATION_DELETE,
    INTEGRATION_READ,
    INTEGRATION_SYNC,
    INTEGRATION_TEST,
    INTEGRATION_UPDATE,
    MAPPING_ACTIONS,
    MAPPING_CREATE,
    MAPPING_DELETE,
    MAPPING_PREVIEW,
    MAPPING_READ,
    MAPPING_UPDATE,
    MODULE_ENTITLEMENT,
    PERMISSIONS,
    SOD_ACTIONS,
    WEBHOOK_ACTIONS,
    WEBHOOK_ACTIVATE,
    WEBHOOK_CREATE,
    WEBHOOK_DEACTIVATE,
    WEBHOOK_DELETE,
    WEBHOOK_READ,
    WEBHOOK_ROTATE_SECRET,
    WEBHOOK_UPDATE,
    AccessRequirement,
    InboundWebhookSignaturePermission,
    access,
)
from .factories import WebhookFactory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def test_permission_catalog_is_exact_unique_and_module_scoped() -> None:
    assert len(PERMISSIONS) == 28
    assert len(set(PERMISSIONS)) == len(PERMISSIONS)
    assert all(value.startswith("integration_platform.") for value in PERMISSIONS)
    assert SOD_ACTIONS == (
        ("integration_platform.integration:create", "integration_platform.integration:delete"),
        ("integration_platform.credential:create", "integration_platform.credential:revoke"),
    )


@pytest.mark.parametrize(
    ("action_map", "actions"),
    [
        (CONNECTOR_ACTIONS, {"list", "retrieve", "schema", "connector_schema", "health"}),
        (
            INTEGRATION_ACTIONS,
            {
                "list",
                "retrieve",
                "create",
                "partial_update",
                "destroy",
                "activate",
                "deactivate",
                "test_connection",
                "sync",
                "job",
            },
        ),
        (CREDENTIAL_ACTIONS, {"retrieve", "rotate", "revoke"}),
        (INTEGRATION_CREDENTIAL_ACTIONS, {"list", "create"}),
        (
            WEBHOOK_ACTIONS,
            {
                "list",
                "retrieve",
                "create",
                "partial_update",
                "destroy",
                "activate",
                "deactivate",
                "rotate_secret",
            },
        ),
        (DELIVERY_ACTIONS, {"list", "retrieve", "redrive"}),
        (
            MAPPING_ACTIONS,
            {"list", "retrieve", "create", "partial_update", "destroy", "validate_mappings", "preview"},
        ),
        (HEALTH_ACTIONS, {"get"}),
    ],
)
def test_every_published_action_has_complete_access_metadata(action_map, actions) -> None:
    assert set(action_map) == actions
    for requirement in action_map.values():
        assert requirement.permission in PERMISSIONS
        assert requirement.entitlement == "integration_platform"
        assert requirement.quota_resource.startswith("integration_platform.")
        assert requirement.quota_cost >= 1


def test_action_maps_are_registered_once_and_unknown_actions_deny() -> None:
    assert set(ACTION_ACCESS_MAPS) == {
        "connectors",
        "integrations",
        "integration_credentials",
        "nested_credentials",
        "webhooks",
        "deliveries",
        "mappings",
        "health",
    }
    request = APIRequestFactory().get("/")
    decision = RequiresAccess().has_permission(request, SimpleNamespace(required_permission=None))
    assert decision is False
    assert request.access_decision.reason_code.value == "DENY_DEFAULT"


def test_governed_api_uses_real_csrf_enforcing_session_authentication() -> None:
    assert GovernedAccessMixin.authentication_classes == (CanonicalSessionAuthentication,)
    assert issubclass(CanonicalSessionAuthentication, SessionAuthentication)
    assert RequiresAccess in GovernedAccessMixin.permission_classes


def test_signature_permission_fails_before_lookup_for_bad_transport_shape() -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="short",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE="optional-signature",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": "not-a-uuid"}),
        )


def test_signature_permission_accepts_only_active_inbound_public_identifier(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    allowed = InboundWebhookSignaturePermission().has_permission(
        request,
        SimpleNamespace(kwargs={"public_id": webhook.public_id}),
    )
    assert allowed is True
    assert request.verified_webhook_public_id == webhook.public_id

    webhook.status = "inactive"
    webhook.transition_history = [
        {
            "from_state": "active",
            "to_state": "inactive",
            "transition_key": "permission-test",
        }
    ]
    webhook.save()
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_permissions_tuple_is_pinned_exact_order() -> None:
    assert PERMISSIONS == (
        CONNECTOR_READ,
        INTEGRATION_CREATE,
        INTEGRATION_READ,
        INTEGRATION_UPDATE,
        INTEGRATION_DELETE,
        INTEGRATION_TEST,
        INTEGRATION_SYNC,
        INTEGRATION_ACTIVATE,
        INTEGRATION_DEACTIVATE,
        CREDENTIAL_CREATE,
        CREDENTIAL_READ,
        CREDENTIAL_ROTATE,
        CREDENTIAL_REVOKE,
        WEBHOOK_CREATE,
        WEBHOOK_READ,
        WEBHOOK_UPDATE,
        WEBHOOK_DELETE,
        WEBHOOK_ACTIVATE,
        WEBHOOK_DEACTIVATE,
        WEBHOOK_ROTATE_SECRET,
        DELIVERY_READ,
        DELIVERY_REDRIVE,
        MAPPING_CREATE,
        MAPPING_READ,
        MAPPING_UPDATE,
        MAPPING_DELETE,
        MAPPING_PREVIEW,
        HEALTH_READ,
    )


def test_permission_literal_values_are_pinned() -> None:
    assert CONNECTOR_READ == "integration_platform.connector:read"
    assert INTEGRATION_CREATE == "integration_platform.integration:create"
    assert INTEGRATION_READ == "integration_platform.integration:read"
    assert INTEGRATION_UPDATE == "integration_platform.integration:update"
    assert INTEGRATION_DELETE == "integration_platform.integration:delete"
    assert INTEGRATION_TEST == "integration_platform.integration:test"
    assert INTEGRATION_SYNC == "integration_platform.integration:sync"
    assert INTEGRATION_ACTIVATE == "integration_platform.integration:activate"
    assert INTEGRATION_DEACTIVATE == "integration_platform.integration:deactivate"
    assert CREDENTIAL_CREATE == "integration_platform.credential:create"
    assert CREDENTIAL_READ == "integration_platform.credential:read"
    assert CREDENTIAL_ROTATE == "integration_platform.credential:rotate"
    assert CREDENTIAL_REVOKE == "integration_platform.credential:revoke"
    assert WEBHOOK_CREATE == "integration_platform.webhook:create"
    assert WEBHOOK_READ == "integration_platform.webhook:read"
    assert WEBHOOK_UPDATE == "integration_platform.webhook:update"
    assert WEBHOOK_DELETE == "integration_platform.webhook:delete"
    assert WEBHOOK_ACTIVATE == "integration_platform.webhook:activate"
    assert WEBHOOK_DEACTIVATE == "integration_platform.webhook:deactivate"
    assert WEBHOOK_ROTATE_SECRET == "integration_platform.webhook:rotate_secret"
    assert DELIVERY_READ == "integration_platform.delivery:read"
    assert DELIVERY_REDRIVE == "integration_platform.delivery:redrive"
    assert MAPPING_CREATE == "integration_platform.mapping:create"
    assert MAPPING_READ == "integration_platform.mapping:read"
    assert MAPPING_UPDATE == "integration_platform.mapping:update"
    assert MAPPING_DELETE == "integration_platform.mapping:delete"
    assert MAPPING_PREVIEW == "integration_platform.mapping:preview"
    assert HEALTH_READ == "integration_platform.health:read"
    assert CONFIGURATION_READ == INTEGRATION_READ
    assert CONFIGURATION_MANAGE == INTEGRATION_UPDATE
    assert MODULE_ENTITLEMENT == "integration_platform"


def test_access_rejects_non_positive_cost() -> None:
    with pytest.raises(ValueError, match="quota cost must be positive"):
        access(INTEGRATION_READ, "integration_platform.integration.read", cost=0)
    with pytest.raises(ValueError, match="quota cost must be positive"):
        access(INTEGRATION_READ, "integration_platform.integration.read", cost=-1)


def test_access_accepts_minimum_positive_cost() -> None:
    requirement = access(INTEGRATION_READ, "integration_platform.integration.read", cost=1)
    assert requirement == AccessRequirement(
        permission=INTEGRATION_READ,
        entitlement=MODULE_ENTITLEMENT,
        quota_resource="integration_platform.integration.read",
        quota_cost=1,
    )


def test_access_default_cost_is_one() -> None:
    requirement = access(HEALTH_READ, "integration_platform.health.read")
    assert requirement.quota_cost == 1


def test_connector_actions_are_pinned_exact() -> None:
    assert CONNECTOR_ACTIONS["list"] == AccessRequirement(
        CONNECTOR_READ, MODULE_ENTITLEMENT, "integration_platform.connector.read", 1
    )
    assert CONNECTOR_ACTIONS["retrieve"] == AccessRequirement(
        CONNECTOR_READ, MODULE_ENTITLEMENT, "integration_platform.connector.read", 1
    )
    assert CONNECTOR_ACTIONS["schema"] == AccessRequirement(
        CONNECTOR_READ, MODULE_ENTITLEMENT, "integration_platform.connector.read", 1
    )
    assert CONNECTOR_ACTIONS["connector_schema"] == AccessRequirement(
        CONNECTOR_READ, MODULE_ENTITLEMENT, "integration_platform.connector.read", 1
    )
    assert CONNECTOR_ACTIONS["health"] == AccessRequirement(
        CONNECTOR_READ, MODULE_ENTITLEMENT, "integration_platform.connector.health", 1
    )


def test_integration_actions_are_pinned_exact() -> None:
    assert INTEGRATION_ACTIONS["list"] == AccessRequirement(
        INTEGRATION_READ, MODULE_ENTITLEMENT, "integration_platform.integration.read", 1
    )
    assert INTEGRATION_ACTIONS["retrieve"] == AccessRequirement(
        INTEGRATION_READ, MODULE_ENTITLEMENT, "integration_platform.integration.read", 1
    )
    assert INTEGRATION_ACTIONS["create"] == AccessRequirement(
        INTEGRATION_CREATE, MODULE_ENTITLEMENT, "integration_platform.integration.write", 2
    )
    assert INTEGRATION_ACTIONS["partial_update"] == AccessRequirement(
        INTEGRATION_UPDATE, MODULE_ENTITLEMENT, "integration_platform.integration.write", 2
    )
    assert INTEGRATION_ACTIONS["destroy"] == AccessRequirement(
        INTEGRATION_DELETE, MODULE_ENTITLEMENT, "integration_platform.integration.write", 2
    )
    assert INTEGRATION_ACTIONS["activate"] == AccessRequirement(
        INTEGRATION_ACTIVATE, MODULE_ENTITLEMENT, "integration_platform.integration.transition", 2
    )
    assert INTEGRATION_ACTIONS["deactivate"] == AccessRequirement(
        INTEGRATION_DEACTIVATE, MODULE_ENTITLEMENT, "integration_platform.integration.transition", 2
    )
    assert INTEGRATION_ACTIONS["test_connection"] == AccessRequirement(
        INTEGRATION_TEST, MODULE_ENTITLEMENT, "integration_platform.integration.test", 5
    )
    assert INTEGRATION_ACTIONS["sync"] == AccessRequirement(
        INTEGRATION_SYNC, MODULE_ENTITLEMENT, "integration_platform.integration.sync", 10
    )
    assert INTEGRATION_ACTIONS["job"] == AccessRequirement(
        INTEGRATION_READ, MODULE_ENTITLEMENT, "integration_platform.integration.job.read", 1
    )


def test_credential_actions_are_pinned_exact() -> None:
    assert CREDENTIAL_ACTIONS["retrieve"] == AccessRequirement(
        CREDENTIAL_READ, MODULE_ENTITLEMENT, "integration_platform.credential.read", 1
    )
    assert CREDENTIAL_ACTIONS["rotate"] == AccessRequirement(
        CREDENTIAL_ROTATE, MODULE_ENTITLEMENT, "integration_platform.credential.write", 3
    )
    assert CREDENTIAL_ACTIONS["revoke"] == AccessRequirement(
        CREDENTIAL_REVOKE, MODULE_ENTITLEMENT, "integration_platform.credential.write", 2
    )


def test_integration_credential_actions_are_pinned_exact() -> None:
    assert INTEGRATION_CREDENTIAL_ACTIONS["list"] == AccessRequirement(
        CREDENTIAL_READ, MODULE_ENTITLEMENT, "integration_platform.credential.read", 1
    )
    assert INTEGRATION_CREDENTIAL_ACTIONS["create"] == AccessRequirement(
        CREDENTIAL_CREATE, MODULE_ENTITLEMENT, "integration_platform.credential.write", 2
    )


def test_webhook_actions_are_pinned_exact() -> None:
    assert WEBHOOK_ACTIONS["list"] == AccessRequirement(
        WEBHOOK_READ, MODULE_ENTITLEMENT, "integration_platform.webhook.read", 1
    )
    assert WEBHOOK_ACTIONS["retrieve"] == AccessRequirement(
        WEBHOOK_READ, MODULE_ENTITLEMENT, "integration_platform.webhook.read", 1
    )
    assert WEBHOOK_ACTIONS["create"] == AccessRequirement(
        WEBHOOK_CREATE, MODULE_ENTITLEMENT, "integration_platform.webhook.write", 2
    )
    assert WEBHOOK_ACTIONS["partial_update"] == AccessRequirement(
        WEBHOOK_UPDATE, MODULE_ENTITLEMENT, "integration_platform.webhook.write", 2
    )
    assert WEBHOOK_ACTIONS["destroy"] == AccessRequirement(
        WEBHOOK_DELETE, MODULE_ENTITLEMENT, "integration_platform.webhook.write", 2
    )
    assert WEBHOOK_ACTIONS["activate"] == AccessRequirement(
        WEBHOOK_ACTIVATE, MODULE_ENTITLEMENT, "integration_platform.webhook.transition", 2
    )
    assert WEBHOOK_ACTIONS["deactivate"] == AccessRequirement(
        WEBHOOK_DEACTIVATE, MODULE_ENTITLEMENT, "integration_platform.webhook.transition", 2
    )
    assert WEBHOOK_ACTIONS["rotate_secret"] == AccessRequirement(
        WEBHOOK_ROTATE_SECRET, MODULE_ENTITLEMENT, "integration_platform.webhook.secret", 3
    )


def test_delivery_actions_are_pinned_exact() -> None:
    assert DELIVERY_ACTIONS["list"] == AccessRequirement(
        DELIVERY_READ, MODULE_ENTITLEMENT, "integration_platform.delivery.read", 1
    )
    assert DELIVERY_ACTIONS["retrieve"] == AccessRequirement(
        DELIVERY_READ, MODULE_ENTITLEMENT, "integration_platform.delivery.read", 1
    )
    assert DELIVERY_ACTIONS["redrive"] == AccessRequirement(
        DELIVERY_REDRIVE, MODULE_ENTITLEMENT, "integration_platform.delivery.redrive", 5
    )


def test_mapping_actions_are_pinned_exact() -> None:
    assert MAPPING_ACTIONS["list"] == AccessRequirement(
        MAPPING_READ, MODULE_ENTITLEMENT, "integration_platform.mapping.read", 1
    )
    assert MAPPING_ACTIONS["retrieve"] == AccessRequirement(
        MAPPING_READ, MODULE_ENTITLEMENT, "integration_platform.mapping.read", 1
    )
    assert MAPPING_ACTIONS["create"] == AccessRequirement(
        MAPPING_CREATE, MODULE_ENTITLEMENT, "integration_platform.mapping.write", 2
    )
    assert MAPPING_ACTIONS["partial_update"] == AccessRequirement(
        MAPPING_UPDATE, MODULE_ENTITLEMENT, "integration_platform.mapping.write", 2
    )
    assert MAPPING_ACTIONS["destroy"] == AccessRequirement(
        MAPPING_DELETE, MODULE_ENTITLEMENT, "integration_platform.mapping.write", 2
    )
    assert MAPPING_ACTIONS["validate_mappings"] == AccessRequirement(
        MAPPING_PREVIEW, MODULE_ENTITLEMENT, "integration_platform.mapping.preview", 2
    )
    assert MAPPING_ACTIONS["preview"] == AccessRequirement(
        MAPPING_PREVIEW, MODULE_ENTITLEMENT, "integration_platform.mapping.preview", 3
    )


def test_health_actions_are_pinned_exact() -> None:
    assert HEALTH_ACTIONS["get"] == AccessRequirement(
        HEALTH_READ, MODULE_ENTITLEMENT, "integration_platform.health.read", 1
    )


def test_configuration_actions_are_pinned_exact() -> None:
    assert set(CONFIGURATION_ACTIONS) == {
        "list",
        "export",
        "versions",
        "audits",
        "manage_capability",
        "create",
        "preview",
        "rollback",
        "import_document",
    }
    read_actions = {"list", "export", "versions", "audits"}
    write_actions = {"manage_capability", "create", "preview", "rollback", "import_document"}
    for action in read_actions:
        assert CONFIGURATION_ACTIONS[action] == AccessRequirement(
            CONFIGURATION_READ, MODULE_ENTITLEMENT, "integration_platform.configuration.read", 1
        )
    for action in write_actions:
        assert CONFIGURATION_ACTIONS[action] == AccessRequirement(
            CONFIGURATION_MANAGE, MODULE_ENTITLEMENT, "integration_platform.configuration.write", 1
        )


def test_configuration_actions_are_intentionally_absent_from_action_access_maps() -> None:
    # Configuration is exposed through a dedicated view (see api.py) rather than
    # the generic ACTION_ACCESS_MAPS registry used by GovernedAccessMixin.
    assert "configuration" not in ACTION_ACCESS_MAPS
    assert CONFIGURATION_ACTIONS not in ACTION_ACCESS_MAPS.values()


def test_action_access_maps_registers_every_action_map_object() -> None:
    assert ACTION_ACCESS_MAPS["connectors"] is CONNECTOR_ACTIONS
    assert ACTION_ACCESS_MAPS["integrations"] is INTEGRATION_ACTIONS
    assert ACTION_ACCESS_MAPS["integration_credentials"] is CREDENTIAL_ACTIONS
    assert ACTION_ACCESS_MAPS["nested_credentials"] is INTEGRATION_CREDENTIAL_ACTIONS
    assert ACTION_ACCESS_MAPS["webhooks"] is WEBHOOK_ACTIONS
    assert ACTION_ACCESS_MAPS["deliveries"] is DELIVERY_ACTIONS
    assert ACTION_ACCESS_MAPS["mappings"] is MAPPING_ACTIONS
    assert ACTION_ACCESS_MAPS["health"] is HEALTH_ACTIONS


def test_signature_permission_message_text_is_pinned() -> None:
    assert InboundWebhookSignaturePermission.message == "A valid signed webhook request is required."


def test_signature_permission_regex_matches_only_exact_sha256_shape() -> None:
    pattern = InboundWebhookSignaturePermission._signature
    assert pattern.fullmatch(f"sha256={'a' * 64}") is not None
    assert pattern.fullmatch(f"sha256={'A' * 64}") is not None
    assert pattern.fullmatch(f"sha256={'a' * 63}") is None
    assert pattern.fullmatch(f"sha256={'a' * 65}") is None
    assert pattern.fullmatch(f"SHA256={'a' * 64}") is None
    assert pattern.fullmatch(f"sha256={'g' * 64}") is None
    assert pattern.fullmatch("") is None


@pytest.mark.parametrize("nonce", ["", "a" * 15])
def test_signature_permission_rejects_nonce_shorter_than_minimum(nonce: str) -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE=nonce,
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": "11111111-1111-1111-1111-111111111111"}),
        )


def test_signature_permission_rejects_nonce_longer_than_maximum() -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="a" * 129,
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": "11111111-1111-1111-1111-111111111111"}),
        )


def test_signature_permission_rejects_zero_and_negative_timestamp() -> None:
    for bad_timestamp in ("0", "-1"):
        request = APIRequestFactory().post(
            "/",
            b"{}",
            content_type="application/json",
            HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=bad_timestamp,
            HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
            HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
        )
        with pytest.raises(AuthenticationFailed):
            InboundWebhookSignaturePermission().has_permission(
                request,
                SimpleNamespace(kwargs={"public_id": "11111111-1111-1111-1111-111111111111"}),
            )


def test_signature_permission_rejects_missing_timestamp_header() -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": "11111111-1111-1111-1111-111111111111"}),
        )


def test_signature_permission_rejects_missing_public_id_kwarg() -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={}),
        )


def test_signature_permission_rejects_view_without_kwargs_attribute() -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(),
        )


def test_signature_permission_accepts_uuid_instance_public_id(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    allowed = InboundWebhookSignaturePermission().has_permission(
        request,
        # public_id passed as an already-constructed UUID instance, exercising
        # the isinstance(raw_public_id, UUID) True branch directly.
        SimpleNamespace(kwargs={"public_id": webhook.public_id}),
    )
    assert allowed is True
    assert request.verified_webhook_public_id == webhook.public_id


def test_signature_permission_rejects_outbound_webhook_public_id(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="outbound",
        url="https://example.com/hook",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_signature_permission_rejects_unknown_public_id(tenant_a) -> None:
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": "22222222-2222-2222-2222-222222222222"}),
        )


def test_signature_permission_rejects_soft_deleted_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    webhook.is_deleted = True
    webhook.save()
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_access_requirement_is_frozen() -> None:
    requirement = AccessRequirement(INTEGRATION_READ, MODULE_ENTITLEMENT, "resource", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.quota_cost = 2  # type: ignore[misc]


def test_access_requirement_uses_slots_with_no_instance_dict() -> None:
    requirement = AccessRequirement(INTEGRATION_READ, MODULE_ENTITLEMENT, "resource", 1)
    assert not hasattr(requirement, "__dict__")
    assert hasattr(AccessRequirement, "__slots__")
    assert AccessRequirement.__slots__ == (
        "permission",
        "entitlement",
        "quota_resource",
        "quota_cost",
    )


def test_access_requires_cost_as_keyword_only_argument() -> None:
    # `cost` is declared keyword-only (`*, cost: int = 1`); passing it positionally
    # must be rejected so a mutant that turns `*` into `/` cannot silently make
    # positional cost arguments legal.
    with pytest.raises(TypeError):
        access(INTEGRATION_READ, "integration_platform.integration.read", 5)  # type: ignore[misc]


def test_signature_permission_converts_string_public_id_to_uuid_instance(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    allowed = InboundWebhookSignaturePermission().has_permission(
        request,
        # raw_public_id supplied as a plain string, exercising the
        # isinstance(raw_public_id, UUID) False branch that must coerce it
        # via UUID(str(raw_public_id)) rather than pass the string through.
        SimpleNamespace(kwargs={"public_id": str(webhook.public_id)}),
    )
    assert allowed is True
    assert request.verified_webhook_public_id == webhook.public_id
    from uuid import UUID as _UUID

    assert isinstance(request.verified_webhook_public_id, _UUID)


def test_signature_permission_rejects_timestamp_zero_even_with_active_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP="0",
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_signature_permission_accepts_timestamp_of_exactly_one_with_active_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP="1",
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    allowed = InboundWebhookSignaturePermission().has_permission(
        request,
        SimpleNamespace(kwargs={"public_id": webhook.public_id}),
    )
    assert allowed is True
    assert request.verified_webhook_public_id == webhook.public_id


def test_signature_permission_rejects_nonce_of_fifteen_chars_even_with_active_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="a" * 15,
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_signature_permission_accepts_nonce_of_exactly_128_chars_with_active_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="a" * 128,
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    allowed = InboundWebhookSignaturePermission().has_permission(
        request,
        SimpleNamespace(kwargs={"public_id": webhook.public_id}),
    )
    assert allowed is True
    assert request.verified_webhook_public_id == webhook.public_id


def test_signature_permission_rejects_nonce_of_129_chars_even_with_active_webhook(tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="a" * 129,
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_signature_permission_rejects_invalid_nonce_even_when_signature_and_webhook_are_valid(tenant_a) -> None:
    # Isolates the nonce-length OR-clause: timestamp is valid, signature is
    # valid, an active matching webhook exists — only the nonce is out of
    # range. This proves the boolean structure short-circuits to a rejection
    # regardless of the other two clauses (guards against `or` -> `and`
    # mutants collapsing the boolean expression).
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="short",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'a' * 64}",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )


def test_signature_permission_rejects_invalid_signature_even_when_timestamp_and_nonce_are_valid(tenant_a) -> None:
    # Mirrors the previous test for the second OR-clause: timestamp and nonce
    # are valid and the webhook exists and is active — only the signature
    # shape is wrong.
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    request = APIRequestFactory().post(
        "/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="0123456789abcdef",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE="not-a-valid-signature",
    )
    with pytest.raises(AuthenticationFailed):
        InboundWebhookSignaturePermission().has_permission(
            request,
            SimpleNamespace(kwargs={"public_id": webhook.public_id}),
        )
