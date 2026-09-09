"""Direct unit coverage for email_marketing.permissions branches."""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.user_models import UserProfile
from src.modules.email_marketing.permissions import (
    PERMISSIONS,
    EmailMarketingAccessMixin,
    ProviderWebhookPermission,
    StrictSessionAuthentication,
)
from src.modules.email_marketing.services import ConfigurationService

pytestmark = pytest.mark.django_db
User = get_user_model()


def _make_user(tenant: uuid.UUID, role: str = "tenant_admin") -> object:
    user = User.objects.create_user(username=f"perm-{uuid.uuid4()}", password="test-password")
    with patch.object(UserProfile, "clean"):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"tenant_id": str(tenant), "tenant_role": role},
        )
    return User.objects.get(pk=user.pk)


class SlottedRequest:
    """A request-like object without a `tenant_id` slot to force AttributeError."""

    __slots__ = ("headers", "body")

    def __init__(self, headers: dict, body: bytes) -> None:
        self.headers = headers
        self.body = body


def test_permissions_registry_is_pinned_exactly() -> None:
    assert PERMISSIONS == (
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
        "email_marketing.configuration:read",
        "email_marketing.configuration:manage",
        "email_marketing.configuration:export",
    )


def test_strict_session_authentication_header_is_pinned() -> None:
    auth = StrictSessionAuthentication()
    assert auth.authenticate_header(SimpleNamespace()) == "Session"
    assert auth.authenticate_header(None) == "Session"
    assert auth.authenticate_header(object()) == "Session"


def test_mixin_class_defaults_are_pinned() -> None:
    assert EmailMarketingAccessMixin.authentication_classes == (StrictSessionAuthentication,)
    assert EmailMarketingAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
    assert EmailMarketingAccessMixin.action_permissions == {}
    assert EmailMarketingAccessMixin.action_quotas == {}
    assert EmailMarketingAccessMixin.read_actions == frozenset({"list", "retrieve", "analytics"})


def test_required_permission_for_action_returns_mapped_value_or_none() -> None:
    mixin = EmailMarketingAccessMixin()
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    assert mixin.required_permission_for_action("list") == "email_marketing.campaign:read"
    assert mixin.required_permission_for_action("destroy") is None


def test_get_permissions_with_no_tenant_id_skips_flag_checks_and_returns_permissions() -> None:
    user = User.objects.create_user(username=f"no-tenant-{uuid.uuid4()}", password="x")
    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    result = mixin.get_permissions()

    assert mixin.request.tenant_id is None
    assert mixin.required_permission == "email_marketing.campaign:read"
    assert mixin.required_entitlement == "email_marketing"
    assert mixin.quota_resource == "email_marketing.api_reads"
    assert mixin.quota_cost == 1
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_get_permissions_with_invalid_tenant_string_sets_none() -> None:
    user = User.objects.create_user(username=f"bad-tenant-{uuid.uuid4()}", password="x")
    with patch.object(UserProfile, "clean"):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"tenant_id": "not-a-uuid", "tenant_role": "tenant_admin"},
        )
    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=User.objects.get(pk=user.pk))

    mixin.get_permissions()

    assert mixin.request.tenant_id is None


def test_get_permissions_configuration_action_skips_flag_gate_even_when_disabled() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    disabled = deepcopy(current.document)
    disabled["feature_flags"]["enabled"] = False
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, disabled, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "current"
    mixin.action_permissions = {"current": "email_marketing.configuration:manage"}
    mixin.request = SimpleNamespace(user=user)

    result = mixin.get_permissions()

    assert len(result) == 2
    assert mixin.quota_resource == "email_marketing.api_writes"


def test_get_permissions_denies_when_flags_disabled() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    disabled = deepcopy(current.document)
    disabled["feature_flags"]["enabled"] = False
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, disabled, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with pytest.raises(PermissionDenied, match="Email marketing is disabled for this tenant."):
        mixin.get_permissions()


def test_get_permissions_denies_when_role_not_in_allowed_roles() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["roles"] = ["tenant_owner"]
    user = _make_user(tenant, role="tenant_admin")
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with pytest.raises(PermissionDenied, match="Email marketing is not enabled for this tenant role."):
        mixin.get_permissions()


