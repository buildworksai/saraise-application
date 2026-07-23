"""Add tenant runtime configuration and immutable customization evidence.

The migration also repairs the retained legacy scaffold table's PostgreSQL
tenant identifier from text to the canonical UUID type. Existing mutable
lifecycle JSON is preserved as append-only rows before its columns are
removed.
"""

from __future__ import annotations

import uuid
from hashlib import sha256

import django.db.models.deletion
from django.db import migrations, models
from django.utils.dateparse import parse_datetime

NEW_TENANT_TABLES = (
    "customization_runtime_configurations",
    "customization_runtime_configuration_versions",
    "customization_configuration_audit_records",
    "customization_field_definition_versions",
    "customization_idempotent_commands",
    "customization_lifecycle_transition_records",
    "customization_publication_records",
)

IMMUTABLE_TABLES = (
    "customization_runtime_configuration_versions",
    "customization_configuration_audit_records",
    "customization_field_definition_versions",
    "customization_idempotent_commands",
    "customization_lifecycle_transition_records",
    "customization_publication_records",
    "customization_form_layout_versions",
    "customization_business_rule_versions",
    "customization_rule_executions",
)

EVIDENCE_RELATIONSHIPS = (
    (
        "customization_runtime_configuration_versions",
        "configuration_id",
        "customization_runtime_configurations",
    ),
    (
        "customization_configuration_audit_records",
        "configuration_id",
        "customization_runtime_configurations",
    ),
    (
        "customization_field_definition_versions",
        "definition_id",
        "customization_field_definitions",
    ),
)

CONTRACT_SEED_MARKER = "_customization_framework_contract_seed_v2"
CONFIGURATION_RESOURCE_CONTRACT = {
    "module": "customization-framework",
    "resource": "configuration",
    "version": "1.0",
    "fields": {},
    "capabilities": {
        "custom_field_types": [
            "text",
            "long_text",
            "integer",
            "decimal",
            "boolean",
            "date",
            "datetime",
            "uuid",
            "choice",
            "multi_choice",
            "json",
        ],
        "form_surfaces": ["default"],
        "rule_triggers": [
            "validate",
            "before_create",
            "before_update",
            "form_change",
        ],
        "entitlement_keys": ["customization_framework.configuration"],
        "available": True,
        "discovery": {"source": "module_registry"},
    },
    "available": True,
    "discovery": {"source": "module_registry"},
}
REGISTRY_MANIFEST = """\
name: customization-framework
version: 2.0.0
type: foundation
lifecycle: core
"""


def migrate_legacy_transition_history(apps, schema_editor) -> None:
    """Copy every legacy JSON transition into its immutable evidence row."""

    del schema_editor
    transition_model = apps.get_model("customization_framework", "LifecycleTransitionRecord")
    aggregates = (
        (
            apps.get_model("customization_framework", "CustomFieldDefinition"),
            "field_definition",
        ),
        (
            apps.get_model("customization_framework", "FormDefinition"),
            "form",
        ),
        (
            apps.get_model("customization_framework", "BusinessRule"),
            "business_rule",
        ),
    )
    for aggregate_model, aggregate_type in aggregates:
        for aggregate in aggregate_model.objects.all().iterator():
            for number, entry in enumerate(aggregate.transition_history or [], start=1):
                metadata = entry.get("metadata") or {}
                actor_value = metadata.get("actor_id") or aggregate.updated_by
                correlation_value = metadata.get("correlation_id")
                if correlation_value is None:
                    raise RuntimeError("Cannot migrate lifecycle evidence without correlation_id")
                occurred_at = parse_datetime(str(entry.get("occurred_at", "")))
                if occurred_at is None:
                    raise RuntimeError("Cannot migrate lifecycle evidence with invalid occurred_at")
                transition_model.objects.create(
                    id=uuid.uuid4(),
                    tenant_id=aggregate.tenant_id,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate.id,
                    version=number,
                    transition_key=entry["transition_key"],
                    command=entry["command"],
                    from_state=entry.get("from_state"),
                    to_state=entry["to_state"],
                    metadata=metadata,
                    actor_id=actor_value,
                    correlation_id=correlation_value,
                    occurred_at=occurred_at,
                )


