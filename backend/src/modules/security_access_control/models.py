"""Tenant-safe authorization policy and immutable security evidence models."""

from __future__ import annotations

import uuid
import sys
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel


def _seed_default(section: str, key: str) -> object:
    """Resolve ORM construction defaults from the governed configuration seed."""
    from .services import default_security_configuration

    configured = default_security_configuration()[section]
    if not isinstance(configured, dict):
        raise RuntimeError(f"Invalid security configuration seed section: {section}")
    return configured[key]


def default_field_visibility() -> str:
    return str(_seed_default("defaults", "field_visibility"))


def default_field_edit_control() -> str:
    return str(_seed_default("defaults", "field_edit_control"))


def default_row_rule_type() -> str:
    return str(_seed_default("defaults", "row_rule_type"))


def default_row_rule_priority() -> int:
    return int(_seed_default("defaults", "row_rule_priority"))


def _profile_seed_default(key: str) -> object:
    profile = _seed_default("defaults", "security_profile")
    if not isinstance(profile, dict):
        raise RuntimeError("Invalid security profile configuration seed")
    return profile[key]


def default_profile_type() -> str:
    return str(_profile_seed_default("profile_type"))


def default_mfa_requirement() -> str:
    return str(_profile_seed_default("mfa_required"))


def default_session_timeout_minutes() -> int:
    return int(_profile_seed_default("session_timeout_minutes"))


def default_absolute_session_timeout_hours() -> int:
    return int(_profile_seed_default("absolute_session_timeout_hours"))


def default_max_concurrent_sessions() -> int:
    return int(_profile_seed_default("max_concurrent_sessions"))


def default_download_allowed() -> bool:
    return bool(_profile_seed_default("download_allowed"))


def default_print_allowed() -> bool:
    return bool(_profile_seed_default("print_allowed"))


def default_copy_paste_allowed() -> bool:
    return bool(_profile_seed_default("copy_paste_allowed"))


def default_mobile_access_allowed() -> bool:
    return bool(_profile_seed_default("mobile_access_allowed"))


def default_login_notification() -> bool:
    return bool(_profile_seed_default("login_notification"))


def default_access_notification() -> bool:
    return bool(_profile_seed_default("access_notification"))


def default_profile_assignment_precedence() -> int:
    return int(_seed_default("defaults", "profile_assignment_precedence"))


class MutableSecurityModel(TenantScopedModel, TimestampedModel):
    """Shared lifecycle columns for tenant-owned mutable policy records."""

    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class ImmutableConfigurationError(RuntimeError):
    """Raised when append-only configuration evidence is mutated."""


class ImmutableConfigurationQuerySet(models.QuerySet):
    """Queryset that makes configuration history and replay evidence append-only."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "ImmutableConfigurationQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableConfigurationError("Configuration evidence is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableConfigurationError("Configuration evidence is append-only")


class SecurityConfiguration(TenantScopedModel, TimestampedModel):
    """Current tenant-owned security behavior document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=32)
    version = models.PositiveIntegerField(default=1)
    document = models.JSONField()
    rollout = models.JSONField()
    updated_by = models.UUIDField()
    correlation_id = models.CharField(max_length=128)

    class Meta:
        db_table = "security_configurations"
        constraints = [models.UniqueConstraint(fields=("tenant_id",), name="sec_config_tenant_uniq")]
        indexes = [
            models.Index(fields=("tenant_id", "version"), name="sec_config_tenant_version_idx"),
            models.Index(fields=("tenant_id", "environment"), name="sec_config_tenant_env_idx"),
        ]


