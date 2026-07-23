"""Align database guard rails with configurable tenant policy bounds."""

from django.db import migrations, models
from django.db.models import Q

import src.modules.security_access_control.models


class Migration(migrations.Migration):
    dependencies = [("security_access_control", "0007_tenant_security_configuration")]

    operations = [
        migrations.RemoveConstraint(model_name="permissionset", name="sec_permset_duration_range"),
        migrations.AddConstraint(
            model_name="permissionset",
            constraint=models.CheckConstraint(
                condition=Q(default_duration_days__isnull=True)
                | Q(default_duration_days__gte=1, default_duration_days__lte=3650),
                name="sec_permset_duration_range",
            ),
        ),
        migrations.RemoveConstraint(model_name="securityprofile", name="sec_profile_session_timeout"),
        migrations.RemoveConstraint(model_name="securityprofile", name="sec_profile_absolute_timeout"),
        migrations.RemoveConstraint(model_name="securityprofile", name="sec_profile_session_count"),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                condition=Q(session_timeout_minutes__gte=1, session_timeout_minutes__lte=10080),
                name="sec_profile_session_timeout",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                condition=Q(absolute_session_timeout_hours__gte=1, absolute_session_timeout_hours__lte=744),
                name="sec_profile_absolute_timeout",
            ),
        ),
        migrations.AddConstraint(
            model_name="securityprofile",
            constraint=models.CheckConstraint(
                condition=Q(max_concurrent_sessions__gte=1, max_concurrent_sessions__lte=1000),
                name="sec_profile_session_count",
            ),
        ),
        migrations.AlterField(
            model_name="fieldsecurity",
            name="visibility",
            field=models.CharField(
                choices=[("visible", "Visible"), ("hidden", "Hidden"), ("masked", "Masked"), ("redacted", "Redacted")],
                default=src.modules.security_access_control.models.default_field_visibility,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="fieldsecurity",
            name="edit_control",
            field=models.CharField(
                choices=[("read_only", "Read only"), ("editable", "Editable"), ("required", "Required")],
                default=src.modules.security_access_control.models.default_field_edit_control,
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
                default=src.modules.security_access_control.models.default_row_rule_type,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="priority",
            field=models.SmallIntegerField(default=src.modules.security_access_control.models.default_row_rule_priority),
        ),
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
                default=src.modules.security_access_control.models.default_profile_type,
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
                default=src.modules.security_access_control.models.default_mfa_requirement,
                max_length=20,
            ),
        ),
        migrations.AlterField(model_name="securityprofile", name="session_timeout_minutes", field=models.PositiveIntegerField(default=src.modules.security_access_control.models.default_session_timeout_minutes)),
        migrations.AlterField(model_name="securityprofile", name="absolute_session_timeout_hours", field=models.PositiveIntegerField(default=src.modules.security_access_control.models.default_absolute_session_timeout_hours)),
        migrations.AlterField(model_name="securityprofile", name="max_concurrent_sessions", field=models.PositiveIntegerField(default=src.modules.security_access_control.models.default_max_concurrent_sessions)),
        migrations.AlterField(model_name="securityprofile", name="download_allowed", field=models.BooleanField(default=src.modules.security_access_control.models.default_download_allowed)),
        migrations.AlterField(model_name="securityprofile", name="print_allowed", field=models.BooleanField(default=src.modules.security_access_control.models.default_print_allowed)),
        migrations.AlterField(model_name="securityprofile", name="copy_paste_allowed", field=models.BooleanField(default=src.modules.security_access_control.models.default_copy_paste_allowed)),
        migrations.AlterField(model_name="securityprofile", name="mobile_access_allowed", field=models.BooleanField(default=src.modules.security_access_control.models.default_mobile_access_allowed)),
        migrations.AlterField(model_name="securityprofile", name="login_notification", field=models.BooleanField(default=src.modules.security_access_control.models.default_login_notification)),
        migrations.AlterField(model_name="securityprofile", name="access_notification", field=models.BooleanField(default=src.modules.security_access_control.models.default_access_notification)),
        migrations.AlterField(model_name="securityprofileassignment", name="precedence", field=models.SmallIntegerField(default=src.modules.security_access_control.models.default_profile_assignment_precedence)),
    ]
