"""Expand the legacy entity table without destroying legacy values."""

import decimal
import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="MasterEntityType",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("is_deleted", models.BooleanField(default=False, editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "key",
                    models.CharField(
                        max_length=64,
                        validators=[django.core.validators.RegexValidator(
                            "^[a-z][a-z0-9_]{1,63}$", "Use a lowercase snake-case key."
                        )],
                    ),
                ),
                ("display_name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("json_schema", models.JSONField(default=dict)),
                ("schema_version", models.PositiveIntegerField(default=1, editable=False)),
                ("required_fields", models.JSONField(blank=True, default=list)),
                ("sensitive_fields", models.JSONField(blank=True, default=list)),
                ("searchable_fields", models.JSONField(blank=True, default=list)),
                ("owner_module", models.CharField(default="master_data_management", max_length=100)),
                ("is_system", models.BooleanField(default=False, editable=False)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "mdm_entity_types",
                "ordering": ("key",),
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "key"), name="mdm_type_tenant_key_uniq"),
                    models.CheckConstraint(
                        condition=models.Q(("key__regex", "^[a-z][a-z0-9_]{1,63}$")),
                        name="mdm_type_key_format_ck",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("schema_version__gte", 1)),
                        name="mdm_type_schema_ver_gte_1_ck",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("is_system", False)) | models.Q(("is_deleted", False)),
                        name="mdm_type_system_not_deleted_ck",
                    ),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "is_active", "key"], name="mdm_type_active_key_idx"),
                    models.Index(fields=["tenant_id", "owner_module"], name="mdm_type_owner_idx"),
                    models.Index(fields=["tenant_id", "updated_at"], name="mdm_type_updated_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="created_by",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="updated_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="entity_type_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entities",
                to="master_data_management.masterentitytype",
            ),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="source_system",
            field=models.CharField(default="manual", max_length=100),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="source_record_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("pending_review", "Pending review"),
                    ("merged", "Merged"),
                    ("archived", "Archived"),
                ],
                default="active",
                editable=False,
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="quality_score",
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), editable=False, max_digits=5),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="quality_evaluated_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="golden_record",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="golden_members",
                to="master_data_management.masterdataentity",
            ),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="is_golden",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="version",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="is_deleted",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="masterdataentity",
            name="deleted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
