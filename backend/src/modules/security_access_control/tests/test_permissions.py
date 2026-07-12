from types import SimpleNamespace

from rest_framework.test import APIRequestFactory

from src.modules.security_access_control.permissions import SecurityAdminPermission, SecurityViewerPermission


def build_request(method="get", roles=None, authenticated=True):
    request = APIRequestFactory().generic(method, "/")
    request.user = SimpleNamespace(
        is_authenticated=authenticated,
        roles=roles or [],
        has_perm=lambda permission: permission in {"security.roles:read", "security.roles:update"},
    )
    return request


def test_security_admin_permission_denies_unauthenticated():
    permission = SecurityAdminPermission()
    request = build_request(authenticated=False)
    assert permission.has_permission(request, None) is False


def test_security_admin_permission_uses_declared_permissions():
    permission = SecurityAdminPermission()
    request = build_request()
    assert permission.has_permission(request, None) is True


def test_security_viewer_permission_safe_methods_only():
    permission = SecurityViewerPermission()
    request = build_request(method="get")
    assert permission.has_permission(request, None) is True

    request = build_request(method="post", roles=["security_viewer"])
    assert permission.has_permission(request, None) is False
