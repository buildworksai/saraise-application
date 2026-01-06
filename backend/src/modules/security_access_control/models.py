"""
Security & Access Control Models.

CRITICAL: These models implement RBAC, permissions, field-level security,
row-level security, security profiles, and audit logs.

Architecture Compliance:
- ✅ Django ORM
- ✅ tenant_id for tenant-scoped models
- ✅ Indexes on frequently queried fields
- ✅ Immutable audit logs
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


def generate_uuid():
    """Generate UUID string for model primary keys (for migration compatibility)."""
    return str(uuid.uuid4())


class Role(models.Model):
    """
    Role model for RBAC.

    CRITICAL: Tenant-scoped model (has tenant_id).
    Roles define collections of permissions.
    """

    class RoleType(models.TextChoices):
        SYSTEM = "system", "System Role"
        FUNCTIONAL = "functional", "Functional Role"
        CUSTOM = "custom", "Custom Role"
        TEMPORARY = "temporary", "Temporary Role"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=False, blank=False)

    # Role definition
    name = models.CharField(max_length=255, db_index=True)
    code = models.CharField(
        max_length=100, db_index=True
    )  # snake_case unique identifier
    description = models.TextField(blank=True)
    role_type = models.CharField(
        max_length=50, choices=RoleType.choices, default=RoleType.CUSTOM
    )

    # Hierarchy
    parent_role_id = models.UUIDField(null=True, blank=True, db_index=True)
    hierarchy_level = models.IntegerField(default=0)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_system = models.BooleanField(default=False)  # System roles cannot be deleted

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "security_roles"
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["parent_role_id"]),
            models.Index(fields=["role_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Permission(models.Model):
    """
    Permission model for granular access control.

    CRITICAL: Platform-level model (NO tenant_id).
    Permissions are shared across all tenants.
    Format: module:object:action (e.g., "crm:customers:read")
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Permission definition
    module = models.CharField(max_length=100, db_index=True)  # crm, accounting, hr
    object = models.CharField(max_length=100)  # customers, invoices, employees
    action = models.CharField(max_length=50)  # create, read, update, delete

    # Display
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_permissions"
        unique_together = [["module", "object", "action"]]
        indexes = [
            models.Index(fields=["module"]),
        ]

    def __str__(self):
        return f"{self.module}:{self.object}:{self.action}"


class RolePermission(models.Model):
    """
    Many-to-many relationship between Roles and Permissions.

    CRITICAL: Links tenant-scoped roles to platform-level permissions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="role_permissions"
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_permissions"
    )

    # Override
    is_granted = models.BooleanField(default=True)  # false for explicit deny

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_role_permissions"
        unique_together = [["role", "permission"]]
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["permission"]),
        ]

    def __str__(self):
        grant_status = "granted" if self.is_granted else "denied"
        return f"{self.role.code} -> {self.permission} ({grant_status})"


class UserRole(models.Model):
    """
    Many-to-many relationship between Users and Roles.

    CRITICAL: Tenant-scoped via role.tenant_id.
    Supports temporal role assignments (valid_from, valid_until).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    # Temporal
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)  # NULL = permanent

    # Delegation
    assigned_by = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_user_roles"
        unique_together = [["user", "role"]]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["role"]),
            models.Index(fields=["valid_from", "valid_until"]),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.role.name}"

    @property
    def is_active(self):
        """Check if role assignment is currently active."""
        now = timezone.now()
        if self.valid_until and self.valid_until < now:
            return False
        if self.valid_from > now:
            return False
        return True


class PermissionSet(models.Model):
    """
    Reusable collection of permissions.

    CRITICAL: Tenant-scoped model (has tenant_id).
    Used for temporary permission grants (e.g., quarterly close, audit access).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=False, blank=False)

    # Set definition
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)

    # Permissions (stored as JSON array of permission IDs)
    permission_ids = models.JSONField(default=list)

    # Temporal
    default_duration_days = models.IntegerField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "security_permission_sets"
        indexes = [
            models.Index(fields=["tenant_id"]),
        ]

    def __str__(self):
        return f"{self.name} ({len(self.permission_ids)} permissions)"


class UserPermissionSet(models.Model):
    """
    Temporary grant of a permission set to a user.

    CRITICAL: Tenant-scoped via permission_set.tenant_id.
    Automatically expires at expires_at.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_permission_sets"
    )
    permission_set = models.ForeignKey(
        PermissionSet, on_delete=models.CASCADE, related_name="user_permission_sets"
    )

    # Temporal
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    # Context
    granted_by = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "security_user_permission_sets"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.permission_set.name} (expires: {self.expires_at})"

    @property
    def is_active(self):
        """Check if permission set grant is currently active."""
        now = timezone.now()
        return self.granted_at <= now < self.expires_at


