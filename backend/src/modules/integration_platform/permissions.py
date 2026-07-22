"""Fail-closed access declarations for Integration Platform API v2.

The action maps in this module are executable policy metadata, not UI hints.
Every governed view selects one exact requirement before ``RequiresAccess``
runs.  An unrecognised DRF action therefore has no permission and is denied by
the core access pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Mapping
from uuid import UUID

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

MODULE_ENTITLEMENT: Final = "integration_platform"

CONNECTOR_READ: Final = "integration_platform.connector:read"
INTEGRATION_CREATE: Final = "integration_platform.integration:create"
INTEGRATION_READ: Final = "integration_platform.integration:read"
INTEGRATION_UPDATE: Final = "integration_platform.integration:update"
INTEGRATION_DELETE: Final = "integration_platform.integration:delete"
INTEGRATION_TEST: Final = "integration_platform.integration:test"
INTEGRATION_SYNC: Final = "integration_platform.integration:sync"
INTEGRATION_ACTIVATE: Final = "integration_platform.integration:activate"
INTEGRATION_DEACTIVATE: Final = "integration_platform.integration:deactivate"
CREDENTIAL_CREATE: Final = "integration_platform.credential:create"
CREDENTIAL_READ: Final = "integration_platform.credential:read"
CREDENTIAL_ROTATE: Final = "integration_platform.credential:rotate"
CREDENTIAL_REVOKE: Final = "integration_platform.credential:revoke"
WEBHOOK_CREATE: Final = "integration_platform.webhook:create"
WEBHOOK_READ: Final = "integration_platform.webhook:read"
WEBHOOK_UPDATE: Final = "integration_platform.webhook:update"
WEBHOOK_DELETE: Final = "integration_platform.webhook:delete"
WEBHOOK_ACTIVATE: Final = "integration_platform.webhook:activate"
WEBHOOK_DEACTIVATE: Final = "integration_platform.webhook:deactivate"
WEBHOOK_ROTATE_SECRET: Final = "integration_platform.webhook:rotate_secret"
DELIVERY_READ: Final = "integration_platform.delivery:read"
DELIVERY_REDRIVE: Final = "integration_platform.delivery:redrive"
MAPPING_CREATE: Final = "integration_platform.mapping:create"
MAPPING_READ: Final = "integration_platform.mapping:read"
MAPPING_UPDATE: Final = "integration_platform.mapping:update"
MAPPING_DELETE: Final = "integration_platform.mapping:delete"
MAPPING_PREVIEW: Final = "integration_platform.mapping:preview"
HEALTH_READ: Final = "integration_platform.health:read"


PERMISSIONS: Final[tuple[str, ...]] = (
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

# Creation and destructive authority must never be bundled into one role.
SOD_ACTIONS: Final[tuple[tuple[str, str], ...]] = (
    (INTEGRATION_CREATE, INTEGRATION_DELETE),
    (CREDENTIAL_CREATE, CREDENTIAL_REVOKE),
)


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Policy, entitlement, quota resource, and metering cost for one action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int


def access(permission: str, quota_resource: str, *, cost: int = 1) -> AccessRequirement:
    """Build one explicit module access requirement."""

    if cost < 1:
        raise ValueError("quota cost must be positive")
    return AccessRequirement(permission, MODULE_ENTITLEMENT, quota_resource, cost)


CONNECTOR_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(CONNECTOR_READ, "integration_platform.connector.read"),
    "retrieve": access(CONNECTOR_READ, "integration_platform.connector.read"),
    "schema": access(CONNECTOR_READ, "integration_platform.connector.read"),
    "health": access(CONNECTOR_READ, "integration_platform.connector.health"),
}

INTEGRATION_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(INTEGRATION_READ, "integration_platform.integration.read"),
    "retrieve": access(INTEGRATION_READ, "integration_platform.integration.read"),
    "create": access(INTEGRATION_CREATE, "integration_platform.integration.write", cost=2),
    "partial_update": access(INTEGRATION_UPDATE, "integration_platform.integration.write", cost=2),
    "destroy": access(INTEGRATION_DELETE, "integration_platform.integration.write", cost=2),
    "activate": access(INTEGRATION_ACTIVATE, "integration_platform.integration.transition", cost=2),
    "deactivate": access(INTEGRATION_DEACTIVATE, "integration_platform.integration.transition", cost=2),
    "test_connection": access(INTEGRATION_TEST, "integration_platform.integration.test", cost=5),
    "sync": access(INTEGRATION_SYNC, "integration_platform.integration.sync", cost=10),
    "job": access(INTEGRATION_READ, "integration_platform.integration.job.read"),
}

CREDENTIAL_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "retrieve": access(CREDENTIAL_READ, "integration_platform.credential.read"),
    "rotate": access(CREDENTIAL_ROTATE, "integration_platform.credential.write", cost=3),
    "revoke": access(CREDENTIAL_REVOKE, "integration_platform.credential.write", cost=2),
}

INTEGRATION_CREDENTIAL_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(CREDENTIAL_READ, "integration_platform.credential.read"),
    "create": access(CREDENTIAL_CREATE, "integration_platform.credential.write", cost=2),
}

WEBHOOK_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(WEBHOOK_READ, "integration_platform.webhook.read"),
    "retrieve": access(WEBHOOK_READ, "integration_platform.webhook.read"),
    "create": access(WEBHOOK_CREATE, "integration_platform.webhook.write", cost=2),
    "partial_update": access(WEBHOOK_UPDATE, "integration_platform.webhook.write", cost=2),
    "destroy": access(WEBHOOK_DELETE, "integration_platform.webhook.write", cost=2),
    "activate": access(WEBHOOK_ACTIVATE, "integration_platform.webhook.transition", cost=2),
    "deactivate": access(WEBHOOK_DEACTIVATE, "integration_platform.webhook.transition", cost=2),
    "rotate_secret": access(WEBHOOK_ROTATE_SECRET, "integration_platform.webhook.secret", cost=3),
}

DELIVERY_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(DELIVERY_READ, "integration_platform.delivery.read"),
    "retrieve": access(DELIVERY_READ, "integration_platform.delivery.read"),
    "redrive": access(DELIVERY_REDRIVE, "integration_platform.delivery.redrive", cost=5),
}

MAPPING_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "list": access(MAPPING_READ, "integration_platform.mapping.read"),
    "retrieve": access(MAPPING_READ, "integration_platform.mapping.read"),
    "create": access(MAPPING_CREATE, "integration_platform.mapping.write", cost=2),
    "partial_update": access(MAPPING_UPDATE, "integration_platform.mapping.write", cost=2),
    "destroy": access(MAPPING_DELETE, "integration_platform.mapping.write", cost=2),
    "validate_mappings": access(MAPPING_PREVIEW, "integration_platform.mapping.preview", cost=2),
    "preview": access(MAPPING_PREVIEW, "integration_platform.mapping.preview", cost=3),
}

HEALTH_ACTIONS: Final[Mapping[str, AccessRequirement]] = {
    "get": access(HEALTH_READ, "integration_platform.health.read"),
}

ACTION_ACCESS_MAPS: Final[Mapping[str, Mapping[str, AccessRequirement]]] = {
    "connectors": CONNECTOR_ACTIONS,
    "integrations": INTEGRATION_ACTIONS,
    "integration_credentials": CREDENTIAL_ACTIONS,
    "nested_credentials": INTEGRATION_CREDENTIAL_ACTIONS,
    "webhooks": WEBHOOK_ACTIONS,
    "deliveries": DELIVERY_ACTIONS,
    "mappings": MAPPING_ACTIONS,
    "health": HEALTH_ACTIONS,
}


class InboundWebhookSignaturePermission(BasePermission):
    """Fail closed before inbound signature/replay authority enters service code.

    This boundary validates the transport credential shape and resolves only an
    active inbound public identifier.  ``WebhookService.receive`` remains the
    sole authority that decrypts the secret, performs constant-time HMAC, and
    atomically consumes the nonce; the permission never double-consumes replay
    state.
    """

    message = "A valid signed webhook request is required."
    _signature = re.compile(r"^sha256=[0-9a-fA-F]{64}$")

    def has_permission(self, request: Request, view: object) -> bool:
        from .models import Webhook, WebhookDirection, WebhookStatus

        raw_public_id = getattr(view, "kwargs", {}).get("public_id")
        try:
            public_id = raw_public_id if isinstance(raw_public_id, UUID) else UUID(str(raw_public_id))
            timestamp = int(request.headers.get("X-SARAISE-Webhook-Timestamp", ""))
        except (AttributeError, TypeError, ValueError) as exc:
            raise AuthenticationFailed(self.message) from exc
        nonce = request.headers.get("X-SARAISE-Webhook-Nonce", "")
        signature = request.headers.get("X-SARAISE-Webhook-Signature", "")
        if timestamp < 1 or not 16 <= len(nonce) <= 128 or self._signature.fullmatch(signature) is None:
            raise AuthenticationFailed(self.message)
        exists = Webhook.objects.filter(
            public_id=public_id,
            direction=WebhookDirection.INBOUND,
            status=WebhookStatus.ACTIVE,
            is_deleted=False,
        ).exists()
        if not exists:
            raise AuthenticationFailed(self.message)
        setattr(request, "verified_webhook_public_id", public_id)
        return True


__all__ = [
    "ACTION_ACCESS_MAPS",
    "AccessRequirement",
    "CONNECTOR_ACTIONS",
    "CREDENTIAL_ACTIONS",
    "DELIVERY_ACTIONS",
    "HEALTH_ACTIONS",
    "INTEGRATION_ACTIONS",
    "INTEGRATION_CREDENTIAL_ACTIONS",
    "InboundWebhookSignaturePermission",
    "MAPPING_ACTIONS",
    "MODULE_ENTITLEMENT",
    "PERMISSIONS",
    "SOD_ACTIONS",
    "WEBHOOK_ACTIONS",
]
