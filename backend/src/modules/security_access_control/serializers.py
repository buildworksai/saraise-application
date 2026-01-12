"""
Security & Access Control Serializers.

DRF serializers for Security & Access Control models.
"""

from rest_framework import serializers

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


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for permissions (read-only)."""

    permission_string = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = [
            "id",
            "module",
            "object",
            "action",
            "name",
            "description",
            "permission_string",
            "created_at",
        ]
        read_only_fields = fields

    def get_permission_string(self, obj):
        """Return permission in module:object:action format."""
        return f"{obj.module}:{obj.object}:{obj.action}"


class RolePermissionSerializer(serializers.ModelSerializer):
    """Serializer for role-permission relationships."""

    permission = PermissionSerializer(read_only=True)
    permission_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = RolePermission
        fields = [
            "id",
            "role",
            "permission",
            "permission_id",
            "is_granted",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for roles."""

    permissions = PermissionSerializer(many=True, read_only=True, source="role_permissions.permission")
    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "tenant_id",
            "name",
            "code",
            "description",
            "role_type",
            "parent_role_id",
            "hierarchy_level",
            "is_active",
            "is_system",
            "permissions",
            "permission_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def get_permission_count(self, obj):
        """Get count of permissions assigned to this role."""
        return obj.role_permissions.filter(is_granted=True).count()

    def validate_code(self, value):
        """Validate role code format."""
        if not value or len(value) < 2:
            raise serializers.ValidationError("Code must be at least 2 characters")
        # Convert to snake_case
        return value.lower().replace(" ", "_").replace("-", "_")


class RoleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating roles."""

    tenant_id = serializers.UUIDField(read_only=True)  # Include in response

    class Meta:
        model = Role
        fields = [
            "id",
            "tenant_id",
            "name",
            "code",
            "description",
            "role_type",
            "parent_role_id",
            "hierarchy_level",
            "is_active",
            "is_system",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_code(self, value):
        """Validate role code format."""
        if not value or len(value) < 2:
            raise serializers.ValidationError("Code must be at least 2 characters")
        return value.lower().replace(" ", "_").replace("-", "_")

    def create(self, validated_data):
        """Create role with tenant_id from view context."""
        # Get tenant_id from view context (set in perform_create)
        tenant_id = self.context.get("tenant_id")
        if not tenant_id:
            raise serializers.ValidationError("tenant_id is required")
        validated_data["tenant_id"] = tenant_id
        return super().create(validated_data)


class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for user-role assignments."""

    role = RoleSerializer(read_only=True)
    role_id = serializers.UUIDField(write_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = UserRole
        fields = [
            "id",
            "user",
            "role",
            "role_id",
            "valid_from",
            "valid_until",
            "assigned_by",
            "reason",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_is_active(self, obj):
        """Check if role assignment is currently active."""
        return obj.is_active


class PermissionSetSerializer(serializers.ModelSerializer):
    """Serializer for permission sets."""

    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = PermissionSet
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "permission_ids",
            "permission_count",
            "default_duration_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def get_permission_count(self, obj):
        """Get count of permissions in this set."""
        return len(obj.permission_ids) if obj.permission_ids else 0


class PermissionSetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating permission sets."""

    tenant_id = serializers.UUIDField(read_only=True)  # Include in response

    class Meta:
        model = PermissionSet
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "permission_ids",
            "default_duration_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def create(self, validated_data):
        """Create permission set with tenant_id from view context."""
        tenant_id = self.context.get("tenant_id")
        if not tenant_id:
            raise serializers.ValidationError("tenant_id is required")
        validated_data["tenant_id"] = tenant_id
        return super().create(validated_data)


class UserPermissionSetSerializer(serializers.ModelSerializer):
    """Serializer for user permission set grants."""

    permission_set = PermissionSetSerializer(read_only=True)
    permission_set_id = serializers.UUIDField(write_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = UserPermissionSet
        fields = [
            "id",
            "user",
            "permission_set",
            "permission_set_id",
            "granted_at",
            "expires_at",
            "granted_by",
            "reason",
            "is_active",
        ]
        read_only_fields = ["id", "granted_at"]

    def get_is_active(self, obj):
        """Check if permission set grant is currently active."""
        return obj.is_active


class FieldSecuritySerializer(serializers.ModelSerializer):
    """Serializer for field-level security."""

    role = RoleSerializer(read_only=True)
    role_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = FieldSecurity
        fields = [
            "id",
            "tenant_id",
            "module",
            "object",
            "field",
            "role",
            "role_id",
            "visibility",
            "edit_control",
            "mask_pattern",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at"]


class FieldSecurityCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating field security rules."""

    class Meta:
        model = FieldSecurity
        fields = [
            "module",
            "object",
            "field",
            "role",
            "visibility",
            "edit_control",
            "mask_pattern",
        ]


class RowSecurityRuleSerializer(serializers.ModelSerializer):
    """Serializer for row-level security rules."""

    role = RoleSerializer(read_only=True)
    role_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = RowSecurityRule
        fields = [
            "id",
            "tenant_id",
            "module",
            "object",
            "role",
            "role_id",
            "rule_type",
            "filter_criteria",
            "priority",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at"]


class RowSecurityRuleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating row security rules."""

    class Meta:
        model = RowSecurityRule
        fields = [
            "module",
            "object",
            "role",
            "rule_type",
            "filter_criteria",
            "priority",
        ]


class SecurityProfileSerializer(serializers.ModelSerializer):
    """Serializer for security profiles."""

    class Meta:
        model = SecurityProfile
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "profile_type",
            "ip_whitelist",
            "ip_blacklist",
            "allowed_countries",
            "blocked_countries",
            "time_restrictions",
            "mfa_required",
            "allowed_mfa_methods",
            "password_policy",
            "session_timeout_minutes",
            "absolute_session_timeout_hours",
            "max_concurrent_sessions",
            "download_allowed",
            "print_allowed",
            "copy_paste_allowed",
            "mobile_access_allowed",
            "login_notification",
            "access_notification",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class SecurityProfileCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating security profiles."""

    tenant_id = serializers.UUIDField(read_only=True)  # Include in response

    class Meta:
        model = SecurityProfile
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "profile_type",
            "ip_whitelist",
            "ip_blacklist",
            "allowed_countries",
            "blocked_countries",
            "time_restrictions",
            "mfa_required",
            "allowed_mfa_methods",
            "password_policy",
            "session_timeout_minutes",
            "absolute_session_timeout_hours",
            "max_concurrent_sessions",
            "download_allowed",
            "print_allowed",
            "copy_paste_allowed",
            "mobile_access_allowed",
            "login_notification",
            "access_notification",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def create(self, validated_data):
        """Create security profile with tenant_id from view context."""
        tenant_id = self.context.get("tenant_id")
        if not tenant_id:
            raise serializers.ValidationError("tenant_id is required")
        validated_data["tenant_id"] = tenant_id
        return super().create(validated_data)


class SecurityAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for security audit logs (read-only)."""

    class Meta:
        model = SecurityAuditLog
        fields = [
            "id",
            "tenant_id",
            "action",
            "actor_type",
            "actor_id",
            "resource_type",
            "resource_id",
            "decision",
            "reason_codes",
            "timestamp",
            "details",
            "ip_address",
            "user_agent",
        ]
        read_only_fields = fields  # All fields are read-only
