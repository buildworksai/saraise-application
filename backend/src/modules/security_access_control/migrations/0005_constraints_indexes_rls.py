"""Install security integrity constraints, production indexes, and typed RLS."""

from __future__ import annotations

from django.db import migrations, models
from django.db.models import F, Q

TENANT_TABLES = (
    "security_roles",
    "security_role_permissions",
    "security_user_roles",
    "security_permission_sets",
    "security_permission_set_permissions",
    "security_user_permission_sets",
    "security_field_security",
    "security_row_security_rules",
    "security_security_profiles",
    "security_profile_assignments",
    "security_audit_logs",
)

INDEX_SPECS = (
    ("sec_role_active_type_idx", "security_roles", "tenant_id, is_active, role_type"),
    ("sec_role_tenant_parent_idx", "security_roles", "tenant_id, parent_role_id"),
    ("sec_role_tenant_name_idx", "security_roles", "tenant_id, name"),
    ("sec_role_perm_decision_idx", "security_role_permissions", "tenant_id, role_id, is_granted"),
    ("sec_user_role_valid_idx", "security_user_roles", "tenant_id, user_id, valid_from, valid_until"),
    ("sec_user_role_revoke_idx", "security_user_roles", "tenant_id, role_id, revoked_at"),
    ("sec_permission_code_idx", "security_permissions", "module, resource, action"),
    ("sec_permset_active_name_idx", "security_permission_sets", "tenant_id, is_active, name"),
    ("sec_permset_member_idx", "security_permission_set_permissions", "tenant_id, permission_set_id, removed_at"),
    ("sec_user_permset_expiry_idx", "security_user_permission_sets", "tenant_id, user_id, expires_at"),
    ("sec_user_permset_revoke_idx", "security_user_permission_sets", "tenant_id, permission_set_id, revoked_at"),
    ("sec_field_resource_idx", "security_field_security", "tenant_id, module, resource, is_active"),
    ("sec_field_role_idx", "security_field_security", "tenant_id, role_id"),
    ("sec_row_resource_idx", "security_row_security_rules", "tenant_id, module, resource, is_active, priority"),
    ("sec_row_role_idx", "security_row_security_rules", "tenant_id, role_id"),
    ("sec_profile_type_active_idx", "security_security_profiles", "tenant_id, profile_type, is_active"),
    ("sec_profile_assign_user_idx", "security_profile_assignments", "tenant_id, user_id, revoked_at"),
    ("sec_profile_assign_role_idx", "security_profile_assignments", "tenant_id, role_id, revoked_at"),
    ("sec_audit_tenant_time_idx", "security_audit_logs", "tenant_id, timestamp"),
    ("sec_audit_actor_time_idx", "security_audit_logs", "tenant_id, actor_id, timestamp"),
    ("sec_audit_resource_idx", "security_audit_logs", "tenant_id, resource_type, resource_id"),
    ("sec_audit_action_time_idx", "security_audit_logs", "tenant_id, action, timestamp"),
    ("sec_audit_decision_time_idx", "security_audit_logs", "tenant_id, decision, timestamp"),
    ("sec_audit_correlation_idx", "security_audit_logs", "tenant_id, correlation_id"),
)

COMPOSITE_FOREIGN_KEYS = (
    ("security_roles", "sac_role_parent_tenant_fk", "tenant_id, parent_role_id", "security_roles"),
    ("security_role_permissions", "sac_roleperm_role_tenant_fk", "tenant_id, role_id", "security_roles"),
    ("security_user_roles", "sac_userrole_role_tenant_fk", "tenant_id, role_id", "security_roles"),
    (
        "security_permission_set_permissions",
        "sac_member_set_tenant_fk",
        "tenant_id, permission_set_id",
        "security_permission_sets",
    ),
    (
        "security_user_permission_sets",
        "sac_grant_set_tenant_fk",
        "tenant_id, permission_set_id",
        "security_permission_sets",
    ),
    ("security_field_security", "sac_field_role_tenant_fk", "tenant_id, role_id", "security_roles"),
    ("security_row_security_rules", "sac_row_role_tenant_fk", "tenant_id, role_id", "security_roles"),
    (
        "security_profile_assignments",
        "sac_assignment_profile_fk",
        "tenant_id, security_profile_id",
        "security_security_profiles",
    ),
    ("security_profile_assignments", "sac_assignment_role_fk", "tenant_id, role_id", "security_roles"),
)


