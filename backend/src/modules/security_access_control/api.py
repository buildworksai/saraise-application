"""
Security & Access Control API ViewSets.

DRF ViewSets with tenant isolation and Policy Engine authorization.

CRITICAL: This module manages RBAC data models.
Policy Engine evaluates permissions at runtime.
"""

import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id

from .models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    UserPermissionSet,
    UserRole,
)
from .serializers import (
    FieldSecurityCreateSerializer,
    FieldSecuritySerializer,
    PermissionSerializer,
    PermissionSetCreateSerializer,
    PermissionSetSerializer,
    RoleCreateSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    RowSecurityRuleCreateSerializer,
    RowSecurityRuleSerializer,
    SecurityAuditLogSerializer,
    SecurityProfileCreateSerializer,
    SecurityProfileSerializer,
    UserPermissionSetSerializer,
    UserRoleSerializer,
)
from .services import SecurityAccessControlService


class RoleViewSet(viewsets.ModelViewSet):
    """
    API endpoints for roles.

    Architecture Compliance:
    - ✅ Tenant filtering in get_queryset
    - ✅ tenant_id set on create
    - ✅ Audit logging on mutations
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return RoleCreateSerializer
        return RoleSerializer

    def get_queryset(self):
        """Filter roles by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Role.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = Role.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return Role.objects.none()

        # Filter by role_type if provided
        role_type = self.request.query_params.get("role_type", None)
        if role_type:
            queryset = queryset.filter(role_type=role_type)

        # Filter by is_active if provided
        is_active = self.request.query_params.get("is_active", None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset.order_by("-created_at")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = Role.objects.get(**{self.lookup_field: lookup_value})
        except Role.DoesNotExist:
            raise NotFound("Not found.")

        # CRITICAL: Explicit tenant isolation check
        if obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        if not tenant_id:
            raise ValidationError({"error": "User must belong to a tenant"})

        # Pass tenant_id to serializer context so create() can use it
        serializer.context["tenant_id"] = tenant_id

        instance = serializer.save(created_by=self.request.user.id)

        # Audit logging
        SecurityAccessControlService.log_audit_event(
            action="security.role.created",
            actor_id=self.request.user.id,
            resource_type="Role",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"name": instance.name, "code": instance.code},
        )

    def perform_update(self, serializer):
        """Audit on update."""
        instance = serializer.save(updated_by=self.request.user.id)
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        SecurityAccessControlService.log_audit_event(
            action="security.role.updated",
            actor_id=self.request.user.id,
            resource_type="Role",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"name": instance.name},
        )

    def perform_destroy(self, instance):
        """Prevent deletion of system roles and audit."""
        if instance.is_system:
            raise ValidationError({"error": "System roles cannot be deleted."})

        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        SecurityAccessControlService.log_audit_event(
            action="security.role.deleted",
            actor_id=self.request.user.id,
            resource_type="Role",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"name": instance.name},
        )

        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def assign_permission(self, request, pk=None):
        """Assign a permission to this role."""
        role = self.get_object()
        permission_id = request.data.get("permission_id")
        is_granted = request.data.get("is_granted", True)

        if not permission_id:
            return Response(
                {"error": "permission_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            permission = Permission.objects.get(id=permission_id)
        except Permission.DoesNotExist:
            return Response({"error": "Permission not found"}, status=status.HTTP_404_NOT_FOUND)

        role_permission, created = RolePermission.objects.get_or_create(
            role=role, permission=permission, defaults={"is_granted": is_granted}
        )

        if not created:
            role_permission.is_granted = is_granted
            role_permission.save()

        return Response(RolePermissionSerializer(role_permission).data)

    @action(detail=True, methods=["post"])
    def revoke_permission(self, request, pk=None):
        """Revoke a permission from this role."""
        role = self.get_object()
        permission_id = request.data.get("permission_id")

        if not permission_id:
            return Response(
                {"error": "permission_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        RolePermission.objects.filter(role=role, permission_id=permission_id).delete()

        return Response({"status": "Permission revoked"})


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for permissions (read-only).

    CRITICAL: Permissions are platform-level (no tenant_id).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()

    def get_queryset(self):
        """Filter permissions by module if provided."""
        queryset = Permission.objects.all()

        module = self.request.query_params.get("module", None)
        if module:
            queryset = queryset.filter(module=module)

        return queryset.order_by("module", "object", "action")


class UserRoleViewSet(viewsets.ModelViewSet):
    """API endpoints for user-role assignments."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserRoleSerializer

    def get_queryset(self):
        """Filter user roles by tenant_id via role."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return UserRole.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = UserRole.objects.filter(role__tenant_id=tenant_id)
        except (ValueError, TypeError):
            return UserRole.objects.none()

        # Filter by user_id if provided
        user_id = self.request.query_params.get("user_id", None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by role_id if provided
        role_id = self.request.query_params.get("role_id", None)
        if role_id:
            queryset = queryset.filter(role_id=role_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set assigned_by and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        instance = serializer.save(assigned_by=self.request.user.id)

        SecurityAccessControlService.log_audit_event(
            action="security.user_role.assigned",
            actor_id=self.request.user.id,
            resource_type="UserRole",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={
                "user_id": str(instance.user.id),
                "role_id": str(instance.role.id),
                "role_name": instance.role.name,
            },
        )


class PermissionSetViewSet(viewsets.ModelViewSet):
    """API endpoints for permission sets."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PermissionSetCreateSerializer
        return PermissionSetSerializer

    def get_queryset(self):
        """Filter permission sets by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return PermissionSet.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = PermissionSet.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return PermissionSet.objects.none()

        return queryset.order_by("-created_at")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = PermissionSet.objects.get(**{self.lookup_field: lookup_value})
        except PermissionSet.DoesNotExist:
            raise NotFound("Not found.")

        if obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        if not tenant_id:
            raise ValidationError({"error": "User must belong to a tenant"})

        # Pass tenant_id to serializer context so create() can use it
        serializer.context["tenant_id"] = tenant_id

        instance = serializer.save(created_by=self.request.user.id)

        SecurityAccessControlService.log_audit_event(
            action="security.permission_set.created",
            actor_id=self.request.user.id,
            resource_type="PermissionSet",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"name": instance.name},
        )


class UserPermissionSetViewSet(viewsets.ModelViewSet):
    """API endpoints for user permission set grants."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserPermissionSetSerializer

    def get_queryset(self):
        """Filter user permission sets by tenant_id via permission_set."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return UserPermissionSet.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = UserPermissionSet.objects.filter(permission_set__tenant_id=tenant_id)
        except (ValueError, TypeError):
            return UserPermissionSet.objects.none()

        # Filter by user_id if provided
        user_id = self.request.query_params.get("user_id", None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset.order_by("-granted_at")

    def perform_create(self, serializer):
        """Set granted_by and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        instance = serializer.save(granted_by=self.request.user.id)

        SecurityAccessControlService.log_audit_event(
            action="security.user_permission_set.granted",
            actor_id=self.request.user.id,
            resource_type="UserPermissionSet",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={
                "user_id": str(instance.user.id),
                "permission_set_id": str(instance.permission_set.id),
                "expires_at": instance.expires_at.isoformat(),
            },
        )


class FieldSecurityViewSet(viewsets.ModelViewSet):
    """API endpoints for field-level security."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return FieldSecurityCreateSerializer
        return FieldSecuritySerializer

    def get_queryset(self):
        """Filter field security by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return FieldSecurity.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = FieldSecurity.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return FieldSecurity.objects.none()

        # Filter by module/object if provided
        module = self.request.query_params.get("module", None)
        if module:
            queryset = queryset.filter(module=module)

        object_name = self.request.query_params.get("object", None)
        if object_name:
            queryset = queryset.filter(object=object_name)

        return queryset.order_by("module", "object", "field")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = FieldSecurity.objects.get(**{self.lookup_field: lookup_value})
        except FieldSecurity.DoesNotExist:
            raise NotFound("Not found.")

        if obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        instance = serializer.save(tenant_id=tenant_id)

        SecurityAccessControlService.log_audit_event(
            action="security.field_security.created",
            actor_id=self.request.user.id,
            resource_type="FieldSecurity",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={
                "module": instance.module,
                "object": instance.object,
                "field": instance.field,
            },
        )


class RowSecurityRuleViewSet(viewsets.ModelViewSet):
    """API endpoints for row-level security rules."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return RowSecurityRuleCreateSerializer
        return RowSecurityRuleSerializer

    def get_queryset(self):
        """Filter row security rules by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return RowSecurityRule.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = RowSecurityRule.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return RowSecurityRule.objects.none()

        # Filter by module/object if provided
        module = self.request.query_params.get("module", None)
        if module:
            queryset = queryset.filter(module=module)

        object_name = self.request.query_params.get("object", None)
        if object_name:
            queryset = queryset.filter(object=object_name)

        return queryset.order_by("-priority", "module", "object")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = RowSecurityRule.objects.get(**{self.lookup_field: lookup_value})
        except RowSecurityRule.DoesNotExist:
            raise NotFound("Not found.")

        if obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        instance = serializer.save(tenant_id=tenant_id)

        SecurityAccessControlService.log_audit_event(
            action="security.row_security_rule.created",
            actor_id=self.request.user.id,
            resource_type="RowSecurityRule",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={
                "module": instance.module,
                "object": instance.object,
                "rule_type": instance.rule_type,
            },
        )


class SecurityProfileViewSet(viewsets.ModelViewSet):
    """API endpoints for security profiles."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return SecurityProfileCreateSerializer
        return SecurityProfileSerializer

    def get_queryset(self):
        """Filter security profiles by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return SecurityProfile.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = SecurityProfile.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return SecurityProfile.objects.none()

        # Filter by profile_type if provided
        profile_type = self.request.query_params.get("profile_type", None)
        if profile_type:
            queryset = queryset.filter(profile_type=profile_type)

        return queryset.order_by("-created_at")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = SecurityProfile.objects.get(**{self.lookup_field: lookup_value})
        except SecurityProfile.DoesNotExist:
            raise NotFound("Not found.")

        if obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        if not tenant_id:
            raise ValidationError({"error": "User must belong to a tenant"})

        # Pass tenant_id to serializer context so create() can use it
        serializer.context["tenant_id"] = tenant_id

        instance = serializer.save(created_by=self.request.user.id)

        SecurityAccessControlService.log_audit_event(
            action="security.security_profile.created",
            actor_id=self.request.user.id,
            resource_type="SecurityProfile",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"name": instance.name, "profile_type": instance.profile_type},
        )


class SecurityAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for security audit logs (read-only).

    CRITICAL: No create/update/delete allowed.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SecurityAuditLogSerializer

    def get_queryset(self):
        """Filter audit logs by tenant_id."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return SecurityAuditLog.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            queryset = SecurityAuditLog.objects.filter(tenant_id=tenant_id)
        except (ValueError, TypeError):
            return SecurityAuditLog.objects.none()

        # Filter by action if provided
        action_filter = self.request.query_params.get("action", None)
        if action_filter:
            queryset = queryset.filter(action__icontains=action_filter)

        # Filter by decision if provided
        decision = self.request.query_params.get("decision", None)
        if decision:
            queryset = queryset.filter(decision=decision)

        return queryset.order_by("-timestamp")

    def get_object(self):
        """Override to ensure tenant isolation on detail view."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        try:
            obj = SecurityAuditLog.objects.get(**{self.lookup_field: lookup_value})
        except SecurityAuditLog.DoesNotExist:
            raise NotFound("Not found.")

        if obj.tenant_id is not None and obj.tenant_id != tenant_id:
            raise NotFound("Not found.")

        return obj
