"""Create the UUID-native DMS v2 schema without disturbing legacy rows."""

from __future__ import annotations

import uuid

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q
from django.db.models.functions import Lower


def quarantine_resource_table(apps, schema_editor) -> None:
    del apps
    schema_editor.execute(
        f"ALTER TABLE {schema_editor.quote_name('dms_resources')} "
        f"RENAME TO {schema_editor.quote_name('dms_resources_legacy')}"
    )


def restore_resource_table(apps, schema_editor) -> None:
    del apps
    schema_editor.execute(
        f"ALTER TABLE {schema_editor.quote_name('dms_resources_legacy')} "
        f"RENAME TO {schema_editor.quote_name('dms_resources')}"
    )


def create_search_index(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE INDEX dms_doc_search_gin
            ON dms_documents_v2
         USING GIN (
            to_tsvector(
                'simple',
                coalesce(name, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(metadata::text, '')
            )
         )
        """)


def drop_search_index(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS dms_doc_search_gin")


class Migration(migrations.Migration):
    dependencies = [("dms", "0002_add_document_models")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(quarantine_resource_table, restore_resource_table)],
            state_operations=[migrations.DeleteModel(name="DmsResource")],
        ),
        migrations.CreateModel(
            name="FolderV2",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("path", models.CharField(max_length=2000)),
                ("depth", models.PositiveSmallIntegerField(default=0)),
                ("sort_order", models.IntegerField(default=0)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="dms.folderv2",
                    ),
                ),
            ],
            options={
                "db_table": "dms_folders_v2",
                "ordering": ("sort_order", "name", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "parent", "is_deleted", "sort_order", "name"],
                        name="dms_folder_contents_idx",
                    ),
                    models.Index(fields=["tenant_id", "path"], name="dms_folder_path_idx"),
                    models.Index(fields=["tenant_id", "updated_at"], name="dms_folder_updated_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(depth__gte=0, depth__lte=10),
                        name="dms_folder_depth_range",
                    ),
                    models.CheckConstraint(
                        condition=~Q(id=F("parent_id")),
                        name="dms_folder_not_self_parent",
                    ),
                    models.UniqueConstraint(
                        Lower("name"),
                        F("tenant_id"),
                        condition=Q(parent__isnull=True, is_deleted=False),
                        name="dms_folder_root_name_ci_uq",
                    ),
                    models.UniqueConstraint(
                        Lower("name"),
                        F("tenant_id"),
                        F("parent"),
                        condition=Q(parent__isnull=False, is_deleted=False),
                        name="dms_folder_child_name_ci_uq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentV2",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("tags", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("version_count", models.PositiveIntegerField(default=0)),
                (
                    "folder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="documents",
                        to="dms.folderv2",
                    ),
                ),
            ],
            options={
                "db_table": "dms_documents_v2",
                "ordering": ("-updated_at", "name", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "folder", "is_deleted", "updated_at"],
                        name="dms_doc_folder_updated_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "created_by", "is_deleted"],
                        name="dms_doc_owner_alive_idx",
                    ),
                    models.Index(fields=["tenant_id", "name"], name="dms_doc_name_idx"),
                    django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="dms_doc_tags_gin"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=Q(version_count__gte=0), name="dms_doc_version_count_gte0"),
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentVersionV2",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version_number", models.PositiveIntegerField()),
                ("storage_backend", models.CharField(db_index=True, default="django", max_length=100)),
                ("storage_key", models.CharField(max_length=2000)),
                ("original_filename", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=255)),
                ("size_bytes", models.PositiveBigIntegerField()),
                (
                    "checksum_sha256",
                    models.CharField(
                        max_length=64,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[0-9a-f]{64}$",
                                "Checksum must be a lowercase SHA-256 digest.",
                            )
                        ],
                    ),
                ),
                ("change_note", models.CharField(blank=True, default="", max_length=1000)),
                ("created_by", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="dms.documentv2",
                    ),
                ),
                (
                    "source_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="restored_versions",
                        to="dms.documentversionv2",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_versions_v2",
                "ordering": ("-version_number", "-created_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "document", "-version_number"],
                        name="dms_version_doc_number_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "checksum_sha256"],
                        name="dms_version_checksum_idx",
                    ),
                    models.Index(fields=["tenant_id", "created_at"], name="dms_version_created_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "document", "version_number"),
                        name="dms_version_tenant_doc_no_uq",
                    ),
                    models.CheckConstraint(condition=Q(version_number__gte=1), name="dms_version_number_gte1"),
                    models.CheckConstraint(condition=Q(size_bytes__gt=0), name="dms_version_size_gt0"),
                    models.CheckConstraint(
                        condition=Q(checksum_sha256__regex="^[0-9a-f]{64}$"),
                        name="dms_version_checksum_sha256",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="documentv2",
            name="current_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="current_for_documents",
                to="dms.documentversionv2",
            ),
        ),
        migrations.CreateModel(
            name="DocumentPermissionV2",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "principal_type",
                    models.CharField(choices=[("user", "User"), ("role", "Role"), ("group", "Group")], max_length=20),
                ),
                ("principal_id", models.UUIDField()),
                (
                    "permission",
                    models.CharField(
                        choices=[
                            ("read", "Read"),
                            ("write", "Write"),
                            ("delete", "Delete"),
                            ("share", "Share"),
                            ("manage", "Manage"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permissions",
                        to="dms.documentv2",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_permissions_v2",
                "ordering": ("principal_type", "principal_id", "permission", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "document", "is_deleted"],
                        name="dms_perm_document_alive_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "principal_type", "principal_id", "is_deleted"],
                        name="dms_perm_principal_alive_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "permission", "is_deleted"],
                        name="dms_perm_level_alive_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "document", "principal_type", "principal_id", "permission"),
                        condition=Q(is_deleted=False),
                        name="dms_permission_live_grant_uq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentShareV2",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "token_digest",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[0-9a-f]{64}$",
                                "Token digest must be a lowercase SHA-256 digest.",
                            )
                        ],
                    ),
                ),
                ("token_prefix", models.CharField(db_index=True, max_length=12)),
                ("expires_at", models.DateTimeField()),
                ("max_access_count", models.PositiveIntegerField(blank=True, null=True)),
                ("access_count", models.PositiveIntegerField(default=0)),
                ("last_accessed_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shares",
                        to="dms.documentv2",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shares",
                        to="dms.documentversionv2",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_shares_v2",
                "ordering": ("-created_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "document", "revoked_at", "expires_at"],
                        name="dms_share_doc_validity_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(max_access_count__isnull=True)
                        | Q(max_access_count__gte=1, max_access_count__lte=10000),
                        name="dms_share_max_access_range",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_access_count__isnull=True) | Q(access_count__lte=F("max_access_count")),
                        name="dms_share_access_not_over",
                    ),
                    models.CheckConstraint(condition=Q(access_count__gte=0), name="dms_share_access_gte0"),
                    models.CheckConstraint(
                        condition=Q(token_digest__regex="^[0-9a-f]{64}$"),
                        name="dms_share_digest_sha256",
                    ),
                ],
            },
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(create_search_index, drop_search_index)],
            state_operations=[
                migrations.AddIndex(
                    model_name="documentv2",
                    index=django.contrib.postgres.indexes.GinIndex(
                        django.contrib.postgres.search.SearchVector("name", "description", "metadata", config="simple"),
                        name="dms_doc_search_gin",
                    ),
                )
            ],
        ),
    ]
