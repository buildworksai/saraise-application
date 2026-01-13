from types import SimpleNamespace

from rest_framework.test import APIRequestFactory

from src.modules.platform_management.permissions import PlatformAdminPermission, PlatformViewerPermission


def build_request(method="get", roles=None, authenticated=True):
    request = APIRequestFactory().generic(method, "/")
    request.user = SimpleNamespace(
        is_authenticated=authenticated,
        roles=roles or [],
    )
    return request


def test_platform_admin_permission_denies_unauthenticated():
    permission = PlatformAdminPermission()
    request = build_request(authenticated=False)
    assert permission.has_permission(request, None) is False


def test_platform_admin_permission_allows_admin_roles():
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    assert permission.has_permission(request, None) is True

    request = build_request(roles=["super_admin"])
    assert permission.has_permission(request, None) is True


def test_platform_viewer_permission_safe_methods_only():
    permission = PlatformViewerPermission()
    request = build_request(method="get", roles=["platform_viewer"])
    assert permission.has_permission(request, None) is True

    request = build_request(method="post", roles=["platform_viewer"])
    assert permission.has_permission(request, None) is False
