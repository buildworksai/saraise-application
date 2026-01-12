# Generated migration for DMS document models

import src.modules.dms.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Folder",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.dms.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="dms.folder",
                    ),
                ),
                ("path", models.CharField(db_index=True, max_length=2000)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
            ],
            options={
                "db_table": "dms_folders",
                "indexes": [
                    models.Index(fields=["tenant_id", "parent"], name="dms_folder_tenant__parent_idx"),
                    models.Index(fields=["tenant_id", "path"], name="dms_folder_tenant__path_idx"),
                ],
                "unique_together": {("tenant_id", "parent", "name")},
            },
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.dms.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                (
                    "folder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="dms.folder",
                    ),
                ),
                ("file_path", models.CharField(max_length=2000)),
                ("mime_type", models.CharField(max_length=255)),
                ("size", models.BigIntegerField()),
                ("checksum", models.CharField(db_index=True, max_length=64)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
            ],
            options={
                "db_table": "dms_documents",
                "indexes": [
                    models.Index(fields=["tenant_id", "folder"], name="dms_documen_tenant__folder_idx"),
                    models.Index(fields=["tenant_id", "name"], name="dms_documen_tenant__name_idx"),
                    models.Index(fields=["tenant_id", "checksum"], name="dms_documen_tenant__checksum_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentVersion",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.dms.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version_number", models.IntegerField()),
                ("file_path", models.CharField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="dms.document",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_versions",
                "indexes": [
                    models.Index(fields=["document", "version_number"], name="dms_documen_documen_version_idx"),
                ],
                "unique_together": {("document", "version_number")},
            },
        ),
        migrations.CreateModel(
            name="DocumentPermission",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.dms.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "principal_type",
                    models.CharField(
                        choices=[("user", "User"), ("role", "Role"), ("group", "Group")],
                        max_length=20,
                    ),
                ),
                ("principal_id", models.CharField(db_index=True, max_length=36)),
                (
                    "permission",
                    models.CharField(
                        choices=[("read", "Read"), ("write", "Write"), ("delete", "Delete"), ("share", "Share")],
                        max_length=20,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permissions",
                        to="dms.document",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_permissions",
                "indexes": [
                    models.Index(fields=["tenant_id", "document"], name="dms_documen_perm_tenant__document_idx"),
                    models.Index(fields=["tenant_id", "principal_id"], name="dms_documen_perm_tenant__principal_idx"),
                ],
                "unique_together": {("document", "principal_type", "principal_id", "permission")},
            },
        ),
        migrations.CreateModel(
            name="DocumentShare",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.dms.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("share_token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("permissions", models.JSONField(default=list)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="dms.document",
                    ),
                ),
            ],
            options={
                "db_table": "dms_document_shares",
                "indexes": [
                    models.Index(fields=["tenant_id", "document"], name="dms_documen_share_tenant__document_idx"),
                    models.Index(fields=["share_token"], name="dms_documen_share_token_idx"),
                    models.Index(fields=["expires_at"], name="dms_documen_expires_at_idx"),
                ],
            },
        ),
    ]
