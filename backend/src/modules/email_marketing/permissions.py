"""Fail-closed private and public access controls for email marketing."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final
from uuid import UUID

from django.conf import settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "email_marketing.campaign:read",
    "email_marketing.campaign:create",
    "email_marketing.campaign:update",
    "email_marketing.campaign:delete",
    "email_marketing.campaign:resolve_audience",
    "email_marketing.campaign:schedule",
    "email_marketing.campaign:send",
    "email_marketing.campaign:pause",
    "email_marketing.campaign:cancel",
    "email_marketing.analytics:read",
    "email_marketing.template:read",
    "email_marketing.template:create",
    "email_marketing.template:update",
    "email_marketing.template:delete",
    "email_marketing.template:activate",
    "email_marketing.recipient:read",
    "email_marketing.recipient:retry",
    "email_marketing.delivery:read",
    "email_marketing.suppression:read",
    "email_marketing.suppression:manage",
    "email_marketing.consent:read",
    "email_marketing.consent:record",
    "email_marketing.consent:revoke",
    "email_marketing.health:read",
    "email_marketing.provider_event:ingest",
)


class StrictSessionAuthentication(SessionAuthentication):
    """Standard Django session authentication with mandatory CSRF enforcement."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class EmailMarketingAccessMixin:
    """Resolve action policy, module entitlement, and metered quota explicitly."""

    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    read_actions = frozenset({"list", "retrieve", "analytics"})

    def get_permissions(self) -> list[BasePermission]:
        action = str(getattr(self, "action", ""))
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant))
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = "email_marketing"
        self.quota_resource = self.action_quotas.get(
            action,
            "email_marketing.api_reads" if action in self.read_actions else "email_marketing.api_writes",
        )
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


class ProviderWebhookPermission(BasePermission):
    """Authenticate a provider account using a bounded HMAC replay window.

    Tenant identity comes only from trusted server configuration keyed by the
    provider account, never from the event body.
    """

    message = "Provider event authentication failed."
    max_age_seconds = 300

    def has_permission(self, request: object, view: object) -> bool:
        del view
        headers = getattr(request, "headers", {})
        gateway_key = str(headers.get("X-Email-Gateway", "")).strip()
        timestamp_text = str(headers.get("X-Email-Timestamp", "")).strip()
        signature = str(headers.get("X-Email-Signature", "")).strip()
        try:
            timestamp = int(timestamp_text)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time()) - timestamp) > self.max_age_seconds:
            return False
        accounts = getattr(settings, "EMAIL_MARKETING_PROVIDER_ACCOUNTS", {})
        account = accounts.get(gateway_key) if isinstance(accounts, dict) else None
        if not isinstance(account, dict):
            return False
        secret = account.get("webhook_secret")
        tenant = account.get("tenant_id")
        if not isinstance(secret, str) or not secret or tenant is None:
            return False
        body = bytes(getattr(request, "body", b""))
        digest = hmac.new(secret.encode("utf-8"), timestamp_text.encode("ascii") + b"." + body, hashlib.sha256)
        if not hmac.compare_digest(signature, digest.hexdigest()):
            return False
        try:
            request.tenant_id = UUID(str(tenant))
        except (TypeError, ValueError, AttributeError):
            return False
        request.gateway_key = gateway_key
        return True


__all__ = [
    "EmailMarketingAccessMixin",
    "PERMISSIONS",
    "ProviderWebhookPermission",
    "StrictSessionAuthentication",
]
