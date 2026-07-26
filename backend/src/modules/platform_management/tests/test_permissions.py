from types import SimpleNamespace

from rest_framework.test import APIRequestFactory

from src.modules.platform_management.permissions import PlatformAdminPermission, PlatformViewerPermission


def build_request(method="get", roles=None, authenticated=True):
    request = APIRequestFactory().generic(method, "/")
    request.user = SimpleNamespace(
        is_authenticated=authenticated,
        roles=roles or [],
        has_perm=lambda permission: permission in {"platform.settings:read", "platform.settings:update"},
    )
    return request


def test_platform_admin_permission_denies_unauthenticated():
    permission = PlatformAdminPermission()
    request = build_request(authenticated=False)
    assert permission.has_permission(request, None) is False


def test_platform_admin_permission_uses_declared_permissions():
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    view = SimpleNamespace(action="list", permission_resource="platform.settings")
    assert permission.has_permission(request, view) is True


def test_platform_admin_permission_uses_delete_permission():
    seen = []
    request = build_request(method="delete")
    request.user.has_perm = lambda value: seen.append(value) or True
    view = SimpleNamespace(action="destroy", permission_resource="platform.feature-flags")
    assert PlatformAdminPermission().has_permission(request, view) is True
    assert seen == ["platform.feature-flags:delete"]


def test_platform_viewer_permission_safe_methods_only():
    permission = PlatformViewerPermission()
    request = build_request(method="get")
    view = SimpleNamespace(permission_resource="platform.settings")
    assert permission.has_permission(request, view) is True

    request = build_request(method="post", roles=["platform_viewer"])
    assert permission.has_permission(request, view) is False
