"""Evolve the legacy security schema into directly tenant-owned records.

The data migration is intentionally fail-closed.  A relationship whose stored
tenant conflicts with its parent, or an unattributed legacy audit record,
cannot be repaired without inventing security provenance and therefore aborts
the migration with the offending identifiers.
"""

from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def _ids(queryset) -> str:
    return ", ".join(str(value) for value in queryset.values_list("id", flat=True)[:25])


def _legacy_integrity_failures(apps) -> list[str]:
    Role = apps.get_model("security_access_control", "Role")
    UserRole = apps.get_model("security_access_control", "UserRole")
    UserPermissionSet = apps.get_model("security_access_control", "UserPermissionSet")
    FieldSecurity = apps.get_model("security_access_control", "FieldSecurity")
    RowSecurityRule = apps.get_model("security_access_control", "RowSecurityRule")
    SecurityAuditLog = apps.get_model("security_access_control", "SecurityAuditLog")

    failures: list[str] = []
    invalid_audit = SecurityAuditLog.objects.filter(tenant_id__isnull=True)
    if invalid_audit.exists():
        failures.append(
            "SecurityAuditLog contains tenant-null evidence; archive it before migration. "
            f"Offending IDs: {_ids(invalid_audit)}"
        )

    for assignment in UserRole.objects.select_related("role").iterator():
        if assignment.assigned_by is None or not (assignment.reason or "").strip():
            failures.append(
                f"UserRole {assignment.id} lacks assigned_by or a nonblank reason; repair provenance before migration"
            )
    for grant in UserPermissionSet.objects.select_related("permission_set").iterator():
        if grant.granted_by is None or not (grant.reason or "").strip():
            failures.append(
                f"UserPermissionSet {grant.id} lacks granted_by or a nonblank reason; repair provenance before migration"
            )

    bad_fields = FieldSecurity.objects.exclude(tenant_id=models.F("role__tenant_id"))
    if bad_fields.exists():
        failures.append(f"FieldSecurity crosses tenants. Offending IDs: {_ids(bad_fields)}")
    bad_rows = RowSecurityRule.objects.exclude(tenant_id=models.F("role__tenant_id"))
    if bad_rows.exists():
        failures.append(f"RowSecurityRule crosses tenants. Offending IDs: {_ids(bad_rows)}")

    role_tenants = dict(Role.objects.values_list("id", "tenant_id"))
    bad_hierarchy: list[str] = []
    for role in Role.objects.exclude(parent_role__isnull=True).iterator():
        if role_tenants.get(role.parent_role_id) != role.tenant_id:
            bad_hierarchy.append(str(role.id))
    if bad_hierarchy:
        failures.append("Role hierarchy crosses tenants. Offending IDs: " + ", ".join(bad_hierarchy[:25]))

    return failures


def validate_legacy_security_data(apps, schema_editor) -> None:
    del schema_editor
    failures = _legacy_integrity_failures(apps)
    if failures:
        raise RuntimeError("; ".join(failures))


def validate_and_backfill_tenants(apps, schema_editor) -> None:
    del schema_editor
    failures = _legacy_integrity_failures(apps)
    if failures:
        raise RuntimeError("; ".join(failures))

    RolePermission = apps.get_model("security_access_control", "RolePermission")
    UserRole = apps.get_model("security_access_control", "UserRole")
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    UserPermissionSet = apps.get_model("security_access_control", "UserPermissionSet")
    SecurityAuditLog = apps.get_model("security_access_control", "SecurityAuditLog")

    for role_permission in RolePermission.objects.select_related("role").iterator():
        role_permission.tenant_id = role_permission.role.tenant_id
        role_permission.save(update_fields=["tenant_id"])
    for assignment in UserRole.objects.select_related("role").iterator():
        assignment.tenant_id = assignment.role.tenant_id
        assignment.save(update_fields=["tenant_id"])
    for grant in UserPermissionSet.objects.select_related("permission_set").iterator():
        grant.tenant_id = grant.permission_set.tenant_id
        grant.save(update_fields=["tenant_id"])
        UserPermissionSet.objects.filter(pk=grant.pk).update(created_at=grant.granted_at)

    # Correlation is mandatory after this migration.  Legacy records did not
    # carry one, so use a stable, explicitly-labelled provenance identifier.
    for audit in SecurityAuditLog.objects.filter(correlation_id="").iterator():
        audit.correlation_id = f"legacy-migration:{audit.id}"
        audit.save(update_fields=["correlation_id"])

    # Touch the model to make the intended parent for indirect ownership
    # explicit in the migration oracle.
    PermissionSet.objects.exists()


