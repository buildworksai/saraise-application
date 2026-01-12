# Generated migration for Data Migration models

import src.modules.data_migration.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("data_migration", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MigrationJob",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.data_migration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("csv", "CSV File"),
                            ("excel", "Excel File"),
                            ("json", "JSON File"),
                            ("database", "Database"),
                            ("api", "API"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                ("source_config", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("records_processed", models.IntegerField(default=0)),
                ("records_failed", models.IntegerField(default=0)),
                ("records_total", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
            ],
            options={
                "db_table": "data_migration_jobs",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="data_migrat_tenant__status_idx"),
                    models.Index(fields=["tenant_id", "source_type"], name="data_migrat_tenant__source_type_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MigrationMapping",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.data_migration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("source_field", models.CharField(max_length=255)),
                ("target_field", models.CharField(max_length=255)),
                ("transform", models.JSONField(default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mappings",
                        to="data_migration.migrationjob",
                    ),
                ),
            ],
            options={
                "db_table": "data_migration_mappings",
                "indexes": [
                    models.Index(fields=["tenant_id", "job"], name="data_migrat_tenant__job_idx"),
                ],
                "unique_together": {("job", "source_field")},
            },
        ),
        migrations.CreateModel(
            name="MigrationLog",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.data_migration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("debug", "Debug"),
                            ("info", "Info"),
                            ("warning", "Warning"),
                            ("error", "Error"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("message", models.TextField()),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="data_migration.migrationjob",
                    ),
                ),
            ],
            options={
                "db_table": "data_migration_logs",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "job", "timestamp"],
                        name="data_migrat_tenant__job__timestamp_idx",
                    ),
                    models.Index(fields=["job", "level"], name="data_migrat_log_job__level_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MigrationValidation",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.data_migration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("field", models.CharField(max_length=255)),
                ("rule", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("warning", "Warning"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("record_index", models.IntegerField(blank=True, null=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="validations",
                        to="data_migration.migrationjob",
                    ),
                ),
            ],
            options={
                "db_table": "data_migration_validations",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "job", "status"],
                        name="data_migrat_tenant__job__status_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="MigrationRollback",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.data_migration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("checkpoint_data", models.JSONField(default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rollbacks",
                        to="data_migration.migrationjob",
                    ),
                ),
            ],
            options={
                "db_table": "data_migration_rollbacks",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "job", "created_at"],
                        name="data_migrat_tenant__job__created_idx",
                    ),
                ],
            },
        ),
    ]
