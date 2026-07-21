"""Create the declarative customization domain without rewriting legacy data."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

import src.modules.customization_framework.models


SAME_TENANT_RELATIONSHIPS = (
    ("customization_field_values", "definition_id", "customization_field_definitions"),
    ("customization_form_layout_versions", "form_id", "customization_form_definitions"),
    ("customization_business_rule_versions", "rule_id", "customization_business_rules"),
    ("customization_rule_executions", "rule_id", "customization_business_rules"),
    ("customization_rule_executions", "rule_version_id", "customization_business_rule_versions"),
)


def make_legacy_table_read_only(apps, schema_editor) -> None:
    """Preserve the physical scaffold table while rejecting future writes."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        r"""
        CREATE OR REPLACE FUNCTION customization_legacy_reject_write()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'legacy customization resources are read-only'
                USING ERRCODE = '55000';
        END;
        $$;
        DROP TRIGGER IF EXISTS customization_legacy_read_only
            ON customization_framework_resources;
        CREATE TRIGGER customization_legacy_read_only
        BEFORE INSERT OR UPDATE OR DELETE ON customization_framework_resources
        FOR EACH ROW EXECUTE FUNCTION customization_legacy_reject_write();
        """
    )


def restore_legacy_table_writes(apps, schema_editor) -> None:
    """Remove only the legacy write guard installed by this migration."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        r"""
        DROP TRIGGER IF EXISTS customization_legacy_read_only
            ON customization_framework_resources;
        DROP FUNCTION IF EXISTS customization_legacy_reject_write();
        """
    )


def install_relationship_guards(apps, schema_editor) -> None:
    """Install database guards for every tenant-owned foreign-key edge."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        r"""
        CREATE OR REPLACE FUNCTION customization_require_same_tenant()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_id UUID;
            parent_tenant UUID;
        BEGIN
            parent_id := (to_jsonb(NEW) ->> TG_ARGV[0])::UUID;
            IF parent_id IS NULL THEN
                RETURN NEW;
            END IF;
            EXECUTE format('SELECT tenant_id FROM %I WHERE id = $1', TG_ARGV[1])
               INTO parent_tenant
              USING parent_id;
            IF parent_tenant IS NULL OR parent_tenant <> NEW.tenant_id THEN
                RAISE EXCEPTION 'cross-tenant customization relationship rejected'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE OR REPLACE FUNCTION customization_require_execution_version()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            version_rule_id UUID;
        BEGIN
            SELECT rule_id INTO version_rule_id
              FROM customization_business_rule_versions
             WHERE id = NEW.rule_version_id;
            IF version_rule_id IS NULL OR version_rule_id <> NEW.rule_id THEN
                RAISE EXCEPTION 'rule execution version does not belong to rule'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    for child_table, fk_column, parent_table in SAME_TENANT_RELATIONSHIPS:
        trigger_name = f"cust_same_tenant_{fk_column}_{child_table[-8:]}"
        quoted_trigger = schema_editor.quote_name(trigger_name)
        quoted_child = schema_editor.quote_name(child_table)
        quoted_fk = schema_editor.quote_name(fk_column)
        schema_editor.execute(
            f"""
            DROP TRIGGER IF EXISTS {quoted_trigger} ON {quoted_child};
            CREATE TRIGGER {quoted_trigger}
            BEFORE INSERT OR UPDATE OF tenant_id, {quoted_fk} ON {quoted_child}
            FOR EACH ROW EXECUTE FUNCTION customization_require_same_tenant(
                '{fk_column}', '{parent_table}'
            );
            """
        )
    schema_editor.execute(
        """
        DROP TRIGGER IF EXISTS cust_execution_version_rule
            ON customization_rule_executions;
        CREATE TRIGGER cust_execution_version_rule
        BEFORE INSERT OR UPDATE OF rule_id, rule_version_id
            ON customization_rule_executions
        FOR EACH ROW EXECUTE FUNCTION customization_require_execution_version();
        """
    )