class SecurityConfigurationVersion(TenantScopedModel):
    """Immutable before/after evidence for every tenant configuration change."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField()
    environment = models.CharField(max_length=32)
    previous_document = models.JSONField(null=True)
    current_document = models.JSONField()
    previous_rollout = models.JSONField(null=True)
    current_rollout = models.JSONField()
    actor_id = models.UUIDField()
    correlation_id = models.CharField(max_length=128)
    reason = models.TextField()
    change_kind = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableConfigurationQuerySet.as_manager()

    class Meta:
        db_table = "security_configuration_versions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "version"), name="sec_config_version_tenant_uniq")
        ]
        indexes = [
            models.Index(fields=("tenant_id", "-version"), name="sec_config_version_history_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="sec_config_version_corr_idx"),
        ]
        ordering = ("-version",)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableConfigurationError("Configuration evidence is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableConfigurationError("Configuration evidence is append-only")


class MutationReplay(TenantScopedModel):
    """Immutable response ledger used to make tenant mutations replay-safe."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    operation = models.CharField(max_length=128)
    resource_id = models.UUIDField(null=True)
    response_status = models.PositiveSmallIntegerField()
    response_document = models.JSONField()
    correlation_id = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableConfigurationQuerySet.as_manager()

    class Meta:
        db_table = "security_mutation_replays"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="sec_replay_tenant_key_uniq")
        ]
        indexes = [models.Index(fields=("tenant_id", "operation"), name="sec_replay_tenant_op_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableConfigurationError("Mutation replay evidence is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableConfigurationError("Mutation replay evidence is append-only")


class Permission(models.Model):
    """Immutable, platform-global permission catalog entry."""

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    action = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.MEDIUM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_permissions"
        constraints = [
            models.UniqueConstraint(fields=("module", "resource", "action"), name="sec_permission_code_uniq")
        ]
        indexes = [models.Index(fields=("module", "resource", "action"), name="sec_permission_code_idx")]
        ordering = ("module", "resource", "action")

    @property
    def code(self) -> str:
        return f"{self.module}.{self.resource}:{self.action}"

    def __str__(self) -> str:
        return self.code


class Role(MutableSecurityModel):
    """Tenant-owned RBAC role with bounded single-parent inheritance."""

    class RoleType(models.TextChoices):
        SYSTEM = "system", "System"
        FUNCTIONAL = "functional", "Functional"
        CUSTOM = "custom", "Custom"
        TEMPORARY = "temporary", "Temporary"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    role_type = models.CharField(max_length=20, choices=RoleType.choices, default=RoleType.CUSTOM)
    parent_role = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="child_roles")
    hierarchy_level = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        db_table = "security_roles"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "code"), condition=Q(is_deleted=False), name="sec_role_tenant_code_active_uniq"
            ),
            models.CheckConstraint(condition=Q(hierarchy_level__gte=0), name="sec_role_hierarchy_nonnegative"),
            models.CheckConstraint(
                condition=Q(parent_role__isnull=True) | ~Q(parent_role=models.F("id")),
                name="sec_role_parent_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "role_type"), name="sec_role_active_type_idx"),
            models.Index(fields=("tenant_id", "parent_role"), name="sec_role_tenant_parent_idx"),
            models.Index(fields=("tenant_id", "name"), name="sec_role_tenant_name_idx"),
        ]
        ordering = ("name", "id")

    def clean(self) -> None:
        if self.parent_role_id:
            parent = Role.objects.filter(id=self.parent_role_id).only("tenant_id", "parent_role_id").first()
            if parent is None or parent.tenant_id != self.tenant_id:
                raise ValidationError({"parent_role_id": "Parent role must belong to this tenant."})
            configuration = SecurityConfiguration.objects.for_tenant(self.tenant_id).first()
            if configuration is None:
                # Direct ORM/model validation can run before the API bootstrap has
                # an authenticated actor. Apply the same fail-closed seed policy;
                # API/service mutations always persist the tenant copy first.
                from .services import default_security_configuration

                limits = default_security_configuration()["limits"]
            else:
                limits = configuration.document.get("limits")
            if not isinstance(limits, dict):
                raise ValidationError({"parent_role_id": "Tenant hierarchy configuration is required."})
            maximum_depth = int(limits["role_hierarchy_max_depth"])
            seen = {self.id}
            depth = 1
            while parent is not None:
                if parent.id in seen:
                    raise ValidationError({"parent_role_id": "Role hierarchy cannot contain a cycle."})
                seen.add(parent.id)
                if depth > maximum_depth:
                    raise ValidationError({"parent_role_id": f"Role hierarchy cannot exceed {maximum_depth} levels."})
                parent = (
                    Role.objects.filter(id=parent.parent_role_id).only("id", "tenant_id", "parent_role_id").first()
                    if parent.parent_role_id
                    else None
                )
                depth += 1

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class RolePermission(TenantScopedModel, TimestampedModel):
    """Explicit allow or deny associated with a role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="role_permissions")
    is_granted = models.BooleanField(default=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "security_role_permissions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "role", "permission"), name="sec_role_permission_uniq")
        ]
        indexes = [models.Index(fields=("tenant_id", "role", "is_granted"), name="sec_role_perm_decision_idx")]

    def clean(self) -> None:
        if self.role_id and self.role.tenant_id != self.tenant_id:
            raise ValidationError({"role_id": "Role must belong to this tenant."})

    def __str__(self) -> str:
        return f"{self.role.code} -> {self.permission.code} ({'allow' if self.is_granted else 'deny'})"


class UserRole(TenantScopedModel, TimestampedModel):
    """Temporal, revocable role assignment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_user_roles")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_roles")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    assigned_by = models.UUIDField()
    reason = models.TextField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.UUIDField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "security_user_roles"
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F("valid_from")),
                name="sec_user_role_valid_interval",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "user", "role"),
                condition=Q(revoked_at__isnull=True),
                name="sec_user_role_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "user", "valid_from", "valid_until"), name="sec_user_role_valid_idx"),
            models.Index(fields=("tenant_id", "role", "revoked_at"), name="sec_user_role_revoke_idx"),
        ]
        ordering = ("-valid_from", "id")

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return (
            self.revoked_at is None and self.valid_from <= now and (self.valid_until is None or now < self.valid_until)
        )

    def clean(self) -> None:
        if self.role_id and self.role.tenant_id != self.tenant_id:
            raise ValidationError({"role_id": "Role must belong to this tenant."})
        if not self.reason.strip():
            raise ValidationError({"reason": "A nonblank assignment reason is required."})
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "Must be later than valid_from."})

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.role.code}"