def restore_legacy_transition_history(apps, schema_editor) -> None:
    """Rebuild the removed JSON only when explicitly reversing this migration."""

    del schema_editor
    transition_model = apps.get_model("customization_framework", "LifecycleTransitionRecord")
    aggregates = (
        (
            apps.get_model("customization_framework", "CustomFieldDefinition"),
            "field_definition",
        ),
        (
            apps.get_model("customization_framework", "FormDefinition"),
            "form",
        ),
        (
            apps.get_model("customization_framework", "BusinessRule"),
            "business_rule",
        ),
    )
    for aggregate_model, aggregate_type in aggregates:
        for aggregate in aggregate_model.objects.all().iterator():
            rows = transition_model.objects.filter(
                tenant_id=aggregate.tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate.id,
            ).order_by("version")
            history = [
                {
                    "transition_key": row.transition_key,
                    "command": row.command,
                    "from_state": row.from_state,
                    "to_state": row.to_state,
                    "occurred_at": row.occurred_at.isoformat(),
                    "metadata": row.metadata,
                }
                for row in rows
            ]
            aggregate_model.objects.filter(pk=aggregate.pk).update(transition_history=history)


def convert_legacy_tenant_to_uuid(apps, schema_editor) -> None:
    """Convert the retained PostgreSQL legacy tenant column without data loss."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT tenant_id
             FROM customization_framework_resources
             WHERE tenant_id IS NULL
                OR tenant_id !~*
                   '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             LIMIT 1
            """)
        invalid = cursor.fetchone()
    if invalid is not None:
        raise RuntimeError(
            "Legacy customization tenant_id contains a non-UUID value; " "conversion stopped without changing storage"
        )
    schema_editor.execute("""
        ALTER TABLE customization_framework_resources
        ALTER COLUMN tenant_id TYPE UUID USING tenant_id::UUID;
        """)


def restore_legacy_tenant_text(apps, schema_editor) -> None:
    """Restore the exact legacy text storage contract on migration reversal."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        ALTER TABLE customization_framework_resources
        ALTER COLUMN tenant_id TYPE VARCHAR(36) USING tenant_id::TEXT;
        """)


def register_configuration_resource_contract(apps, schema_editor) -> None:
    """Merge the production contract into durable module-registry metadata."""

    del schema_editor
    registry_model = apps.get_model("core", "ModuleRegistryEntry")
    entry, _created = registry_model.objects.get_or_create(
        name="customization-framework",
        version="2.0.0",
        defaults={
            "description": ("Tenant-safe custom fields, forms, rules, and runtime configuration"),
            "module_type": "foundation",
            "lifecycle": "core",
            "manifest_content": REGISTRY_MANIFEST,
            "manifest_hash": sha256(REGISTRY_MANIFEST.encode("utf-8")).hexdigest(),
            "dependencies": [],
            "permissions": [],
            "sod_actions": [],
            "search_indexes": [],
            "ai_tools": [],
            "metadata": {},
            "is_active": True,
        },
    )
    metadata = dict(entry.metadata or {})
    if CONTRACT_SEED_MARKER in metadata:
        return
    previous = metadata.get("customization_resource_contracts")
    if previous is not None and not isinstance(previous, list):
        raise RuntimeError("Existing customization_resource_contracts metadata must be a list")
    contracts = list(previous or [])
    identity = (
        CONFIGURATION_RESOURCE_CONTRACT["module"],
        CONFIGURATION_RESOURCE_CONTRACT["resource"],
        CONFIGURATION_RESOURCE_CONTRACT["version"],
    )
    contracts = [
        contract
        for contract in contracts
        if not (
            isinstance(contract, dict)
            and (
                contract.get("module"),
                contract.get("resource"),
                contract.get("version"),
            )
            == identity
        )
    ]
    contracts.append(CONFIGURATION_RESOURCE_CONTRACT)
    metadata[CONTRACT_SEED_MARKER] = {
        "previous_contracts_present": previous is not None,
        "previous_contracts": previous,
    }
    metadata["customization_resource_contracts"] = contracts
    registry_model.objects.filter(pk=entry.pk).update(metadata=metadata)


