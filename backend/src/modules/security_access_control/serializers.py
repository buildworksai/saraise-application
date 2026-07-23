"""Operation-specific serializers for the governed security API v2."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityConfiguration,
    SecurityConfigurationVersion,
    SecurityProfile,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)
from .predicates import validate_predicate
from .validators import redact_sensitive

UUID = serializers.UUIDField


class SecurityConfigurationSerializer(serializers.ModelSerializer[SecurityConfiguration]):
    class Meta:
        model = SecurityConfiguration
        fields = (
            "id",
            "environment",
            "version",
            "document",
            "rollout",
            "updated_by",
            "correlation_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SecurityConfigurationVersionSerializer(serializers.ModelSerializer[SecurityConfigurationVersion]):
    class Meta:
        model = SecurityConfigurationVersion
        fields = (
            "id",
            "version",
            "environment",
            "previous_document",
            "current_document",
            "previous_rollout",
            "current_rollout",
            "actor_id",
            "correlation_id",
            "reason",
            "change_kind",
            "created_at",
        )
        read_only_fields = fields


class SecurityConfigurationWriteSerializer(serializers.Serializer[dict[str, Any]]):
    environment = serializers.ChoiceField(choices=("development", "test", "staging", "production"))
    document = serializers.DictField()
    rollout = serializers.DictField(required=False)
    reason = serializers.CharField(allow_blank=False, max_length=2000)


class SecurityConfigurationPreviewSerializer(serializers.Serializer[dict[str, Any]]):
    document = serializers.DictField()
    rollout = serializers.DictField(required=False)


class SecurityConfigurationRollbackSerializer(serializers.Serializer[dict[str, Any]]):
    reason = serializers.CharField(allow_blank=False, max_length=2000)


class SecurityConfigurationRolloutSerializer(serializers.Serializer[dict[str, Any]]):
    rollout = serializers.DictField()
    reason = serializers.CharField(allow_blank=False, max_length=2000)


class PermissionSerializer(serializers.ModelSerializer[Permission]):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Permission
        fields = ("id", "module", "resource", "action", "code", "name", "description", "risk_level", "created_at")
        read_only_fields = fields


PermissionListSerializer = PermissionSerializer
PermissionDetailSerializer = PermissionSerializer


class RolePermissionSerializer(serializers.ModelSerializer[RolePermission]):
    permission = PermissionSerializer(read_only=True)
    role_id = serializers.UUIDField(read_only=True)
    permission_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RolePermission
        fields = (
            "id",
            "tenant_id",
            "role_id",
            "permission_id",
            "permission",
            "is_granted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        read_only_fields = fields


class RoleListSerializer(serializers.ModelSerializer[Role]):
    parent_role_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "name",
            "code",
            "description",
            "role_type",
            "parent_role_id",
            "hierarchy_level",
            "is_active",
            "is_system",
            "is_deleted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
        )
        read_only_fields = fields


class RoleDetailSerializer(RoleListSerializer):
    permissions = RolePermissionSerializer(source="role_permissions", many=True, read_only=True)

    class Meta(RoleListSerializer.Meta):
        fields = RoleListSerializer.Meta.fields + ("permissions",)


class RoleCreateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=255)
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{0,99}$")
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    role_type = serializers.ChoiceField(choices=Role.RoleType.choices, default=Role.RoleType.CUSTOM)
    parent_role_id = serializers.UUIDField(required=False, allow_null=True)


class RoleUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=255, required=False)
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{0,99}$", required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    role_type = serializers.ChoiceField(choices=Role.RoleType.choices, required=False)
    parent_role_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class SetRolePermissionSerializer(serializers.Serializer[dict[str, Any]]):
    permission_id = serializers.UUIDField()
    is_granted = serializers.BooleanField()


class UserRoleListSerializer(serializers.ModelSerializer[UserRole]):
    is_active = serializers.BooleanField(read_only=True)
    role = RoleListSerializer(read_only=True)
    role_id = serializers.UUIDField(read_only=True)
    user_id = serializers.CharField(read_only=True)

    class Meta:
        model = UserRole
        fields = (
            "id",
            "tenant_id",
            "user_id",
            "role_id",
            "role",
            "valid_from",
            "valid_until",
            "reason",
            "revoked_at",
            "revocation_reason",
            "assigned_by",
            "revoked_by",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserRoleDetailSerializer(UserRoleListSerializer):
    pass


class UserRoleCreateSerializer(serializers.Serializer[dict[str, Any]]):
    user_id = serializers.CharField(max_length=128)
    role_id = serializers.UUIDField()
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=2000, allow_blank=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("valid_until") and attrs.get("valid_from") and attrs["valid_until"] <= attrs["valid_from"]:
            raise serializers.ValidationError({"valid_until": "Must be later than valid_from."})
        return attrs


class UserRoleUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, max_length=2000, allow_blank=False)


class PermissionSetListSerializer(serializers.ModelSerializer[PermissionSet]):
    permission_count = serializers.SerializerMethodField()
    permission_ids = serializers.SerializerMethodField()

    class Meta:
        model = PermissionSet
        fields = (
            "id",
            "tenant_id",
            "name",
            "description",
            "default_duration_days",
            "is_active",
            "permission_count",
            "permission_ids",
            "is_deleted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
        )
        read_only_fields = fields

    def get_permission_count(self, obj: PermissionSet) -> int:
        return obj.memberships.filter(removed_at__isnull=True).count()

    def get_permission_ids(self, obj: PermissionSet) -> list[str]:
        return [
            str(value)
            for value in obj.memberships.filter(removed_at__isnull=True).values_list("permission_id", flat=True)
        ]


class PermissionSetDetailSerializer(PermissionSetListSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta(PermissionSetListSerializer.Meta):
        fields = PermissionSetListSerializer.Meta.fields + ("permissions",)

    def get_permissions(self, obj: PermissionSet) -> list[dict[str, Any]]:
        rows = [
            membership.permission
            for membership in obj.memberships.filter(removed_at__isnull=True).select_related("permission")
        ]
        return PermissionSerializer(rows, many=True).data


class PermissionSetCreateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    default_duration_days = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    permission_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True, max_length=1000
    )


class PermissionSetUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    default_duration_days = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class ReplacePermissionSetPermissionsSerializer(serializers.Serializer[dict[str, Any]]):
    permission_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True, max_length=1000)


class UserPermissionSetListSerializer(serializers.ModelSerializer[UserPermissionSet]):
    is_active = serializers.BooleanField(read_only=True)
    permission_set = PermissionSetListSerializer(read_only=True)
    permission_set_id = serializers.UUIDField(read_only=True)
    user_id = serializers.CharField(read_only=True)

    class Meta:
        model = UserPermissionSet
        fields = (
            "id",
            "tenant_id",
            "user_id",
            "permission_set_id",
            "permission_set",
            "granted_at",
            "expires_at",
            "reason",
            "revoked_at",
            "revocation_reason",
            "granted_by",
            "revoked_by",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserPermissionSetDetailSerializer(UserPermissionSetListSerializer):
    pass


class UserPermissionSetCreateSerializer(serializers.Serializer[dict[str, Any]]):
    user_id = serializers.CharField(max_length=128)
    permission_set_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField(required=False)
    duration_days = serializers.IntegerField(required=False)
    reason = serializers.CharField(max_length=2000, allow_blank=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "expires_at" in attrs and "duration_days" in attrs:
            raise serializers.ValidationError("Provide expires_at or duration_days, not both.")
        return attrs


class UserPermissionSetUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    expires_at = serializers.DateTimeField()
    reason = serializers.CharField(required=False, max_length=2000, allow_blank=False)


class FieldSecurityListSerializer(serializers.ModelSerializer[FieldSecurity]):
    role = RoleListSerializer(read_only=True)
    role_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FieldSecurity
        fields = (
            "id",
            "tenant_id",
            "module",
            "resource",
            "field",
            "role",
            "role_id",
            "visibility",
            "edit_control",
            "mask_pattern",
            "is_active",
            "is_deleted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
        )
        read_only_fields = fields


class FieldSecurityDetailSerializer(FieldSecurityListSerializer):
    pass


class FieldSecurityCreateSerializer(serializers.Serializer[dict[str, Any]]):
    module = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,99}$")
    resource = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,99}$")
    field = serializers.RegexField(r"^[a-z][a-z0-9_]{0,99}$")
    role_id = serializers.UUIDField()
    visibility = serializers.ChoiceField(choices=FieldSecurity.Visibility.choices, required=False)
    edit_control = serializers.ChoiceField(choices=FieldSecurity.EditControl.choices, required=False)
    mask_pattern = serializers.CharField(required=False, allow_blank=True, max_length=100)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("visibility") == "masked" and not attrs.get("mask_pattern"):
            raise serializers.ValidationError({"mask_pattern": "Required for masked visibility."})
        if attrs.get("visibility") != "masked" and attrs.get("mask_pattern"):
            raise serializers.ValidationError({"mask_pattern": "Only valid for masked visibility."})
        return attrs


class FieldSecurityUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    visibility = serializers.ChoiceField(choices=FieldSecurity.Visibility.choices, required=False)
    edit_control = serializers.ChoiceField(choices=FieldSecurity.EditControl.choices, required=False)
    mask_pattern = serializers.CharField(required=False, allow_blank=True, max_length=100)
    is_active = serializers.BooleanField(required=False)


class PredicateSerializer(serializers.DictField):
    def to_internal_value(self, data: Any) -> dict[str, Any]:
        value = super().to_internal_value(data)
        return value


class RowSecurityRuleListSerializer(serializers.ModelSerializer[RowSecurityRule]):
    role = RoleListSerializer(read_only=True)
    role_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RowSecurityRule
        fields = (
            "id",
            "tenant_id",
            "module",
            "resource",
            "role",
            "role_id",
            "rule_type",
            "filter_criteria",
            "priority",
            "is_active",
            "version",
            "is_deleted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
        )
        read_only_fields = fields


class RowSecurityRuleDetailSerializer(RowSecurityRuleListSerializer):
    pass


class RowSecurityRuleCreateSerializer(serializers.Serializer[dict[str, Any]]):
    module = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,99}$")
    resource = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,99}$")
    role_id = serializers.UUIDField()
    rule_type = serializers.ChoiceField(choices=RowSecurityRule.RuleType.choices, required=False)
    filter_criteria = PredicateSerializer()
    priority = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False, default=True)


class RowSecurityRuleUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    rule_type = serializers.ChoiceField(choices=RowSecurityRule.RuleType.choices, required=False)
    filter_criteria = PredicateSerializer(required=False)
    priority = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)


class TimeWindowSerializer(serializers.Serializer[dict[str, Any]]):
    start = serializers.TimeField()
    end = serializers.TimeField()


class TimeRestrictionsSerializer(serializers.Serializer[dict[str, Any]]):
    timezone = serializers.CharField(max_length=64)
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=7), max_length=7)
    windows = TimeWindowSerializer(many=True)


class SecurityProfileListSerializer(serializers.ModelSerializer[SecurityProfile]):
    class Meta:
        model = SecurityProfile
        fields = (
            "id",
            "tenant_id",
            "name",
            "description",
            "profile_type",
            "mfa_required",
            "session_timeout_minutes",
            "is_active",
            "is_deleted",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
        )
        read_only_fields = fields


_PROFILE_FIELDS = (
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
    "is_active",
)


class SecurityProfileDetailSerializer(serializers.ModelSerializer[SecurityProfile]):
    class Meta:
        model = SecurityProfile
        fields = (
            ("id", "tenant_id")
            + _PROFILE_FIELDS
            + (
                "is_deleted",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "deleted_at",
            )
        )
        read_only_fields = fields


class SecurityProfileWriteSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    profile_type = serializers.ChoiceField(choices=SecurityProfile.ProfileType.choices, required=False)
    ip_whitelist = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=100)
    ip_blacklist = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=100)
    allowed_countries = serializers.ListField(
        child=serializers.RegexField(r"^[A-Za-z]{2}$"), required=False, max_length=249
    )
    blocked_countries = serializers.ListField(
        child=serializers.RegexField(r"^[A-Za-z]{2}$"), required=False, max_length=249
    )
    time_restrictions = TimeRestrictionsSerializer(required=False)
    mfa_required = serializers.ChoiceField(choices=SecurityProfile.MFARequired.choices, required=False)
    allowed_mfa_methods = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, max_length=20
    )
    password_policy = serializers.DictField(required=False)
    session_timeout_minutes = serializers.IntegerField(required=False)
    absolute_session_timeout_hours = serializers.IntegerField(required=False)
    max_concurrent_sessions = serializers.IntegerField(required=False)
    download_allowed = serializers.BooleanField(required=False)
    print_allowed = serializers.BooleanField(required=False)
    copy_paste_allowed = serializers.BooleanField(required=False)
    mobile_access_allowed = serializers.BooleanField(required=False)
    login_notification = serializers.BooleanField(required=False)
    access_notification = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class SecurityProfileCreateSerializer(SecurityProfileWriteSerializer):
    name = serializers.CharField(max_length=255)


class SecurityProfileUpdateSerializer(SecurityProfileWriteSerializer):
    pass


class SecurityProfileAssignmentListSerializer(serializers.ModelSerializer[SecurityProfileAssignment]):
    is_active = serializers.BooleanField(read_only=True)
    security_profile = SecurityProfileListSerializer(read_only=True)
    role = RoleListSerializer(read_only=True)
    security_profile_id = serializers.UUIDField(read_only=True)
    role_id = serializers.UUIDField(read_only=True, allow_null=True)
    user_id = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = SecurityProfileAssignment
        fields = (
            "id",
            "tenant_id",
            "security_profile_id",
            "security_profile",
            "user_id",
            "role_id",
            "role",
            "precedence",
            "valid_from",
            "valid_until",
            "reason",
            "revoked_at",
            "revocation_reason",
            "assigned_by",
            "revoked_by",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SecurityProfileAssignmentDetailSerializer(SecurityProfileAssignmentListSerializer):
    pass


class SecurityProfileAssignmentCreateSerializer(serializers.Serializer[dict[str, Any]]):
    security_profile_id = serializers.UUIDField()
    user_id = serializers.CharField(required=False, allow_null=True, max_length=128)
    role_id = serializers.UUIDField(required=False, allow_null=True)
    precedence = serializers.IntegerField(required=False)
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=2000, allow_blank=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if bool(attrs.get("user_id")) == bool(attrs.get("role_id")):
            raise serializers.ValidationError("Exactly one of user_id or role_id is required.")
        return attrs


class SecurityProfileAssignmentUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    precedence = serializers.IntegerField(required=False)
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, max_length=2000, allow_blank=False)


class SecurityAuditLogSerializer(serializers.ModelSerializer[SecurityAuditLog]):
    details = serializers.SerializerMethodField()

    class Meta:
        model = SecurityAuditLog
        fields = (
            "id",
            "action",
            "actor_type",
            "resource_type",
            "resource_id",
            "decision",
            "reason_codes",
            "timestamp",
            "details",
            "correlation_id",
        )
        read_only_fields = fields

    def get_details(self, obj: SecurityAuditLog) -> object:
        return redact_sensitive(obj.details)


SecurityAuditLogListSerializer = SecurityAuditLogSerializer
SecurityAuditLogDetailSerializer = SecurityAuditLogSerializer


class AccessSimulationSerializer(serializers.Serializer[dict[str, Any]]):
    subject_id = serializers.CharField(max_length=128)
    permission_code = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,99}\.[a-z][a-z0-9_-]{0,99}:[a-z][a-z0-9_-]{0,49}$")
    resource_context = serializers.DictField(required=False, default=dict)


class AccessDecisionSerializer(serializers.Serializer[dict[str, Any]]):
    allowed = serializers.BooleanField(read_only=True)
    subject_id = serializers.CharField(read_only=True)
    permission_code = serializers.CharField(read_only=True)
    decision = serializers.ChoiceField(choices=("allow", "deny"), read_only=True)
    reason_codes = serializers.ListField(child=serializers.CharField(), read_only=True)
    applied_policy_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    entitlement = serializers.DictField(read_only=True)
    quota = serializers.DictField(read_only=True)
    field_decisions = serializers.ListField(read_only=True)
    row_explanation = serializers.DictField(read_only=True, allow_null=True)
    audit_log_id = serializers.CharField(read_only=True, allow_null=True)
    correlation_id = serializers.CharField(read_only=True)
    evaluated_at = serializers.DateTimeField(read_only=True)


__all__ = [name for name in globals() if name.endswith("Serializer")]