class PermissionSet(MutableSecurityModel):
    """Reusable tenant-owned capability bundle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_duration_days = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "security_permission_sets"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="sec_permset_tenant_name_uniq"
            ),
            models.CheckConstraint(
                condition=Q(default_duration_days__isnull=True)
                | Q(default_duration_days__gte=1, default_duration_days__lte=3650),
                name="sec_permset_duration_range",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "is_active", "name"), name="sec_permset_active_name_idx")]
        ordering = ("name", "id")

    def clean(self) -> None:
        configuration = SecurityConfiguration.objects.for_tenant(self.tenant_id).first()
        if configuration is None:
            from .services import default_security_configuration

            limits = default_security_configuration()["limits"]
        else:
            limits = configuration.document.get("limits")
        if not isinstance(limits, dict):
            raise ValidationError({"default_duration_days": "Tenant duration configuration is required."})
        minimum = int(limits["permission_set_duration_min_days"])
        maximum = int(limits["permission_set_duration_max_days"])
        if self.default_duration_days is not None and not minimum <= self.default_duration_days <= maximum:
            raise ValidationError(
                {"default_duration_days": f"Must be between {minimum} and {maximum} days."}
            )

    def __str__(self) -> str:
        return self.name


class PermissionSetPermission(TenantScopedModel):
    """Revocable normalized permission-set membership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    permission_set = models.ForeignKey(PermissionSet, on_delete=models.CASCADE, related_name="memberships")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="permission_set_memberships")
    added_at = models.DateTimeField(default=timezone.now)
    added_by = models.UUIDField()
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "security_permission_set_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "permission_set", "permission"),
                condition=Q(removed_at__isnull=True),
                name="sec_permset_member_active_uniq",
            )
        ]
        indexes = [models.Index(fields=("tenant_id", "permission_set", "removed_at"), name="sec_permset_member_idx")]

    def clean(self) -> None:
        if self.permission_set_id and self.permission_set.tenant_id != self.tenant_id:
            raise ValidationError({"permission_set_id": "Permission set must belong to this tenant."})


