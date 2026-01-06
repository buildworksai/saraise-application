"""
Security & Access Control Services.

Business logic for Security & Access Control operations.
"""

from typing import Optional, Union, List, Dict, Any
from django.utils import timezone
from django.db import models
from datetime import timedelta
import uuid

from .models import (
    Role,
    Permission,
    RolePermission,
    UserRole,
    PermissionSet,
    UserPermissionSet,
    FieldSecurity,
    RowSecurityRule,
    SecurityProfile,
    SecurityAuditLog,
)


class SecurityAccessControlService:
    """Business logic for Security & Access Control operations."""

    @staticmethod
    def create_role(
        name: str,
        code: str,
        tenant_id: Union[str, uuid.UUID],
        description: str = "",
        role_type: str = Role.RoleType.CUSTOM,
        parent_role_id: Optional[Union[str, uuid.UUID]] = None,
        is_active: bool = True,
        created_by: Optional[Union[str, uuid.UUID]] = None,
    ) -> Role:
        """
        Create a new role.
        """
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        if parent_role_id and isinstance(parent_role_id, str):
            parent_role_id = uuid.UUID(parent_role_id)
        if created_by and isinstance(created_by, str):
            created_by = uuid.UUID(created_by)

        role = Role.objects.create(
            name=name,
            code=code,
            tenant_id=tenant_id,
            description=description,
            role_type=role_type,
            parent_role_id=parent_role_id,
            is_active=is_active,
            created_by=created_by,
        )
        return role

    @staticmethod
    def assign_permission_to_role(
        role_id: Union[str, uuid.UUID],
        permission_id: Union[str, uuid.UUID],
        is_granted: bool = True,
    ) -> RolePermission:
        """
        Assign a permission to a role.
        """
        if isinstance(role_id, str):
            role_id = uuid.UUID(role_id)
        if isinstance(permission_id, str):
            permission_id = uuid.UUID(permission_id)

        role = Role.objects.get(id=role_id)
        permission = Permission.objects.get(id=permission_id)

        role_permission, created = RolePermission.objects.get_or_create(
            role=role, permission=permission, defaults={"is_granted": is_granted}
        )

        if not created:
            role_permission.is_granted = is_granted
            role_permission.save()

        return role_permission

    @staticmethod
    def assign_role_to_user(
        user_id: Union[str, uuid.UUID],
        role_id: Union[str, uuid.UUID],
        valid_until: Optional[timezone.datetime] = None,
        assigned_by: Optional[Union[str, uuid.UUID]] = None,
        reason: str = "",
    ) -> UserRole:
        """
        Assign a role to a user.
        """
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        if isinstance(role_id, str):
            role_id = uuid.UUID(role_id)
        if assigned_by and isinstance(assigned_by, str):
            assigned_by = uuid.UUID(assigned_by)

        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        role = Role.objects.get(id=role_id)

        user_role, created = UserRole.objects.get_or_create(
            user=user,
            role=role,
            defaults={
                "valid_until": valid_until,
                "assigned_by": assigned_by,
                "reason": reason,
            },
        )

        if not created:
            user_role.valid_until = valid_until
            user_role.assigned_by = assigned_by
            user_role.reason = reason
            user_role.save()

        return user_role

    @staticmethod
    def create_permission_set(
        name: str,
        tenant_id: Union[str, uuid.UUID],
        permission_ids: List[Union[str, uuid.UUID]],
        description: str = "",
        default_duration_days: Optional[int] = None,
        created_by: Optional[Union[str, uuid.UUID]] = None,
    ) -> PermissionSet:
        """
        Create a permission set.
        """
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        if created_by and isinstance(created_by, str):
            created_by = uuid.UUID(created_by)

        # Convert permission IDs to strings for JSON storage
        permission_ids_str = [
            str(pid) if isinstance(pid, uuid.UUID) else pid for pid in permission_ids
        ]

        permission_set = PermissionSet.objects.create(
            name=name,
            tenant_id=tenant_id,
            description=description,
            permission_ids=permission_ids_str,
            default_duration_days=default_duration_days,
            created_by=created_by,
        )
        return permission_set

    @staticmethod
    def grant_permission_set_to_user(
        user_id: Union[str, uuid.UUID],
        permission_set_id: Union[str, uuid.UUID],
        expires_at: Optional[timezone.datetime] = None,
        duration_days: Optional[int] = None,
        granted_by: Optional[Union[str, uuid.UUID]] = None,
        reason: str = "",
    ) -> UserPermissionSet:
        """
        Grant a permission set to a user.
        """
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        if isinstance(permission_set_id, str):
            permission_set_id = uuid.UUID(permission_set_id)
        if granted_by and isinstance(granted_by, str):
            granted_by = uuid.UUID(granted_by)

        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        permission_set = PermissionSet.objects.get(id=permission_set_id)

        # Calculate expires_at if duration_days provided
        if expires_at is None and duration_days:
            expires_at = timezone.now() + timedelta(days=duration_days)
        elif expires_at is None:
            # Use permission set's default duration
            if permission_set.default_duration_days:
                expires_at = timezone.now() + timedelta(
                    days=permission_set.default_duration_days
                )
            else:
                # Default to 30 days if no duration specified
                expires_at = timezone.now() + timedelta(days=30)

        user_permission_set = UserPermissionSet.objects.create(
            user=user,
            permission_set=permission_set,
            expires_at=expires_at,
            granted_by=granted_by,
            reason=reason,
        )
        return user_permission_set

    @staticmethod
    def create_field_security(
        module: str,
        object_name: str,
        field: str,
        role_id: Union[str, uuid.UUID],
        tenant_id: Union[str, uuid.UUID],
        visibility: str = FieldSecurity.Visibility.VISIBLE,
        edit_control: str = FieldSecurity.EditControl.EDITABLE,
        mask_pattern: str = "",
    ) -> FieldSecurity:
        """
        Create a field-level security rule.
        """
        if isinstance(role_id, str):
            role_id = uuid.UUID(role_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        role = Role.objects.get(id=role_id)

        field_security, created = FieldSecurity.objects.get_or_create(
            tenant_id=tenant_id,
            module=module,
            object=object_name,
            field=field,
            role=role,
            defaults={
                "visibility": visibility,
                "edit_control": edit_control,
                "mask_pattern": mask_pattern,
            },
        )

        if not created:
            field_security.visibility = visibility
            field_security.edit_control = edit_control
            field_security.mask_pattern = mask_pattern
            field_security.save()

        return field_security

    @staticmethod
    def create_row_security_rule(
        module: str,
        object_name: str,
        role_id: Union[str, uuid.UUID],
        tenant_id: Union[str, uuid.UUID],
        rule_type: str = RowSecurityRule.RuleType.OWNERSHIP,
        filter_criteria: str = "",
        priority: int = 0,
    ) -> RowSecurityRule:
        """
        Create a row-level security rule.
        """
        if isinstance(role_id, str):
            role_id = uuid.UUID(role_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        role = Role.objects.get(id=role_id)

        row_security_rule = RowSecurityRule.objects.create(
            tenant_id=tenant_id,
            module=module,
            object=object_name,
            role=role,
            rule_type=rule_type,
            filter_criteria=filter_criteria,
            priority=priority,
        )
        return row_security_rule

    @staticmethod
    def create_security_profile(
        name: str,
        tenant_id: Union[str, uuid.UUID],
        profile_type: str = SecurityProfile.ProfileType.STANDARD,
        description: str = "",
        created_by: Optional[Union[str, uuid.UUID]] = None,
        **kwargs,
    ) -> SecurityProfile:
        """
        Create a security profile.
        """
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        if created_by and isinstance(created_by, str):
            created_by = uuid.UUID(created_by)

        security_profile = SecurityProfile.objects.create(
            name=name,
            tenant_id=tenant_id,
            description=description,
            profile_type=profile_type,
            created_by=created_by,
            **kwargs,
        )
        return security_profile

    @staticmethod
    def log_audit_event(
        action: str,
        actor_id: Union[str, uuid.UUID],
        resource_type: str,
        resource_id: Optional[Union[str, uuid.UUID]] = None,
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        decision: Optional[str] = None,
        reason_codes: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> SecurityAuditLog:
        """
        Log an immutable audit event.
        """
        if isinstance(actor_id, str):
            actor_id = uuid.UUID(actor_id)
        if resource_id and isinstance(resource_id, str):
            resource_id = uuid.UUID(resource_id)
        if tenant_id and isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        return SecurityAuditLog.objects.create(
            action=action,
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            decision=decision,
            reason_codes=reason_codes or [],
            details=details or {},
            ip_address=ip_address,
        )

    @staticmethod
    def get_user_effective_permissions(
        user_id: Union[str, uuid.UUID], tenant_id: Union[str, uuid.UUID]
    ) -> List[str]:
        """
        Get effective permissions for a user (from all assigned roles and permission sets).

        Returns list of permission strings in module:object:action format.
        """
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)

        # Get permissions from roles
        active_user_roles = UserRole.objects.filter(
            user=user, role__tenant_id=tenant_id, role__is_active=True
        ).filter(
            models.Q(valid_until__isnull=True)
            | models.Q(valid_until__gt=timezone.now())
        )

        permission_ids = set()
        for user_role in active_user_roles:
            role_permissions = RolePermission.objects.filter(
                role=user_role.role, is_granted=True
            )
            for rp in role_permissions:
                permission_ids.add(rp.permission.id)

        # Get permissions from active permission sets
        active_permission_sets = UserPermissionSet.objects.filter(
            user=user, permission_set__tenant_id=tenant_id
        ).filter(granted_at__lte=timezone.now(), expires_at__gt=timezone.now())

        for ups in active_permission_sets:
            for perm_id_str in ups.permission_set.permission_ids:
                try:
                    permission_ids.add(uuid.UUID(perm_id_str))
                except (ValueError, TypeError):
                    continue

        # Convert permission IDs to permission strings
        permissions = Permission.objects.filter(id__in=permission_ids)
        return [f"{p.module}:{p.object}:{p.action}" for p in permissions]