def remove_relationship_guards(apps, schema_editor) -> None:
    """Remove only the cross-tenant guards owned by this module."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS cust_execution_version_rule "
        "ON customization_rule_executions;"
    )
    for child_table, fk_column, _parent_table in reversed(SAME_TENANT_RELATIONSHIPS):
        trigger_name = f"cust_same_tenant_{fk_column}_{child_table[-8:]}"
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger_name)} "
            f"ON {schema_editor.quote_name(child_table)};"
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS customization_require_execution_version();")
    schema_editor.execute("DROP FUNCTION IF EXISTS customization_require_same_tenant();")


class Migration(migrations.Migration):
    dependencies = [("customization_framework", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(make_legacy_table_read_only, restore_legacy_table_writes)
            ],
            state_operations=[migrations.DeleteModel(name="CustomizationFrameworkResource")],
        ),
        migrations.CreateModel(
            name="CustomFieldDefinition",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("deleted_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("lock_version", models.PositiveIntegerField(default=1, editable=False)),
                ("key", models.SlugField(max_length=100)),
                ("label", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("owner_module", models.SlugField(max_length=100)),
                ("target_resource", models.SlugField(max_length=120)),
                ("target_contract_version", models.CharField(max_length=32)),
                (
                    "data_type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("long_text", "Long text"),
                            ("integer", "Integer"),
                            ("decimal", "Decimal"),
                            ("boolean", "Boolean"),
                            ("date", "Date"),
                            ("datetime", "Datetime"),
                            ("uuid", "UUID"),
                            ("choice", "Choice"),
                            ("multi_choice", "Multiple choice"),
                            ("json", "JSON"),
                        ],
                        max_length=20,
                    ),
                ),
                ("required", models.BooleanField(default=False)),
                ("searchable", models.BooleanField(default=False)),
                ("default_value", models.JSONField(blank=True, null=True)),
                ("validation_schema", models.JSONField(blank=True, default=dict)),
                ("presentation_schema", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("deprecated", "Deprecated"),
                            ("retired", "Retired"),
                        ],
                        default="draft",
                        editable=False,
                        max_length=16,
                    ),
                ),
                ("activated_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("deprecated_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("retired_at", models.DateTimeField(blank=True, editable=False, null=True)),
            ],
            options={
                "db_table": "customization_field_definitions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "owner_module", "target_resource", "status"],
                        name="cust_fd_tgt_status_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "status", "updated_at"],
                        name="cust_fd_status_upd_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=("tenant_id", "owner_module", "target_resource", "key"),
                        name="cust_fd_live_target_key_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(key__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                        name="cust_fd_key_lower_slug_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                status="draft",
                                activated_at__isnull=True,
                                deprecated_at__isnull=True,
                                retired_at__isnull=True,
                            )
                            | models.Q(
                                status="active",
                                activated_at__isnull=False,
                                deprecated_at__isnull=True,
                                retired_at__isnull=True,
                            )
                            | models.Q(
                                status="deprecated",
                                activated_at__isnull=False,
                                deprecated_at__isnull=False,
                                retired_at__isnull=True,
                            )
                            | models.Q(
                                status="retired",
                                activated_at__isnull=False,
                                deprecated_at__isnull=False,
                                retired_at__isnull=False,
                            )
                        ),
                        name="cust_fd_lifecycle_timestamps_ck",
                    ),
                ],
            },
            bases=(src.modules.customization_framework.models.SoftDeleteOnlyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="CustomFieldValue",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("target_record_id", models.UUIDField()),
                ("value", models.JSONField()),
                ("definition_revision", models.PositiveIntegerField(editable=False)),
                (
                    "source",
                    models.CharField(
                        choices=[("ui", "UI"), ("api", "API"), ("import", "Import"), ("rule", "Rule")],
                        max_length=12,
                    ),
                ),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("deleted_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("lock_version", models.PositiveIntegerField(default=1, editable=False)),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="values",
                        to="customization_framework.customfielddefinition",
                    ),
                ),
            ],
            options={
                "db_table": "customization_field_values",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "target_record_id"],
                        name="cust_fv_tenant_record_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "definition", "updated_at"],
                        name="cust_fv_tenant_def_updated_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=("tenant_id", "definition", "target_record_id"),
                        name="cust_fv_live_target_uniq",
                    )
                ],
            },
            bases=(src.modules.customization_framework.models.SoftDeleteOnlyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="FormDefinition",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("deleted_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("lock_version", models.PositiveIntegerField(default=1, editable=False)),
                ("key", models.SlugField(max_length=100)),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("owner_module", models.SlugField(max_length=100)),
                ("target_resource", models.SlugField(max_length=120)),
                ("target_contract_version", models.CharField(max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                        default="draft",
                        editable=False,
                        max_length=12,
                    ),
                ),
                ("published_version", models.PositiveIntegerField(blank=True, editable=False, null=True)),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("published_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("archived_at", models.DateTimeField(blank=True, editable=False, null=True)),
            ],
            options={
                "db_table": "customization_form_definitions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "owner_module", "target_resource", "status"],
                        name="cust_form_tgt_status_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "status", "updated_at"],
                        name="cust_form_status_upd_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=("tenant_id", "owner_module", "target_resource", "key"),
                        name="cust_form_live_target_key_uniq",
                    ),
                    models.CheckConstraint(
                        condition=(
                            ~models.Q(status="published")
                            | models.Q(
                                published_version__isnull=False,
                                published_at__isnull=False,
                                published_by__isnull=False,
                            )
                        ),
                        name="cust_form_published_fields_ck",
                    ),
                ],
            },
            bases=(src.modules.customization_framework.models.SoftDeleteOnlyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="FormLayoutVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(editable=False)),
                ("schema_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                ("layout", models.JSONField()),
                ("content_hash", models.CharField(editable=False, max_length=64)),
                ("change_summary", models.CharField(max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate"),
                            ("published", "Published"),
                            ("superseded", "Superseded"),
                            ("rejected", "Rejected"),
                        ],
                        default="candidate",
                        editable=False,
                        max_length=12,
                    ),
                ),
                ("validation_errors", models.JSONField(blank=True, default=list, editable=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("published_by", models.UUIDField(blank=True, editable=False, null=True)),
                (
                    "form",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="layout_versions",
                        to="customization_framework.formdefinition",
                    ),
                ),
            ],
            options={
                "db_table": "customization_form_layout_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "form", "status", "version"],
                        name="cust_layout_form_stat_ver_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "form", "version"),
                        name="cust_layout_tenant_form_ver_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("tenant_id", "form", "content_hash"),
                        name="cust_layout_tenant_form_hash_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(status="published"),
                        fields=("tenant_id", "form"),
                        name="cust_layout_one_published_uniq",
                    ),
                ],
            },
            bases=(src.modules.customization_framework.models.ImmutableVersionMixin, models.Model),
        ),
        migrations.CreateModel(
            name="BusinessRule",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("deleted_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
                ("lock_version", models.PositiveIntegerField(default=1, editable=False)),
                ("key", models.SlugField(max_length=100)),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("owner_module", models.SlugField(max_length=100)),
                ("target_resource", models.SlugField(max_length=120)),
                ("target_contract_version", models.CharField(max_length=32)),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("validate", "Validate"),
                            ("before_create", "Before create"),
                            ("before_update", "Before update"),
                            ("form_change", "Form change"),
                        ],
                        max_length=20,
                    ),
                ),
                ("priority", models.PositiveSmallIntegerField(default=100)),
                ("stop_on_match", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("published", "Published"),
                            ("paused", "Paused"),
                            ("retired", "Retired"),
                        ],
                        default="draft",
                        editable=False,
                        max_length=12,
                    ),
                ),
                ("published_version", models.PositiveIntegerField(blank=True, editable=False, null=True)),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("published_by", models.UUIDField(blank=True, editable=False, null=True)),
            ],
            options={
                "db_table": "customization_business_rules",
                "indexes": [
                    models.Index(
                        fields=[
                            "tenant_id",
                            "owner_module",
                            "target_resource",
                            "trigger",
                            "status",
                            "priority",
                        ],
                        name="cust_rule_tgt_trig_stat_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "status", "updated_at"],
                        name="cust_rule_status_upd_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=("tenant_id", "owner_module", "target_resource", "key"),
                        name="cust_rule_live_target_key_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=(
                            "tenant_id",
                            "owner_module",
                            "target_resource",
                            "trigger",
                            "priority",
                            "key",
                        ),
                        name="cust_rule_live_trigger_priority_key_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(priority__gte=1, priority__lte=1000),
                        name="cust_rule_priority_range_ck",
                    ),
                ],
            },
            bases=(src.modules.customization_framework.models.SoftDeleteOnlyMixin, models.Model),
        ),
        migrations.CreateModel(
            name="BusinessRuleVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(editable=False)),
                ("language_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                ("condition_ast", models.JSONField()),
                ("action_ast", models.JSONField()),
                ("dependencies", models.JSONField(blank=True, default=list)),
                ("content_hash", models.CharField(editable=False, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate"),
                            ("published", "Published"),
                            ("superseded", "Superseded"),
                            ("rejected", "Rejected"),
                        ],
                        default="candidate",
                        editable=False,
                        max_length=12,
                    ),
                ),
                ("validation_errors", models.JSONField(blank=True, default=list, editable=False)),
                ("change_summary", models.CharField(max_length=500)),
                ("created_by", models.UUIDField(editable=False)),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("published_by", models.UUIDField(blank=True, editable=False, null=True)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="customization_framework.businessrule",
                    ),
                ),
            ],
            options={
                "db_table": "customization_business_rule_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "rule", "status", "version"],
                        name="cust_rulever_rule_stat_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "rule", "version"),
                        name="cust_rulever_tenant_rule_ver_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("tenant_id", "rule", "content_hash"),
                        name="cust_rulever_tenant_rule_hash_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(status="published"),
                        fields=("tenant_id", "rule"),
                        name="cust_rulever_one_published_uniq",
                    ),
                ],
            },
            bases=(src.modules.customization_framework.models.ImmutableVersionMixin, models.Model),
        ),
        migrations.CreateModel(
            name="RuleExecution",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("target_record_id", models.UUIDField(blank=True, null=True)),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("validate", "Validate"),
                            ("before_create", "Before create"),
                            ("before_update", "Before update"),
                            ("form_change", "Form change"),
                        ],
                        max_length=20,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=128)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("matched", "Matched"),
                            ("not_matched", "Not matched"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        max_length=12,
                    ),
                ),
                ("input_fingerprint", models.CharField(max_length=64)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("diagnostics", models.JSONField(blank=True, default=list)),
                ("duration_ms", models.PositiveIntegerField()),
                ("correlation_id", models.UUIDField()),
                ("executed_by", models.UUIDField()),
                ("executed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="customization_framework.businessrule",
                    ),
                ),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="customization_framework.businessruleversion",
                    ),
                ),
            ],
            options={
                "db_table": "customization_rule_executions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "rule", "executed_at"],
                        name="cust_exec_tenant_rule_time_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "target_record_id", "executed_at"],
                        name="cust_exec_record_time_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "status", "executed_at"],
                        name="cust_exec_status_time_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "rule", "idempotency_key"),
                        name="cust_exec_tenant_rule_idem_uniq",
                    )
                ],
            },
        ),
        migrations.RunPython(install_relationship_guards, remove_relationship_guards),
    ]