class UserPermissionSet(TenantScopedModel, TimestampedModel):
    """Time-bound, revocable grant of a permission set."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_user_permission_sets"
    )
    permission_set = models.ForeignKey(PermissionSet, on_delete=models.PROTECT, related_name="user_grants")
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    granted_by = models.UUIDField()
    reason = models.TextField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.UUIDField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "security_user_permission_sets"
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("granted_at")), name="sec_user_permset_interval"
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "user", "permission_set"),
                condition=Q(revoked_at__isnull=True),
                name="sec_user_permset_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "user", "expires_at"), name="sec_user_permset_expiry_idx"),
            models.Index(fields=("tenant_id", "permission_set", "revoked_at"), name="sec_user_permset_revoke_idx"),
        ]
        ordering = ("-granted_at", "id")

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.revoked_at is None and self.granted_at <= now < self.expires_at

    def clean(self) -> None:
        if self.permission_set_id and self.permission_set.tenant_id != self.tenant_id:
            raise ValidationError({"permission_set_id": "Permission set must belong to this tenant."})
        if not self.reason.strip():
            raise ValidationError({"reason": "A nonblank grant reason is required."})
        if self.expires_at <= self.granted_at:
            raise ValidationError({"expires_at": "Must be later than granted_at."})


class FieldSecurity(MutableSecurityModel):
    """Tenant-owned field visibility and edit rule."""

    class Visibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        HIDDEN = "hidden", "Hidden"
        MASKED = "masked", "Masked"
        REDACTED = "redacted", "Redacted"

    class EditControl(models.TextChoices):
        READ_ONLY = "read_only", "Read only"
        EDITABLE = "editable", "Editable"
        REQUIRED = "required", "Required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    field = models.CharField(max_length=100)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="field_security_rules")
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=default_field_visibility)
    edit_control = models.CharField(max_length=20, choices=EditControl.choices, default=default_field_edit_control)
    mask_pattern = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "security_field_security"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "module", "resource", "field", "role"),
                condition=Q(is_active=True, is_deleted=False),
                name="sec_field_rule_active_uniq",
            ),
            models.CheckConstraint(
                condition=Q(visibility="masked", mask_pattern__gt="") | ~Q(visibility="masked"),
                name="sec_field_mask_required",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "module", "resource", "is_active"), name="sec_field_resource_idx"),
            models.Index(fields=("tenant_id", "role"), name="sec_field_role_idx"),
        ]

    def clean(self) -> None:
        if self.role_id and self.role.tenant_id != self.tenant_id:
            raise ValidationError({"role_id": "Role must belong to this tenant."})
        if self.visibility == self.Visibility.MASKED and not self.mask_pattern.strip():
            raise ValidationError({"mask_pattern": "A mask pattern is required for masked fields."})
        if self.visibility != self.Visibility.MASKED and self.mask_pattern:
            raise ValidationError({"mask_pattern": "A mask pattern is only valid for masked fields."})

    def __str__(self) -> str:
        return f"{self.module}.{self.resource}.{self.field} -> {self.role.code} ({self.visibility})"


class RowSecurityRule(MutableSecurityModel):
    """Versioned row-access rule stored as a validated predicate AST."""

    class RuleType(models.TextChoices):
        OWNERSHIP = "ownership", "Ownership"
        HIERARCHY = "hierarchy", "Hierarchy"
        ATTRIBUTE = "attribute", "Attribute"
        CRITERIA = "criteria", "Criteria"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="row_security_rules")
    rule_type = models.CharField(max_length=20, choices=RuleType.choices, default=default_row_rule_type)
    filter_criteria = models.JSONField(default=dict)
    priority = models.SmallIntegerField(default=default_row_rule_priority)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "security_row_security_rules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "module", "resource", "role", "priority", "version"),
                name="sec_row_rule_version_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "module", "resource", "is_active", "priority"), name="sec_row_resource_idx"
            ),
            models.Index(fields=("tenant_id", "role"), name="sec_row_role_idx"),
        ]
        ordering = ("-priority", "module", "resource", "id")

    def clean(self) -> None:
        from .predicates import validate_predicate

        if self.role_id and self.role.tenant_id != self.tenant_id:
            raise ValidationError({"role_id": "Role must belong to this tenant."})
        # Model validation enforces the closed grammar. Tenant-configured complexity
        # bounds are enforced in RowSecurityService before this model is persisted.
        validate_predicate(
            self.filter_criteria,
            max_nodes=sys.maxsize,
            max_depth=max(1, sys.getrecursionlimit() - 10),
            max_in_values=sys.maxsize,
        )

    def __str__(self) -> str:
        return f"{self.module}.{self.resource} -> {self.role.code} ({self.rule_type})"


class SecurityProfile(MutableSecurityModel):
    """Contextual restrictions assigned directly or through roles."""

    class ProfileType(models.TextChoices):
        STANDARD = "standard", "Standard"
        PRIVILEGED = "privileged", "Privileged"
        RESTRICTED = "restricted", "Restricted"
        HIGH_SECURITY = "high_security", "High security"

    class MFARequired(models.TextChoices):
        ALWAYS = "always", "Always"
        CONDITIONAL = "conditional", "Conditional"
        SENSITIVE_ACTIONS = "sensitive_actions", "Sensitive actions"
        NEVER = "never", "Never"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    profile_type = models.CharField(max_length=20, choices=ProfileType.choices, default=default_profile_type)
    ip_whitelist = models.JSONField(default=list, blank=True)
    ip_blacklist = models.JSONField(default=list, blank=True)
    allowed_countries = models.JSONField(default=list, blank=True)
    blocked_countries = models.JSONField(default=list, blank=True)
    time_restrictions = models.JSONField(default=dict, blank=True)
    mfa_required = models.CharField(max_length=20, choices=MFARequired.choices, default=default_mfa_requirement)
    allowed_mfa_methods = models.JSONField(default=list, blank=True)
    password_policy = models.JSONField(default=dict, blank=True)
    session_timeout_minutes = models.PositiveIntegerField(default=default_session_timeout_minutes)
    absolute_session_timeout_hours = models.PositiveIntegerField(default=default_absolute_session_timeout_hours)
    max_concurrent_sessions = models.PositiveIntegerField(default=default_max_concurrent_sessions)
    download_allowed = models.BooleanField(default=default_download_allowed)
    print_allowed = models.BooleanField(default=default_print_allowed)
    copy_paste_allowed = models.BooleanField(default=default_copy_paste_allowed)
    mobile_access_allowed = models.BooleanField(default=default_mobile_access_allowed)
    login_notification = models.BooleanField(default=default_login_notification)
    access_notification = models.BooleanField(default=default_access_notification)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "security_security_profiles"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="sec_profile_tenant_name_uniq"
            ),
            models.CheckConstraint(
                condition=Q(session_timeout_minutes__gte=1, session_timeout_minutes__lte=10080),
                name="sec_profile_session_timeout",
            ),
            models.CheckConstraint(
                condition=Q(absolute_session_timeout_hours__gte=1, absolute_session_timeout_hours__lte=744),
                name="sec_profile_absolute_timeout",
            ),
            models.CheckConstraint(
                condition=Q(max_concurrent_sessions__gte=1, max_concurrent_sessions__lte=1000),
                name="sec_profile_session_count",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "profile_type", "is_active"), name="sec_profile_type_active_idx")]
        ordering = ("name", "id")

    def clean(self) -> None:
        from .validators import validate_security_profile

        validate_security_profile(self)

    def __str__(self) -> str:
        return f"{self.name} ({self.profile_type})"


class SecurityProfileAssignment(TenantScopedModel, TimestampedModel):
    """Temporal assignment of one security profile to one user or role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    security_profile = models.ForeignKey(SecurityProfile, on_delete=models.PROTECT, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="security_profile_assignments",
    )
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.PROTECT, related_name="security_profile_assignments"
    )
    precedence = models.SmallIntegerField(default=default_profile_assignment_precedence)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    assigned_by = models.UUIDField()
    reason = models.TextField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.UUIDField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "security_profile_assignments"
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False, role__isnull=True) | Q(user__isnull=True, role__isnull=False)),
                name="sec_profile_assignment_one_subject",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F("valid_from")),
                name="sec_profile_assignment_interval",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "user", "security_profile"),
                condition=Q(revoked_at__isnull=True, user__isnull=False),
                name="sec_profile_assignment_user_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "role", "security_profile"),
                condition=Q(revoked_at__isnull=True, role__isnull=False),
                name="sec_profile_assignment_role_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "user", "revoked_at"), name="sec_profile_assign_user_idx"),
            models.Index(fields=("tenant_id", "role", "revoked_at"), name="sec_profile_assign_role_idx"),
        ]
        ordering = ("-precedence", "-valid_from", "id")

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return (
            self.revoked_at is None and self.valid_from <= now and (self.valid_until is None or now < self.valid_until)
        )

    def clean(self) -> None:
        if bool(self.user_id) == bool(self.role_id):
            raise ValidationError("Exactly one of user or role is required.")
        if self.security_profile_id and self.security_profile.tenant_id != self.tenant_id:
            raise ValidationError({"security_profile_id": "Profile must belong to this tenant."})
        if self.role_id and self.role.tenant_id != self.tenant_id:
            raise ValidationError({"role_id": "Role must belong to this tenant."})
        if not self.reason.strip():
            raise ValidationError({"reason": "A nonblank assignment reason is required."})
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "Must be later than valid_from."})