def unregister_configuration_resource_contract(apps, schema_editor) -> None:
    """Restore only metadata owned by this migration's explicit marker."""

    del schema_editor
    registry_model = apps.get_model("core", "ModuleRegistryEntry")
    entry = registry_model.objects.filter(name="customization-framework", version="2.0.0").first()
    if entry is None:
        return
    metadata = dict(entry.metadata or {})
    marker = metadata.pop(CONTRACT_SEED_MARKER, None)
    if not isinstance(marker, dict):
        return
    if marker.get("previous_contracts_present"):
        metadata["customization_resource_contracts"] = marker.get("previous_contracts")
    else:
        metadata.pop("customization_resource_contracts", None)
    registry_model.objects.filter(pk=entry.pk).update(metadata=metadata)


def install_evidence_guards(apps, schema_editor) -> None:
    """Enable RLS, cross-tenant FK checks, and hard append-only triggers."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in NEW_TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION customization_reject_evidence_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'customization evidence is append-only'
                USING ERRCODE = '55000';
        END;
        $$;
        """)
    for table_name in IMMUTABLE_TABLES:
        trigger_name = f"cust_append_only_{table_name.removeprefix('customization_')}"
        schema_editor.execute(f"""
            DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger_name)}
                ON {schema_editor.quote_name(table_name)};
            CREATE TRIGGER {schema_editor.quote_name(trigger_name)}
            BEFORE UPDATE OR DELETE ON {schema_editor.quote_name(table_name)}
            FOR EACH ROW EXECUTE FUNCTION customization_reject_evidence_mutation();
            """)
    for child_table, fk_column, parent_table in EVIDENCE_RELATIONSHIPS:
        trigger_name = f"cust_same_tenant_{fk_column}_{child_table[-8:]}"
        schema_editor.execute(f"""
            DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger_name)}
                ON {schema_editor.quote_name(child_table)};
            CREATE TRIGGER {schema_editor.quote_name(trigger_name)}
            BEFORE INSERT OR UPDATE OF tenant_id, {schema_editor.quote_name(fk_column)}
                ON {schema_editor.quote_name(child_table)}
            FOR EACH ROW EXECUTE FUNCTION customization_require_same_tenant(
                '{fk_column}', '{parent_table}'
            );
            """)


