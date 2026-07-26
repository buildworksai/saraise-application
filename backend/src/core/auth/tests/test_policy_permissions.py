"""Fail-closed policy permission tests."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from src.core.auth.policy_permissions import PolicyRequiredPermission, _PolicyCircuitBreaker
from src.core.user_models import UserProfile


def _request():
    request = APIRequestFactory().get("/api/v1/protected/")
    request.user = SimpleNamespace(
        is_authenticated=True,
        roles=["tenant_admin"],
        groups=[],
        has_perm=lambda permission: False,
        pk="user-1",
    )
    request.tenant_id = "11111111-1111-4111-8111-111111111111"
    return request


def test_permission_without_contract_is_denied():
    assert PolicyRequiredPermission().has_permission(_request(), SimpleNamespace()) is False


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="")
def test_saas_missing_policy_configuration_is_denied():
    view = SimpleNamespace(required_permissions=["crm.lead:read"])
    assert PolicyRequiredPermission().has_permission(_request(), view) is False


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.invalid")
@patch("requests.post", side_effect=requests.ConnectionError("unavailable"))
def test_saas_policy_outage_is_denied(mock_post):
    view = SimpleNamespace(required_permissions=["crm.lead:read"])
    assert PolicyRequiredPermission().has_permission(_request(), view) is False
    mock_post.assert_called_once()


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.invalid")
@patch("requests.post")
@pytest.mark.parametrize("status_code", [429, 500])
def test_saas_policy_breaker_opens_after_http_failure_threshold(mock_post, status_code):
    mock_post.return_value.status_code = status_code
    permission = PolicyRequiredPermission()
    permission._circuit_breaker = _PolicyCircuitBreaker(threshold=2, reset_seconds=30)
    view = SimpleNamespace(required_permissions=["crm.lead:read"])

    assert permission.has_permission(_request(), view) is False
    assert permission.has_permission(_request(), view) is False
    assert permission.has_permission(_request(), view) is False

    assert mock_post.call_count == 2
    assert permission._circuit_breaker._failures == 2


@pytest.mark.django_db
def test_real_profile_roles_are_used_without_universal_tenant_bypass():
    user = get_user_model().objects.create_user(username="role-test", password="testpass123")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = "11111111-1111-4111-8111-111111111111"
    profile.tenant_role = "tenant_admin"
    with patch.object(UserProfile, "clean"):
        profile.save()
    request = _request()
    request.user = get_user_model().objects.select_related("profile").get(pk=user.pk)
    permission = PolicyRequiredPermission()

    assert permission.has_permission(request, SimpleNamespace(required_permissions=["tenant:read"])) is True
    assert permission.has_permission(request, SimpleNamespace(required_permissions=["platform.settings:read"])) is False
    assert permission.has_permission(request, SimpleNamespace(required_permissions=["security.roles:read"])) is False