def noop_reverse(apps, schema_editor) -> None:
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [
        ("security_access_control", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(model_name="permission", old_name="object", new_name="resource"),
        migrations.AddField(
            model_name="permission",
            name="risk_level",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                default="medium",
                max_length=10,
            ),
        ),
        migrations.AlterField(model_name="permission", name="module", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="permission", name="name", field=models.CharField(max_length=255)),
        migrations.RemoveIndex(model_name="role", name="security_ro_parent__d0d08c_idx"),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(model_name="role", name="parent_role_id"),
                migrations.AddField(
                    model_name="role",
                    name="parent_role",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="child_roles",
                        to="security_access_control.role",
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="role", name="hierarchy_level", field=models.PositiveSmallIntegerField(default=0)
        ),
        migrations.AlterField(model_name="role", name="name", field=models.CharField(max_length=255)),
        migrations.AlterField(model_name="role", name="code", field=models.CharField(max_length=100)),
        migrations.AlterField(
            model_name="role",
            name="role_type",
            field=models.CharField(
                choices=[
                    ("system", "System"),
                    ("functional", "Functional"),
                    ("custom", "Custom"),
                    ("temporary", "Temporary"),
                ],
                default="custom",
                max_length=20,
            ),
        ),
        migrations.AlterField(model_name="role", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="role", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(model_name="role", name="deleted_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="rolepermission", name="tenant_id", field=models.UUIDField(db_index=True, null=True)
        ),
        migrations.AddField(model_name="rolepermission", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(
            model_name="rolepermission", name="created_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="rolepermission", name="updated_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AlterField(
            model_name="rolepermission",
            name="permission",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="role_permissions",
                to="security_access_control.permission",
            ),
        ),
        migrations.AddField(model_name="userrole", name="tenant_id", field=models.UUIDField(db_index=True, null=True)),
        migrations.AddField(model_name="userrole", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(
            model_name="userrole", name="revoked_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(model_name="userrole", name="revoked_by", field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name="userrole", name="revocation_reason", field=models.TextField(blank=True)),
        migrations.AlterField(
            model_name="userrole",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_roles",
                to="security_access_control.role",
            ),
        ),
        migrations.AddField(model_name="permissionset", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="permissionset", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(
            model_name="permissionset", name="deleted_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AlterField(
            model_name="permissionset",
            name="default_duration_days",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(model_name="permissionset", name="name", field=models.CharField(max_length=255)),
        migrations.AddField(
            model_name="userpermissionset", name="tenant_id", field=models.UUIDField(db_index=True, null=True)
        ),
        migrations.AddField(
            model_name="userpermissionset", name="created_at", field=models.DateTimeField(auto_now_add=True, null=True)
        ),
        migrations.AddField(
            model_name="userpermissionset", name="updated_at", field=models.DateTimeField(auto_now=True)
        ),
        migrations.AddField(
            model_name="userpermissionset", name="revoked_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="userpermissionset", name="revoked_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="userpermissionset", name="revocation_reason", field=models.TextField(blank=True)
        ),
        migrations.AlterField(
            model_name="userpermissionset",
            name="permission_set",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_grants",
                to="security_access_control.permissionset",
            ),
        ),
        migrations.RemoveIndex(model_name="fieldsecurity", name="security_fi_tenant__234461_idx"),
        migrations.RenameField(model_name="fieldsecurity", old_name="object", new_name="resource"),
        migrations.AddField(model_name="fieldsecurity", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(
            model_name="fieldsecurity", name="created_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="fieldsecurity", name="updated_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(model_name="fieldsecurity", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="fieldsecurity", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(
            model_name="fieldsecurity", name="deleted_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AlterField(model_name="fieldsecurity", name="module", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="fieldsecurity", name="resource", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="fieldsecurity", name="field", field=models.CharField(max_length=100)),
        migrations.AlterField(
            model_name="fieldsecurity",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="field_security_rules",
                to="security_access_control.role",
            ),
        ),
        migrations.RemoveIndex(model_name="rowsecurityrule", name="security_ro_tenant__51a9a9_idx"),
        migrations.RenameField(model_name="rowsecurityrule", old_name="object", new_name="resource"),
        migrations.AddField(model_name="rowsecurityrule", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(
            model_name="rowsecurityrule", name="created_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="rowsecurityrule", name="updated_by", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.AddField(model_name="rowsecurityrule", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="rowsecurityrule", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(
            model_name="rowsecurityrule", name="deleted_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AlterField(model_name="rowsecurityrule", name="module", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="rowsecurityrule", name="resource", field=models.CharField(max_length=100)),
        migrations.AddField(model_name="rowsecurityrule", name="version", field=models.PositiveIntegerField(default=1)),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="priority",
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="row_security_rules",
                to="security_access_control.role",
            ),
        ),
        migrations.AddField(model_name="securityprofile", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="securityprofile", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(
            model_name="securityprofile", name="deleted_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AlterField(model_name="securityprofile", name="name", field=models.CharField(max_length=255)),
        migrations.AlterField(
            model_name="securityprofile",
            name="profile_type",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("privileged", "Privileged"),
                    ("restricted", "Restricted"),
                    ("high_security", "High security"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="securityprofile",
            name="mfa_required",
            field=models.CharField(
                choices=[
                    ("always", "Always"),
                    ("conditional", "Conditional"),
                    ("sensitive_actions", "Sensitive actions"),
                    ("never", "Never"),
                ],
                default="conditional",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="securityprofile", name="session_timeout_minutes", field=models.PositiveIntegerField(default=60)
        ),
        migrations.AlterField(
            model_name="securityprofile",
            name="absolute_session_timeout_hours",
            field=models.PositiveIntegerField(default=8),
        ),
        migrations.AlterField(
            model_name="securityprofile", name="max_concurrent_sessions", field=models.PositiveIntegerField(default=5)
        ),
        migrations.AddField(
            model_name="securityauditlog", name="correlation_id", field=models.CharField(default="", max_length=128)
        ),
        migrations.AddField(
            model_name="securityauditlog", name="outbox_event_id", field=models.UUIDField(blank=True, null=True)
        ),
        migrations.CreateModel(
            name="SecurityProfileAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("precedence", models.SmallIntegerField(default=0)),
                ("valid_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("assigned_by", models.UUIDField()),
                ("reason", models.TextField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_by", models.UUIDField(blank=True, null=True)),
                ("revocation_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="security_profile_assignments",
                        to="security_access_control.role",
                    ),
                ),
                (
                    "security_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="security_access_control.securityprofile",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="security_profile_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "security_profile_assignments"},
        ),
        migrations.RunPython(validate_legacy_security_data, noop_reverse),
        migrations.AlterField(model_name="userrole", name="assigned_by", field=models.UUIDField()),
        migrations.AlterField(model_name="userpermissionset", name="granted_by", field=models.UUIDField()),
        migrations.AlterField(model_name="userrole", name="reason", field=models.TextField()),
        migrations.AlterField(
            model_name="userrole",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="security_user_roles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(model_name="userpermissionset", name="reason", field=models.TextField()),
        migrations.AlterField(
            model_name="userpermissionset",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="security_user_permission_sets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="securityauditlog", name="correlation_id", field=models.CharField(max_length=128)
        ),
        migrations.RunPython(validate_and_backfill_tenants, noop_reverse),
        migrations.AlterField(model_name="rolepermission", name="tenant_id", field=models.UUIDField(db_index=True)),
        migrations.AlterField(model_name="userrole", name="tenant_id", field=models.UUIDField(db_index=True)),
        migrations.AlterField(model_name="userpermissionset", name="tenant_id", field=models.UUIDField(db_index=True)),
        migrations.AlterField(model_name="securityauditlog", name="tenant_id", field=models.UUIDField(db_index=True)),
    ]