def remove_evidence_guards(apps, schema_editor) -> None:
    """Remove only policies and triggers installed by this migration."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for child_table, fk_column, _parent_table in reversed(EVIDENCE_RELATIONSHIPS):
        trigger_name = f"cust_same_tenant_{fk_column}_{child_table[-8:]}"
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger_name)} "
            f"ON {schema_editor.quote_name(child_table)};"
        )
    for table_name in reversed(IMMUTABLE_TABLES):
        trigger_name = f"cust_append_only_{table_name.removeprefix('customization_')}"
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger_name)} "
            f"ON {schema_editor.quote_name(table_name)};"
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS customization_reject_evidence_mutation();")
    for table_name in reversed(NEW_TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table_name)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [("customization_framework", "0003_domain_rls")]

    operations = [
        migrations.CreateModel(
            name="IdempotentCommand",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(editable=False, max_length=128),
                ),
                ("command_type", models.CharField(editable=False, max_length=96)),
                (
                    "request_fingerprint",
                    models.CharField(editable=False, max_length=64),
                ),
                ("response_payload", models.JSONField(editable=False)),
                ("response_status", models.PositiveSmallIntegerField(editable=False)),
                ("resource_type", models.CharField(editable=False, max_length=64)),
                (
                    "resource_id",
                    models.UUIDField(blank=True, editable=False, null=True),
                ),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "customization_idempotent_commands",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "command_type", "created_at"],
                        name="cust_idem_command_time_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_idem_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "idempotency_key"),
                        name="cust_idem_tenant_key_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="LifecycleTransitionRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("aggregate_type", models.CharField(editable=False, max_length=64)),
                ("aggregate_id", models.UUIDField(editable=False)),
                ("version", models.PositiveIntegerField(editable=False)),
                (
                    "transition_key",
                    models.CharField(editable=False, max_length=128),
                ),
                ("command", models.CharField(editable=False, max_length=64)),
                (
                    "from_state",
                    models.CharField(blank=True, editable=False, max_length=32, null=True),
                ),
                ("to_state", models.CharField(editable=False, max_length=32)),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, editable=False),
                ),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("occurred_at", models.DateTimeField(editable=False)),
            ],
            options={
                "db_table": "customization_lifecycle_transition_records",
                "indexes": [
                    models.Index(
                        fields=[
                            "tenant_id",
                            "aggregate_type",
                            "aggregate_id",
                            "version",
                        ],
                        name="cust_lifecycle_aggregate_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_lifecycle_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "tenant_id",
                            "aggregate_type",
                            "aggregate_id",
                            "version",
                        ),
                        name="cust_lifecycle_aggregate_ver_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=(
                            "tenant_id",
                            "aggregate_type",
                            "aggregate_id",
                            "transition_key",
                        ),
                        name="cust_lifecycle_transition_key_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PublicationRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("aggregate_type", models.CharField(editable=False, max_length=64)),
                ("aggregate_id", models.UUIDField(editable=False)),
                ("snapshot_id", models.UUIDField(editable=False)),
                ("version", models.PositiveIntegerField(editable=False)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("published", "Published"),
                            ("superseded", "Superseded"),
                        ],
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "publication_key",
                    models.CharField(editable=False, max_length=128),
                ),
                (
                    "supersedes_snapshot_id",
                    models.UUIDField(blank=True, editable=False, null=True),
                ),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("occurred_at", models.DateTimeField(editable=False)),
            ],
            options={
                "db_table": "customization_publication_records",
                "indexes": [
                    models.Index(
                        fields=[
                            "tenant_id",
                            "aggregate_type",
                            "aggregate_id",
                            "occurred_at",
                        ],
                        name="cust_publication_aggregate_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "snapshot_id"],
                        name="cust_publication_snapshot_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_publication_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "tenant_id",
                            "aggregate_type",
                            "aggregate_id",
                            "publication_key",
                            "event_type",
                        ),
                        name="cust_publication_key_event_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RuntimeConfiguration",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("tenant_id", models.UUIDField(db_index=True, unique=True)),
                ("document", models.JSONField()),
                ("version", models.PositiveIntegerField(editable=False)),
                ("environment", models.CharField(max_length=32)),
                ("updated_by", models.UUIDField(editable=False)),
            ],
            options={
                "db_table": "customization_runtime_configurations",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment"],
                        name="cust_runtime_tenant_env_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CustomFieldDefinitionVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(editable=False)),
                ("document", models.JSONField(editable=False)),
                (
                    "content_hash",
                    models.CharField(editable=False, max_length=64),
                ),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="customization_framework.customfielddefinition",
                    ),
                ),
            ],
            options={
                "db_table": "customization_field_definition_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "definition", "version"],
                        name="cust_fdver_def_ver_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_fdver_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "definition", "version"),
                        name="cust_fdver_tenant_def_ver_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ConfigurationAuditRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(editable=False)),
                ("action", models.CharField(editable=False, max_length=32)),
                (
                    "before",
                    models.JSONField(blank=True, editable=False, null=True),
                ),
                ("after", models.JSONField(editable=False)),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_records",
                        to="customization_framework.runtimeconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "customization_configuration_audit_records",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "version"],
                        name="cust_cfg_audit_cfg_ver_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_cfg_audit_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"),
                        name="cust_cfg_audit_tenant_ver_uniq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RuntimeConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField(editable=False)),
                ("document", models.JSONField(editable=False)),
                ("environment", models.CharField(editable=False, max_length=32)),
                ("actor_id", models.UUIDField(editable=False)),
                ("correlation_id", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="customization_framework.runtimeconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "customization_runtime_configuration_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "version"],
                        name="cust_runtime_ver_cfg_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="cust_runtime_ver_corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"),
                        name="cust_runtime_ver_tenant_cfg_uniq",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            migrate_legacy_transition_history,
            restore_legacy_transition_history,
        ),
        migrations.RemoveField(
            model_name="businessrule",
            name="transition_history",
        ),
        migrations.RemoveField(
            model_name="customfielddefinition",
            name="transition_history",
        ),
        migrations.RemoveField(
            model_name="formdefinition",
            name="transition_history",
        ),
        migrations.RemoveConstraint(
            model_name="formlayoutversion",
            name="cust_layout_one_published_uniq",
        ),
        migrations.RemoveConstraint(
            model_name="businessruleversion",
            name="cust_rulever_one_published_uniq",
        ),
        migrations.RunPython(
            convert_legacy_tenant_to_uuid,
            restore_legacy_tenant_text,
        ),
        migrations.RunPython(
            register_configuration_resource_contract,
            unregister_configuration_resource_contract,
        ),
        migrations.RunPython(install_evidence_guards, remove_evidence_guards),
    ]