class FieldSecurity(models.Model):
    """
    Field-Level Security (FLS) configuration.

    CRITICAL: Tenant-scoped model (has tenant_id).
    Controls visibility and editability of fields per role.
    """

    class Visibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        HIDDEN = "hidden", "Hidden"
        MASKED = "masked", "Masked"
        REDACTED = "redacted", "Redacted"

    class EditControl(models.TextChoices):
        READ_ONLY = "read_only", "Read Only"
        EDITABLE = "editable", "Editable"
        REQUIRED = "required", "Required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=False, blank=False)

    # Target
    module = models.CharField(max_length=100, db_index=True)
    object = models.CharField(max_length=100, db_index=True)
    field = models.CharField(max_length=100, db_index=True)

    # Security per Role
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="field_security"
    )

    # Visibility
    visibility = models.CharField(
        max_length=50, choices=Visibility.choices, default=Visibility.VISIBLE
    )

    # Edit Control
    edit_control = models.CharField(
        max_length=50, choices=EditControl.choices, default=EditControl.EDITABLE
    )

    # Masking
    mask_pattern = models.CharField(
        max_length=100, blank=True
    )  # e.g., '***-**-XXXX' for SSN

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_field_security"
        unique_together = [["tenant_id", "module", "object", "field", "role"]]
        indexes = [
            models.Index(fields=["tenant_id", "module", "object"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.module}.{self.object}.{self.field} -> {self.role.code} ({self.visibility})"


class RowSecurityRule(models.Model):
    """
    Row-Level Security (RLS) rule.

    CRITICAL: Tenant-scoped model (has tenant_id).
    Defines filter criteria for row-level access control.
    """

    class RuleType(models.TextChoices):
        OWNERSHIP = "ownership", "Ownership-Based"
        HIERARCHY = "hierarchy", "Hierarchy-Based"
        ATTRIBUTE = "attribute", "Attribute-Based"
        CRITERIA = "criteria", "Criteria-Based"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=False, blank=False)

    # Target
    module = models.CharField(max_length=100, db_index=True)
    object = models.CharField(max_length=100, db_index=True)

    # Rule
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="row_security_rules"
    )
    rule_type = models.CharField(
        max_length=50, choices=RuleType.choices, default=RuleType.OWNERSHIP
    )

    # Filter (SQL WHERE clause or equivalent)
    filter_criteria = models.TextField()

    # Priority (higher priority rules apply first)
    priority = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_row_security_rules"
        indexes = [
            models.Index(fields=["tenant_id", "module", "object"]),
            models.Index(fields=["role"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"{self.module}.{self.object} -> {self.role.code} ({self.rule_type})"


class SecurityProfile(models.Model):
    """
    Security Profile for context-aware access control.

    CRITICAL: Tenant-scoped model (has tenant_id).
    Defines access policies, authentication policies, and data policies.
    """

    class ProfileType(models.TextChoices):
        STANDARD = "standard", "Standard"
        PRIVILEGED = "privileged", "Privileged"
        RESTRICTED = "restricted", "Restricted"
        HIGH_SECURITY = "high_security", "High Security"

    class MFARequired(models.TextChoices):
        ALWAYS = "always", "Always"
        CONDITIONAL = "conditional", "Conditional"
        SENSITIVE_ACTIONS = "sensitive_actions", "Sensitive Actions Only"
        NEVER = "never", "Never"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=False, blank=False)

    # Profile definition
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    profile_type = models.CharField(
        max_length=50, choices=ProfileType.choices, default=ProfileType.STANDARD
    )

    # Access Policies (stored as JSON)
    ip_whitelist = models.JSONField(default=list, blank=True)
    ip_blacklist = models.JSONField(default=list, blank=True)
    allowed_countries = models.JSONField(default=list, blank=True)  # ISO country codes
    blocked_countries = models.JSONField(default=list, blank=True)
    time_restrictions = models.JSONField(
        default=dict, blank=True
    )  # {days: [1-5], hours: [9-17]}

    # Authentication Policies
    mfa_required = models.CharField(
        max_length=50, choices=MFARequired.choices, default=MFARequired.CONDITIONAL
    )
    allowed_mfa_methods = models.JSONField(default=list, blank=True)
    password_policy = models.JSONField(default=dict, blank=True)
    session_timeout_minutes = models.IntegerField(default=60)
    absolute_session_timeout_hours = models.IntegerField(default=8)
    max_concurrent_sessions = models.IntegerField(default=5)

    # Data Policies
    download_allowed = models.BooleanField(default=True)
    print_allowed = models.BooleanField(default=True)
    copy_paste_allowed = models.BooleanField(default=True)
    mobile_access_allowed = models.BooleanField(default=True)

    # Monitoring
    login_notification = models.BooleanField(default=False)
    access_notification = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "security_security_profiles"
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["profile_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.profile_type})"


class SecurityAuditLog(models.Model):
    """
    Immutable audit log for security events.

    CRITICAL: This model is APPEND-ONLY. Updates and deletes are forbidden.
    CRITICAL: Tenant-scoped model (has tenant_id).
    """

    class ActorType(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        AGENT = "agent", "Agent"

    class Decision(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)

    # Event
    action = models.CharField(max_length=100, db_index=True)
    actor_type = models.CharField(
        max_length=20, choices=ActorType.choices, default=ActorType.USER
    )
    actor_id = models.UUIDField(db_index=True)
    resource_type = models.CharField(max_length=100, db_index=True)
    resource_id = models.UUIDField(null=True, blank=True)

    # Authorization decision
    decision = models.CharField(
        max_length=10, choices=Decision.choices, null=True, blank=True
    )
    reason_codes = models.JSONField(default=list, blank=True)

    # Context
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "security_audit_logs"
        indexes = [
            models.Index(fields=["tenant_id", "timestamp"]),
            models.Index(fields=["actor_id", "timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["decision"]),
        ]
        # CRITICAL: No update/delete allowed
        managed = True

    def save(self, *args, **kwargs):
        if self.pk and SecurityAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit logs are immutable - updates forbidden")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit logs are immutable - deletes forbidden")

    def __str__(self):
        return f"{self.action} by {self.actor_id} at {self.timestamp} ({self.decision or 'N/A'})"
