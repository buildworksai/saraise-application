"""
Security & Access Control URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    RoleViewSet,
    PermissionViewSet,
    UserRoleViewSet,
    PermissionSetViewSet,
    UserPermissionSetViewSet,
    FieldSecurityViewSet,
    RowSecurityRuleViewSet,
    SecurityProfileViewSet,
    SecurityAuditLogViewSet,
)
from .health import check_security_module_health

router = DefaultRouter()
router.register(r"roles", RoleViewSet, basename="security-roles")
router.register(r"permissions", PermissionViewSet, basename="security-permissions")
router.register(r"user-roles", UserRoleViewSet, basename="security-user-roles")
router.register(
    r"permission-sets", PermissionSetViewSet, basename="security-permission-sets"
)
router.register(
    r"user-permission-sets",
    UserPermissionSetViewSet,
    basename="security-user-permission-sets",
)
router.register(
    r"field-security", FieldSecurityViewSet, basename="security-field-security"
)
router.register(
    r"row-security-rules",
    RowSecurityRuleViewSet,
    basename="security-row-security-rules",
)
router.register(
    r"security-profiles", SecurityProfileViewSet, basename="security-profiles"
)
router.register(r"audit-logs", SecurityAuditLogViewSet, basename="security-audit-logs")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "health/",
        check_security_module_health,
        name="security_access_control_health_check",
    ),
]
