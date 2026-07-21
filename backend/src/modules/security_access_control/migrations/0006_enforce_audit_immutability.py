"""Remove normalized legacy columns and enforce audit immutability in SQL."""

from __future__ import annotations

import json

from django.db import migrations, models


def noop(apps, schema_editor) -> None:
    del apps, schema_editor


def reconstruct_permission_arrays(apps, schema_editor) -> None:
    del schema_editor
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    Membership = apps.get_model("security_access_control", "PermissionSetPermission")
    for permission_set in PermissionSet.objects.order_by("id").iterator():
        permission_set.permission_ids = [
            str(value)
            for value in Membership.objects.filter(
                permission_set_id=permission_set.id,
                removed_at__isnull=True,
            )
            .order_by("permission_id")
            .values_list("permission_id", flat=True)
        ]
        permission_set.save(update_fields=["permission_ids"])


def reconstruct_legacy_predicates(apps, schema_editor) -> None:
    del schema_editor
    RowSecurityRule = apps.get_model("security_access_control", "RowSecurityRule")
    for rule in RowSecurityRule.objects.order_by("id").iterator():
        rule.legacy_filter_criteria = json.dumps(
            rule.filter_criteria,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        rule.save(update_fields=["legacy_filter_criteria"])


INSTALL_TRIGGER = """
CREATE OR REPLACE FUNCTION security_audit_logs_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'security audit records are immutable' USING ERRCODE = '55000';
END;
$$;
DROP TRIGGER IF EXISTS security_audit_logs_immutable ON security_audit_logs;
CREATE TRIGGER security_audit_logs_immutable
BEFORE UPDATE OR DELETE ON security_audit_logs
FOR EACH ROW EXECUTE FUNCTION security_audit_logs_reject_mutation();
"""

REMOVE_TRIGGER = """
DROP TRIGGER IF EXISTS security_audit_logs_immutable ON security_audit_logs;
DROP FUNCTION IF EXISTS security_audit_logs_reject_mutation();
"""


def install_trigger(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_TRIGGER)


def remove_trigger(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REMOVE_TRIGGER)


class Migration(migrations.Migration):
    dependencies = [("security_access_control", "0005_constraints_indexes_rls")]

    operations = [
        migrations.RunPython(noop, reconstruct_permission_arrays),
        migrations.RemoveField(model_name="permissionset", name="permission_ids"),
        migrations.RunPython(noop, reconstruct_legacy_predicates),
        migrations.RemoveField(model_name="rowsecurityrule", name="legacy_filter_criteria"),
        migrations.AlterField(
            model_name="userpermissionset",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="fieldsecurity",
            name="visibility",
            field=models.CharField(
                choices=[("visible", "Visible"), ("hidden", "Hidden"), ("masked", "Masked"), ("redacted", "Redacted")],
                default="visible",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="fieldsecurity",
            name="edit_control",
            field=models.CharField(
                choices=[("read_only", "Read only"), ("editable", "Editable"), ("required", "Required")],
                default="editable",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="rule_type",
            field=models.CharField(
                choices=[
                    ("ownership", "Ownership"),
                    ("hierarchy", "Hierarchy"),
                    ("attribute", "Attribute"),
                    ("criteria", "Criteria"),
                ],
                default="ownership",
                max_length=20,
            ),
        ),
        migrations.AlterField(model_name="securityauditlog", name="action", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="securityauditlog", name="actor_id", field=models.UUIDField()),
        migrations.AlterField(
            model_name="securityauditlog", name="resource_type", field=models.CharField(max_length=100)
        ),
        migrations.AlterField(
            model_name="securityauditlog", name="timestamp", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.RemoveIndex(model_name="role", name="security_ro_tenant__6d1016_idx"),
        migrations.RemoveIndex(model_name="role", name="security_ro_role_ty_a81620_idx"),
        migrations.RemoveIndex(model_name="permissionset", name="security_pe_tenant__ac1166_idx"),
        migrations.RemoveIndex(model_name="permission", name="security_pe_module_f68d6a_idx"),
        migrations.RemoveIndex(model_name="userrole", name="security_us_user_id_e10708_idx"),
        migrations.RemoveIndex(model_name="userrole", name="security_us_role_id_9b94c7_idx"),
        migrations.RemoveIndex(model_name="userrole", name="security_us_valid_f_42f471_idx"),
        migrations.RemoveIndex(model_name="userpermissionset", name="security_us_user_id_adcb23_idx"),
        migrations.RemoveIndex(model_name="userpermissionset", name="security_us_expires_5a92ec_idx"),
        migrations.RemoveIndex(model_name="rowsecurityrule", name="security_ro_role_id_bf5b98_idx"),
        migrations.RemoveIndex(model_name="rowsecurityrule", name="security_ro_priorit_ce5387_idx"),
        migrations.RemoveIndex(model_name="rolepermission", name="security_ro_role_id_2c38a7_idx"),
        migrations.RemoveIndex(model_name="rolepermission", name="security_ro_permiss_b50b52_idx"),
        migrations.RemoveIndex(model_name="fieldsecurity", name="security_fi_role_id_fb6927_idx"),
        migrations.RemoveIndex(model_name="securityprofile", name="security_se_tenant__8609b3_idx"),
        migrations.RemoveIndex(model_name="securityprofile", name="security_se_profile_1b8a9a_idx"),
        migrations.RemoveIndex(model_name="securityauditlog", name="security_au_tenant__78b36d_idx"),
        migrations.RemoveIndex(model_name="securityauditlog", name="security_au_actor_i_1e8ca7_idx"),
        migrations.RemoveIndex(model_name="securityauditlog", name="security_au_resourc_286b6b_idx"),
        migrations.RemoveIndex(model_name="securityauditlog", name="security_au_action_0492cf_idx"),
        migrations.RemoveIndex(model_name="securityauditlog", name="security_au_decisio_60de10_idx"),
        migrations.AlterModelOptions(name="permission", options={"ordering": ("module", "resource", "action")}),
        migrations.AlterModelOptions(name="role", options={"ordering": ("name", "id")}),
        migrations.AlterModelOptions(name="userrole", options={"ordering": ("-valid_from", "id")}),
        migrations.AlterModelOptions(name="permissionset", options={"ordering": ("name", "id")}),
        migrations.AlterModelOptions(name="userpermissionset", options={"ordering": ("-granted_at", "id")}),
        migrations.AlterModelOptions(
            name="rowsecurityrule", options={"ordering": ("-priority", "module", "resource", "id")}
        ),
        migrations.AlterModelOptions(name="securityprofile", options={"ordering": ("name", "id")}),
        migrations.AlterModelOptions(
            name="securityprofileassignment", options={"ordering": ("-precedence", "-valid_from", "id")}
        ),
        migrations.AlterModelOptions(name="securityauditlog", options={"ordering": ("-timestamp", "-id")}),
        migrations.RunPython(install_trigger, remove_trigger),
    ]
