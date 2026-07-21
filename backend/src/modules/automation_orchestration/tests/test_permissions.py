"""Security metadata and authentication contracts."""

from rest_framework.authentication import SessionAuthentication

from ..api import GovernedTenantViewSet
from ..permissions import PERMISSIONS


def test_permission_catalog_is_exact_and_contains_no_generic_resource_permissions() -> None:
    assert len(PERMISSIONS) == 10
    assert len(set(PERMISSIONS)) == len(PERMISSIONS)
    assert all(permission.startswith("automation_orchestration.") for permission in PERMISSIONS)
    assert all("resource:" not in permission for permission in PERMISSIONS)


def test_api_uses_standard_csrf_enforcing_session_authentication() -> None:
    assert len(GovernedTenantViewSet.authentication_classes) == 1
    assert issubclass(GovernedTenantViewSet.authentication_classes[0], SessionAuthentication)
    assert all(
        authentication.__name__ != "RelaxedCsrfSessionAuthentication"
        for authentication in GovernedTenantViewSet.authentication_classes
    )
