"""Fail-closed policy permission tests."""

from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from src.core.auth.policy_permissions import PolicyRequiredPermission


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