def test_get_permissions_allows_when_role_in_allowed_roles() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["roles"] = ["tenant_admin"]
    user = _make_user(tenant, role="tenant_admin")
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    result = mixin.get_permissions()
    assert len(result) == 2


def test_get_permissions_denies_when_cohort_not_member() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["cohorts"] = ["beta"]
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with override_settings(SARAISE_TENANT_COHORTS={}):
        with pytest.raises(PermissionDenied, match="Email marketing is not enabled for this tenant cohort."):
            mixin.get_permissions()


def test_get_permissions_allows_when_cohort_membership_intersects() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["cohorts"] = ["beta"]
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with override_settings(SARAISE_TENANT_COHORTS={str(tenant): ("beta", "gamma")}):
        result = mixin.get_permissions()
    assert len(result) == 2


def test_get_permissions_treats_non_dict_cohort_membership_as_empty() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["cohorts"] = ["beta"]
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with override_settings(SARAISE_TENANT_COHORTS=["not", "a", "dict"]):
        with pytest.raises(PermissionDenied, match="Email marketing is not enabled for this tenant cohort."):
            mixin.get_permissions()


def test_get_permissions_denies_when_outside_rollout_percentage() -> None:
    tenant = uuid.uuid4()
    current = ConfigurationService.current(tenant)
    restricted = deepcopy(current.document)
    restricted["feature_flags"]["rollout_percentage"] = 0
    user = _make_user(tenant)
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}")
    ConfigurationService.update(tenant, actor_id, restricted, expected_version=current.version)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    with pytest.raises(PermissionDenied, match="Email marketing is outside this actor's rollout cohort."):
        mixin.get_permissions()


