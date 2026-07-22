"""Executable authorization metadata and signed-transport boundary tests."""

from __future__ import annotations

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
    CONNECTOR_ACTIONS,
    CREDENTIAL_ACTIONS,
    DELIVERY_ACTIONS,
    HEALTH_ACTIONS,
    INTEGRATION_ACTIONS,
    INTEGRATION_CREDENTIAL_ACTIONS,
    MAPPING_ACTIONS,
    PERMISSIONS,
    SOD_ACTIONS,
    WEBHOOK_ACTIONS,
    InboundWebhookSignaturePermission,
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
        (CONNECTOR_ACTIONS, {"list", "retrieve", "schema", "health"}),
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