def create_concurrent_indexes(apps, schema_editor) -> None:
    del apps
    concurrently = " CONCURRENTLY" if schema_editor.connection.vendor == "postgresql" else ""
    for name, table, columns in INDEX_SPECS:
        schema_editor.execute(
            f"CREATE INDEX{concurrently} IF NOT EXISTS {schema_editor.quote_name(name)} "
            f"ON {schema_editor.quote_name(table)} ({columns})"
        )


def drop_concurrent_indexes(apps, schema_editor) -> None:
    del apps
    concurrently = " CONCURRENTLY" if schema_editor.connection.vendor == "postgresql" else ""
    for name, _, _ in reversed(INDEX_SPECS):
        schema_editor.execute(f"DROP INDEX{concurrently} IF EXISTS {schema_editor.quote_name(name)}")


def add_composite_foreign_keys(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, constraint, _, _ in COMPOSITE_FOREIGN_KEYS:
        schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    for table in ("security_roles", "security_permission_sets", "security_security_profiles"):
        constraint = f"{table}_tenant_id_id_uniq"
        schema_editor.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint}" UNIQUE (tenant_id, id)')
    for table, constraint, columns, target in COMPOSITE_FOREIGN_KEYS:
        schema_editor.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint}" FOREIGN KEY ({columns}) '
            f'REFERENCES "{target}" (tenant_id, id) DEFERRABLE INITIALLY DEFERRED'
        )


def drop_composite_foreign_keys(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, constraint, _, _ in reversed(COMPOSITE_FOREIGN_KEYS):
        schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    for table in reversed(("security_roles", "security_permission_sets", "security_security_profiles")):
        constraint = f"{table}_tenant_id_id_uniq"
        schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')


def enable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")


def disable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}"[:63])
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY")