def test_get_permissions_allows_when_rollout_percentage_is_full() -> None:
    tenant = uuid.uuid4()
    # default rollout_percentage is 100 which always admits every bucket (0-99).
    user = _make_user(tenant)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "list"
    mixin.action_permissions = {"list": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    result = mixin.get_permissions()
    assert len(result) == 2


def test_get_permissions_quota_resource_uses_action_quota_override() -> None:
    tenant = uuid.uuid4()
    user = _make_user(tenant)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "resolve_audience"
    mixin.action_permissions = {"resolve_audience": "email_marketing.campaign:resolve_audience"}
    mixin.action_quotas = {"resolve_audience": "email_marketing.audience_resolutions"}
    mixin.request = SimpleNamespace(user=user)

    mixin.get_permissions()
    assert mixin.quota_resource == "email_marketing.audience_resolutions"


def test_get_permissions_quota_resource_defaults_to_writes_for_non_read_action() -> None:
    tenant = uuid.uuid4()
    user = _make_user(tenant)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "create"
    mixin.action_permissions = {"create": "email_marketing.campaign:create"}
    mixin.request = SimpleNamespace(user=user)

    mixin.get_permissions()
    assert mixin.quota_resource == "email_marketing.api_writes"


def test_get_permissions_quota_resource_defaults_to_reads_for_read_action() -> None:
    tenant = uuid.uuid4()
    user = _make_user(tenant)

    mixin = EmailMarketingAccessMixin()
    mixin.action = "retrieve"
    mixin.action_permissions = {"retrieve": "email_marketing.campaign:read"}
    mixin.request = SimpleNamespace(user=user)

    mixin.get_permissions()
    assert mixin.quota_resource == "email_marketing.api_reads"


def test_get_permissions_defaults_action_to_empty_string_when_absent() -> None:
    tenant = uuid.uuid4()
    user = _make_user(tenant)

    mixin = EmailMarketingAccessMixin()
    mixin.request = SimpleNamespace(user=user)
    # `action` attribute intentionally not set on the mixin instance.

    mixin.get_permissions()
    assert mixin.required_permission is None
    assert mixin.quota_resource == "email_marketing.api_writes"


# ---------------------------------------------------------------------------
# ProviderWebhookPermission
# ---------------------------------------------------------------------------


def _signed_request(
    *,
    secret: str = "provider-secret",
    gateway: str = "provider",
    body: bytes = b'{"event":"delivered"}',
    timestamp: int | None = None,
    bad_signature: bool = False,
    request_cls: type = SimpleNamespace,
) -> object:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    digest = hmac.new(secret.encode("utf-8"), ts.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    signature = "0" * len(digest) if bad_signature else digest
    headers = {
        "X-Email-Gateway": gateway,
        "X-Email-Timestamp": ts,
        "X-Email-Signature": signature,
    }
    if request_cls is SlottedRequest:
        return SlottedRequest(headers=headers, body=body)
    return SimpleNamespace(headers=headers, body=body)


def test_provider_webhook_permission_missing_headers_default_and_fail() -> None:
    permission = ProviderWebhookPermission()
    request = SimpleNamespace(headers={}, body=b"")
    assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_non_integer_timestamp_fails() -> None:
    permission = ProviderWebhookPermission()
    request = SimpleNamespace(
        headers={"X-Email-Gateway": "provider", "X-Email-Timestamp": "not-a-number", "X-Email-Signature": "abc"},
        body=b"",
    )
    assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_accounts_not_configured_dict_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(EMAIL_MARKETING_PROVIDER_ACCOUNTS=["not", "a", "dict"]):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_unknown_gateway_key_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request(gateway="unknown-gateway")
    with override_settings(EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(uuid.uuid4()), "webhook_secret": "x"}}):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_account_not_dict_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": "not-a-dict"}):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_missing_secret_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(uuid.uuid4())}}
    ):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_empty_secret_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(uuid.uuid4()), "webhook_secret": ""}}
    ):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_non_string_secret_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(uuid.uuid4()), "webhook_secret": 12345}}
    ):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_missing_tenant_fails() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"webhook_secret": "provider-secret"}}
    ):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_invalid_tenant_uuid_fails_closed() -> None:
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={
            "provider": {"tenant_id": "not-a-valid-uuid", "webhook_secret": "provider-secret"}
        }
    ):
        assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_stale_timestamp_outside_replay_window_fails() -> None:
    tenant = uuid.uuid4()
    permission = ProviderWebhookPermission()
    stale_timestamp = int(time.time()) - 10_000
    request = _signed_request(timestamp=stale_timestamp)
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": "provider-secret"}}
    ):
        with patch(
            "src.modules.email_marketing.services.get_runtime_configuration",
            return_value=SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
        ):
            assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_bad_signature_fails() -> None:
    tenant = uuid.uuid4()
    permission = ProviderWebhookPermission()
    request = _signed_request(bad_signature=True)
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": "provider-secret"}}
    ):
        with patch(
            "src.modules.email_marketing.services.get_runtime_configuration",
            return_value=SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
        ):
            assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_attribute_assignment_failure_fails_closed() -> None:
    tenant = uuid.uuid4()
    permission = ProviderWebhookPermission()
    request = _signed_request(request_cls=SlottedRequest)
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": "provider-secret"}}
    ):
        with patch(
            "src.modules.email_marketing.services.get_runtime_configuration",
            return_value=SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
        ):
            assert permission.has_permission(request, SimpleNamespace()) is False


def test_provider_webhook_permission_success_sets_tenant_and_gateway_context() -> None:
    tenant = uuid.uuid4()
    permission = ProviderWebhookPermission()
    request = _signed_request()
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": "provider-secret"}}
    ):
        with patch(
            "src.modules.email_marketing.services.get_runtime_configuration",
            return_value=SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
        ):
            assert permission.has_permission(request, SimpleNamespace()) is True
    assert request.tenant_id == tenant
    assert request.gateway_key == "provider"


def test_provider_webhook_permission_replay_window_boundary_is_inclusive() -> None:
    tenant = uuid.uuid4()
    permission = ProviderWebhookPermission()
    boundary_timestamp = int(time.time()) - 300
    request = _signed_request(timestamp=boundary_timestamp)
    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": "provider-secret"}}
    ):
        with patch(
            "src.modules.email_marketing.services.get_runtime_configuration",
            return_value=SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
        ):
            assert permission.has_permission(request, SimpleNamespace()) is True
    assert request.tenant_id == tenant
