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


def test_platform_admin_permission_denies_missing_resource():
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    view = SimpleNamespace(action="list", permission_resource=None)
    assert permission.has_permission(request, view) is False


def test_platform_admin_permission_denies_unknown_action():
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    view = SimpleNamespace(action="unmapped-action", permission_resource="platform.settings")
    assert permission.has_permission(request, view) is False


def test_platform_admin_permission_denies_disallowed_permission_combination():
    """platform.audit only ever grants :read; :create is not in ALLOWED_PERMISSIONS."""
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    view = SimpleNamespace(action="create", permission_resource="platform.audit")
    assert permission.has_permission(request, view) is False
    assert not hasattr(view, "required_permissions")


def test_platform_admin_permission_denies_when_policy_check_fails():
    permission = PlatformAdminPermission()
    request = build_request(roles=[])
    request.user.has_perm = lambda value: False
    view = SimpleNamespace(action="list", permission_resource="platform.settings")
    assert permission.has_permission(request, view) is False


def test_platform_admin_permission_sets_required_permissions_before_delegating():
    permission = PlatformAdminPermission()
    request = build_request(roles=["platform_admin"])
    view = SimpleNamespace(action="retrieve", permission_resource="platform.feature-flags")
    assert permission.has_permission(request, view) is True
    assert view.required_permissions == ["platform.feature-flags:read"]


def test_platform_admin_actions_mapping_is_exact():
    assert PlatformAdminPermission.ACTIONS == {
        "create": "create",
        "destroy": "delete",
        "list": "read",
        "retrieve": "read",
        "update": "update",
        "partial_update": "update",
        "current": "read",
        "save": "create",
        "summary": "read",
        "toggle": "update",
    }


def test_platform_admin_allowed_permissions_is_exact():
    assert PlatformAdminPermission.ALLOWED_PERMISSIONS == {
        "platform.settings:create",
        "platform.settings:read",
        "platform.settings:update",
        "platform.settings:delete",
        "platform.feature-flags:create",
        "platform.feature-flags:read",
        "platform.feature-flags:update",
        "platform.feature-flags:delete",
        "platform.health:read",
        "platform.audit:read",
        "platform.metrics:create",
        "platform.metrics:read",
        "platform.metrics:update",
        "platform.metrics:delete",
    }


def test_platform_viewer_permission_denies_missing_resource():
    permission = PlatformViewerPermission()
    request = build_request(method="get")
    view = SimpleNamespace(permission_resource=None)
    assert permission.has_permission(request, view) is False


def test_platform_viewer_permission_denies_disallowed_resource():
    """No 'platform.unknown:read' entry exists in ALLOWED_PERMISSIONS."""
    permission = PlatformViewerPermission()
    request = build_request(method="get")
    view = SimpleNamespace(permission_resource="platform.unknown")
    assert permission.has_permission(request, view) is False
    assert not hasattr(view, "required_permissions")


def test_platform_viewer_permission_denies_when_policy_check_fails():
    permission = PlatformViewerPermission()
    request = build_request(method="get", roles=[])
    request.user.has_perm = lambda value: False
    view = SimpleNamespace(permission_resource="platform.settings")
    assert permission.has_permission(request, view) is False


def test_platform_viewer_permission_sets_required_permissions_before_delegating():
    permission = PlatformViewerPermission()
    request = build_request(method="get")
    view = SimpleNamespace(permission_resource="platform.settings")
    assert permission.has_permission(request, view) is True
    assert view.required_permissions == ["platform.settings:read"]