STATE_INDEXES = [
    migrations.AddIndex(
        model_name=model_name,
        index=models.Index(fields=fields, name=name),
    )
    for name, model_name, fields in (
        ("sec_role_active_type_idx", "role", ["tenant_id", "is_active", "role_type"]),
        ("sec_role_tenant_parent_idx", "role", ["tenant_id", "parent_role"]),
        ("sec_role_tenant_name_idx", "role", ["tenant_id", "name"]),
        ("sec_role_perm_decision_idx", "rolepermission", ["tenant_id", "role", "is_granted"]),
        ("sec_user_role_valid_idx", "userrole", ["tenant_id", "user", "valid_from", "valid_until"]),
        ("sec_user_role_revoke_idx", "userrole", ["tenant_id", "role", "revoked_at"]),
        ("sec_permission_code_idx", "permission", ["module", "resource", "action"]),
        ("sec_permset_active_name_idx", "permissionset", ["tenant_id", "is_active", "name"]),
        ("sec_permset_member_idx", "permissionsetpermission", ["tenant_id", "permission_set", "removed_at"]),
        ("sec_user_permset_expiry_idx", "userpermissionset", ["tenant_id", "user", "expires_at"]),
        ("sec_user_permset_revoke_idx", "userpermissionset", ["tenant_id", "permission_set", "revoked_at"]),
        ("sec_field_resource_idx", "fieldsecurity", ["tenant_id", "module", "resource", "is_active"]),
        ("sec_field_role_idx", "fieldsecurity", ["tenant_id", "role"]),
        ("sec_row_resource_idx", "rowsecurityrule", ["tenant_id", "module", "resource", "is_active", "priority"]),
        ("sec_row_role_idx", "rowsecurityrule", ["tenant_id", "role"]),
        ("sec_profile_type_active_idx", "securityprofile", ["tenant_id", "profile_type", "is_active"]),
        ("sec_profile_assign_user_idx", "securityprofileassignment", ["tenant_id", "user", "revoked_at"]),
        ("sec_profile_assign_role_idx", "securityprofileassignment", ["tenant_id", "role", "revoked_at"]),
        ("sec_audit_tenant_time_idx", "securityauditlog", ["tenant_id", "timestamp"]),
        ("sec_audit_actor_time_idx", "securityauditlog", ["tenant_id", "actor_id", "timestamp"]),
        ("sec_audit_resource_idx", "securityauditlog", ["tenant_id", "resource_type", "resource_id"]),
        ("sec_audit_action_time_idx", "securityauditlog", ["tenant_id", "action", "timestamp"]),
        ("sec_audit_decision_time_idx", "securityauditlog", ["tenant_id", "decision", "timestamp"]),
        ("sec_audit_correlation_idx", "securityauditlog", ["tenant_id", "correlation_id"]),
    )
]


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("security_access_control", "0004_safe_row_rule_predicates"),
    ]

    operations = [
        migrations.AlterUniqueTogether(name="role", unique_together=set()),
        migrations.AlterUniqueTogether(name="permission", unique_together=set()),
        migrations.AlterUniqueTogether(name="rolepermission", unique_together=set()),
        migrations.AlterUniqueTogether(name="userrole", unique_together=set()),
        migrations.AlterUniqueTogether(name="fieldsecurity", unique_together=set()),
        migrations.AddConstraint(
            model_name="permission",
            constraint=models.UniqueConstraint(
                fields=("module", "resource", "action"), name="sec_permission_code_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "code"), condition=Q(is_deleted=False), name="sec_role_tenant_code_active_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.CheckConstraint(check=Q(hierarchy_level__gte=0), name="sec_role_hierarchy_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.CheckConstraint(
                check=Q(parent_role__isnull=True) | ~Q(parent_role=F("id")), name="sec_role_parent_not_self"
            ),
        ),
        migrations.AddConstraint(
            model_name="rolepermission",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "role", "permission"), name="sec_role_permission_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.CheckConstraint(
                check=Q(valid_until__isnull=True) | Q(valid_until__gt=F("valid_from")),
                name="sec_user_role_valid_interval",
            ),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "user", "role"),
                condition=Q(revoked_at__isnull=True),
                name="sec_user_role_active_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="permissionset",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="sec_permset_tenant_name_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="permissionset",
            constraint=models.CheckConstraint(
                check=Q(default_duration_days__isnull=True)
                | (Q(default_duration_days__gte=1) & Q(default_duration_days__lte=365)),
                name="sec_permset_duration_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="permissionsetpermission",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "permission_set", "permission"),
                condition=Q(removed_at__isnull=True),
                name="sec_permset_member_active_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="userpermissionset",
            constraint=models.CheckConstraint(
                check=Q(expires_at__gt=F("granted_at")), name="sec_user_permset_interval"
            ),
        ),
        migrations.AddConstraint(
            model_name="userpermissionset",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "user", "permission_set"),
                condition=Q(revoked_at__isnull=True),
                name="sec_user_permset_active_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="fieldsecurity",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "module", "resource", "field", "role"),
                condition=Q(is_active=True, is_deleted=False),
                name="sec_field_rule_active_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="fieldsecurity",
            constraint=models.CheckConstraint(
                check=Q(visibility="masked", mask_pattern__gt="") | ~Q(visibility="masked"),
                name="sec_field_mask_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="rowsecurityrule",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "module", "resource", "role", "priority", "version"),
                name="sec_row_rule_version_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="sec_profile_tenant_name_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                check=Q(session_timeout_minutes__gte=5) & Q(session_timeout_minutes__lte=1440),
                name="sec_profile_session_timeout",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                check=Q(absolute_session_timeout_hours__gte=1) & Q(absolute_session_timeout_hours__lte=168),
                name="sec_profile_absolute_timeout",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                check=Q(max_concurrent_sessions__gte=1) & Q(max_concurrent_sessions__lte=100),
                name="sec_profile_session_count",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofileassignment",
            constraint=models.CheckConstraint(
                check=Q(user__isnull=False, role__isnull=True) | Q(user__isnull=True, role__isnull=False),
                name="sec_profile_assignment_one_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofileassignment",
            constraint=models.CheckConstraint(
                check=Q(valid_until__isnull=True) | Q(valid_until__gt=F("valid_from")),
                name="sec_profile_assignment_interval",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofileassignment",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "user", "security_profile"),
                condition=Q(revoked_at__isnull=True, user__isnull=False),
                name="sec_profile_assignment_user_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofileassignment",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "role", "security_profile"),
                condition=Q(revoked_at__isnull=True, role__isnull=False),
                name="sec_profile_assignment_role_uniq",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(create_concurrent_indexes, drop_concurrent_indexes)],
            state_operations=STATE_INDEXES,
        ),
        migrations.RunPython(add_composite_foreign_keys, drop_composite_foreign_keys),
        migrations.RunPython(enable_rls, disable_rls),
    ]
