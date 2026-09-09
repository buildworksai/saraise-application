"""
Unit tests for TenantManagementPermission.

Pins exact behavior of the resource/action derivation and delegation to
PolicyRequiredPermission.has_permission so mutation testing on
src/modules/tenant_management/permissions.py has full branch and value
coverage.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.modules.tenant_management.permissions import TenantManagementPermission


class _View:
    """Minimal stand-in for a DRF view exposing permission_resource."""

    def __init__(self, permission_resource=None):
        if permission_resource is not None:
            self.permission_resource = permission_resource
        # required_permissions intentionally absent until set by the
        # permission class under test.


def _request(method):
    return SimpleNamespace(method=method)


class TestTenantManagementPermissionNoResource:
    def test_missing_permission_resource_attribute_denies(self):
        """No permission_resource attribute at all -> denied, no delegation."""
        perm = TenantManagementPermission()
        view = _View()  # no permission_resource set
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission"
        ) as mock_super:
            result = perm.has_permission(_request("GET"), view)
        assert result is False
        mock_super.assert_not_called()

    def test_none_permission_resource_denies(self):
        perm = TenantManagementPermission()
        view = _View(permission_resource=None)
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission"
        ) as mock_super:
            result = perm.has_permission(_request("GET"), view)
        assert result is False
        mock_super.assert_not_called()

    def test_empty_string_permission_resource_denies(self):
        """Empty string is falsy -> denied (exercises `not resource`, not `is None`)."""
        perm = TenantManagementPermission()
        view = _View(permission_resource="")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission"
        ) as mock_super:
            result = perm.has_permission(_request("GET"), view)
        assert result is False
        mock_super.assert_not_called()


class TestTenantManagementPermissionSafeMethods:
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_safe_methods_derive_read_action(self, method):
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenants")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=True,
        ) as mock_super:
            result = perm.has_permission(_request(method), view)
        assert result is True
        assert view.required_permissions == ["tenants:read"]
        mock_super.assert_called_once()

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_unsafe_methods_derive_write_action(self, method):
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenants")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=True,
        ) as mock_super:
            result = perm.has_permission(_request(method), view)
        assert result is True
        assert view.required_permissions == ["tenants:write"]
        mock_super.assert_called_once()


class TestTenantManagementPermissionDelegation:
    def test_delegates_return_value_from_super_true(self):
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenants")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=True,
        ):
            assert perm.has_permission(_request("GET"), view) is True

    def test_delegates_return_value_from_super_false(self):
        """Confirms the method does not short-circuit to True after setting
        required_permissions -- the delegated (denying) result is returned."""
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenants")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=False,
        ):
            assert perm.has_permission(_request("GET"), view) is False

    def test_required_permissions_format_is_resource_colon_action(self):
        """Exact string pin -- catches mutants swapping ':' for another
        separator or altering the f-string composition."""
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenant_settings")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=True,
        ):
            perm.has_permission(_request("PATCH"), view)
        assert view.required_permissions == ["tenant_settings:write"]
        assert view.required_permissions != ["tenant_settings-write"]
        assert len(view.required_permissions) == 1

    def test_super_called_with_original_request_and_view(self):
        perm = TenantManagementPermission()
        view = _View(permission_resource="tenants")
        request = _request("GET")
        with patch(
            "src.modules.tenant_management.permissions.PolicyRequiredPermission.has_permission",
            return_value=True,
        ) as mock_super:
            perm.has_permission(request, view)
        mock_super.assert_called_once_with(request, view)