class ImmutableAuditError(RuntimeError):
    """Raised whenever append-only security evidence is mutated."""


class SecurityAuditQuerySet(models.QuerySet["SecurityAuditLog"]):
    def for_tenant(self, tenant_id: uuid.UUID) -> "SecurityAuditQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableAuditError("SecurityAuditLog records are append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableAuditError("SecurityAuditLog records are append-only")


class SecurityAuditLog(TenantScopedModel):
    """Immutable, tenant-owned security evidence."""

    class ActorType(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        AGENT = "agent", "Agent"

    class Decision(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=100)
    actor_type = models.CharField(max_length=20, choices=ActorType.choices, default=ActorType.USER)
    actor_id = models.UUIDField()
    resource_type = models.CharField(max_length=100)
    resource_id = models.UUIDField(null=True, blank=True)
    decision = models.CharField(max_length=10, choices=Decision.choices, null=True, blank=True)
    reason_codes = models.JSONField(default=list, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=128)
    outbox_event_id = models.UUIDField(null=True, blank=True)

    objects = SecurityAuditQuerySet.as_manager()

    class Meta:
        db_table = "security_audit_logs"
        indexes = [
            models.Index(fields=("tenant_id", "timestamp"), name="sec_audit_tenant_time_idx"),
            models.Index(fields=("tenant_id", "actor_id", "timestamp"), name="sec_audit_actor_time_idx"),
            models.Index(fields=("tenant_id", "resource_type", "resource_id"), name="sec_audit_resource_idx"),
            models.Index(fields=("tenant_id", "action", "timestamp"), name="sec_audit_action_time_idx"),
            models.Index(fields=("tenant_id", "decision", "timestamp"), name="sec_audit_decision_time_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="sec_audit_correlation_idx"),
        ]
        ordering = ("-timestamp", "-id")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableAuditError("SecurityAuditLog records are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableAuditError("SecurityAuditLog records are append-only")

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id} at {self.timestamp} ({self.decision or 'evidence'})"
