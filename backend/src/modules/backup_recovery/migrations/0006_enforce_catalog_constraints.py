"""Enforce the v2 catalog schema, indexes, and tenant-consistent relations."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q

JOB_STATUS = [
    ("pending", "Pending"),
    ("running", "Running"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
]
BACKUP_TYPES = [("full", "Full"), ("incremental", "Incremental"), ("differential", "Differential")]
SCOPES = [("tenant", "Tenant"), ("module", "Module"), ("database", "Database"), ("files", "Files")]
FREQUENCIES = [("hourly", "Hourly"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]


def validate_one_archive_per_job(apps, schema_editor):
    del schema_editor
    Archive = apps.get_model("backup_recovery", "BackupArchive")
    duplicate = (
        Archive.objects.values("backup_job_id")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
        .order_by("backup_job_id")
        .values_list("backup_job_id", flat=True)
        .first()
    )
    if duplicate:
        raise RuntimeError(f"Multiple legacy archives exist for backup job {str(duplicate)[:12]}")


POSTGRES_TRIGGER_SQL = r"""
CREATE OR REPLACE FUNCTION backup_recovery_assert_tenant_relations()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'backup_recovery_schedules' THEN
    IF NOT EXISTS (SELECT 1 FROM backup_recovery_storage_targets t WHERE t.id=NEW.storage_target_id AND t.tenant_id=NEW.tenant_id)
       OR NOT EXISTS (SELECT 1 FROM backup_recovery_retention_policies p WHERE p.id=NEW.retention_policy_id AND p.tenant_id=NEW.tenant_id)
    THEN RAISE EXCEPTION 'cross-tenant backup schedule relation'; END IF;
  ELSIF TG_TABLE_NAME = 'backup_recovery_jobs' THEN
    IF NOT EXISTS (SELECT 1 FROM backup_recovery_storage_targets t WHERE t.id=NEW.storage_target_id AND t.tenant_id=NEW.tenant_id)
       OR (NEW.schedule_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_schedules s WHERE s.id=NEW.schedule_id AND s.tenant_id=NEW.tenant_id))
       OR (NEW.retention_policy_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_retention_policies p WHERE p.id=NEW.retention_policy_id AND p.tenant_id=NEW.tenant_id))
       OR (NEW.retry_of_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.retry_of_id AND j.tenant_id=NEW.tenant_id))
       OR (NEW.base_job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.base_job_id AND j.tenant_id=NEW.tenant_id))
    THEN RAISE EXCEPTION 'cross-tenant backup job relation'; END IF;
  ELSIF TG_TABLE_NAME = 'backup_recovery_archives' THEN
    IF NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.backup_job_id AND j.tenant_id=NEW.tenant_id)
    THEN RAISE EXCEPTION 'cross-tenant backup archive relation'; END IF;
  ELSIF TG_TABLE_NAME = 'backup_recovery_verifications' THEN
    IF NOT EXISTS (SELECT 1 FROM backup_recovery_archives a WHERE a.id=NEW.archive_id AND a.tenant_id=NEW.tenant_id)
    THEN RAISE EXCEPTION 'cross-tenant backup verification relation'; END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS br_schedule_tenant_guard ON backup_recovery_schedules;
CREATE TRIGGER br_schedule_tenant_guard BEFORE INSERT OR UPDATE ON backup_recovery_schedules
FOR EACH ROW EXECUTE FUNCTION backup_recovery_assert_tenant_relations();
DROP TRIGGER IF EXISTS br_job_tenant_guard ON backup_recovery_jobs;
CREATE TRIGGER br_job_tenant_guard BEFORE INSERT OR UPDATE ON backup_recovery_jobs
FOR EACH ROW EXECUTE FUNCTION backup_recovery_assert_tenant_relations();
DROP TRIGGER IF EXISTS br_archive_tenant_guard ON backup_recovery_archives;
CREATE TRIGGER br_archive_tenant_guard BEFORE INSERT OR UPDATE ON backup_recovery_archives
FOR EACH ROW EXECUTE FUNCTION backup_recovery_assert_tenant_relations();
DROP TRIGGER IF EXISTS br_verify_tenant_guard ON backup_recovery_verifications;
CREATE TRIGGER br_verify_tenant_guard BEFORE INSERT OR UPDATE ON backup_recovery_verifications
FOR EACH ROW EXECUTE FUNCTION backup_recovery_assert_tenant_relations();
"""

SQLITE_TRIGGER_SQL = (
    "CREATE TRIGGER br_schedule_tenant_guard BEFORE INSERT ON backup_recovery_schedules BEGIN "
    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM backup_recovery_storage_targets t WHERE t.id=NEW.storage_target_id AND t.tenant_id=NEW.tenant_id) "
    "OR NOT EXISTS (SELECT 1 FROM backup_recovery_retention_policies p WHERE p.id=NEW.retention_policy_id AND p.tenant_id=NEW.tenant_id) "
    "THEN RAISE(ABORT, 'cross-tenant backup schedule relation') END; END;",
    "CREATE TRIGGER br_job_tenant_guard BEFORE INSERT ON backup_recovery_jobs BEGIN "
    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM backup_recovery_storage_targets t WHERE t.id=NEW.storage_target_id AND t.tenant_id=NEW.tenant_id) "
    "OR (NEW.schedule_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_schedules s WHERE s.id=NEW.schedule_id AND s.tenant_id=NEW.tenant_id)) "
    "OR (NEW.retention_policy_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_retention_policies p WHERE p.id=NEW.retention_policy_id AND p.tenant_id=NEW.tenant_id)) "
    "OR (NEW.retry_of_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.retry_of_id AND j.tenant_id=NEW.tenant_id)) "
    "OR (NEW.base_job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.base_job_id AND j.tenant_id=NEW.tenant_id)) "
    "THEN RAISE(ABORT, 'cross-tenant backup job relation') END; END;",
    "CREATE TRIGGER br_archive_tenant_guard BEFORE INSERT ON backup_recovery_archives BEGIN "
    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM backup_recovery_jobs j WHERE j.id=NEW.backup_job_id AND j.tenant_id=NEW.tenant_id) "
    "THEN RAISE(ABORT, 'cross-tenant backup archive relation') END; END;",
    "CREATE TRIGGER br_verify_tenant_guard BEFORE INSERT ON backup_recovery_verifications BEGIN "
    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM backup_recovery_archives a WHERE a.id=NEW.archive_id AND a.tenant_id=NEW.tenant_id) "
    "THEN RAISE(ABORT, 'cross-tenant backup verification relation') END; END;",
)

SQLITE_UPDATE_TRIGGER_SQL = tuple(
    statement.replace("_tenant_guard BEFORE INSERT", "_tenant_update_guard BEFORE UPDATE")
    for statement in SQLITE_TRIGGER_SQL
)
SQLITE_TRIGGER_SQL = SQLITE_TRIGGER_SQL + tuple(
    statement.replace("_tenant_guard BEFORE INSERT", "_tenant_guard_update BEFORE UPDATE")
    for statement in SQLITE_TRIGGER_SQL
)


def add_tenant_guards(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_TRIGGER_SQL)
    elif schema_editor.connection.vendor == "sqlite":
        for statement in SQLITE_TRIGGER_SQL + SQLITE_UPDATE_TRIGGER_SQL:
            schema_editor.execute(statement)


def drop_tenant_guards(apps, schema_editor):
    del apps
    for table, trigger in (
        ("backup_recovery_schedules", "br_schedule_tenant_guard"),
        ("backup_recovery_jobs", "br_job_tenant_guard"),
        ("backup_recovery_archives", "br_archive_tenant_guard"),
        ("backup_recovery_verifications", "br_verify_tenant_guard"),
    ):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}"')
        elif schema_editor.connection.vendor == "sqlite":
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger.replace("_guard", "_update_guard")}"')
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}_update"')
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP FUNCTION IF EXISTS backup_recovery_assert_tenant_relations()")


def state_only_alter(model_name, name, field):
    """Keep legacy NULL evidence readable while new ORM writes stay strict."""
    return migrations.SeparateDatabaseAndState(
        database_operations=[],
        state_operations=[migrations.AlterField(model_name=model_name, name=name, field=field)],
    )


class Migration(migrations.Migration):
    dependencies = [("backup_recovery", "0005_backfill_catalog_domain")]
    operations = [
        migrations.RunPython(validate_one_archive_per_job, migrations.RunPython.noop),
        migrations.RemoveField("backupschedule", "retention_days"),
        migrations.RemoveField("backuparchive", "description"),
        *[
            migrations.RemoveField(model_name, field_name)
            for model_name in ("backupjob", "backupschedule", "backupretentionpolicy", "backuparchive")
            for field_name in ("legacy_id_text", "legacy_tenant_id_text")
        ],
        migrations.AlterField("backupjob", "scope_type", models.CharField(max_length=20, choices=SCOPES)),
        migrations.AlterField("backupjob", "scope_ref", models.CharField(max_length=255)),
        migrations.AlterField("backupjob", "backup_type", models.CharField(max_length=20, choices=BACKUP_TYPES)),
        migrations.AlterField(
            "backupjob", "status", models.CharField(max_length=20, choices=JOB_STATUS, default="pending")
        ),
        migrations.AlterField("backupjob", "idempotency_key", models.CharField(max_length=128)),
        migrations.AlterField(
            "backupjob",
            "storage_target",
            models.ForeignKey(
                to="backup_recovery.backupstoragetarget",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="backup_jobs",
            ),
        ),
        migrations.AlterField("backupschedule", "name", models.CharField(max_length=120)),
        migrations.AlterField("backupschedule", "scope_type", models.CharField(max_length=20, choices=SCOPES)),
        migrations.AlterField("backupschedule", "scope_ref", models.CharField(max_length=255)),
        migrations.AlterField("backupschedule", "backup_type", models.CharField(max_length=20, choices=BACKUP_TYPES)),
        migrations.AlterField("backupschedule", "frequency", models.CharField(max_length=20, choices=FREQUENCIES)),
        migrations.AlterField("backupschedule", "schedule_time", models.TimeField(null=True, blank=True)),
        migrations.AlterField("backupschedule", "timezone", models.CharField(max_length=64)),
        migrations.AlterField(
            "backupschedule",
            "storage_target",
            models.ForeignKey(
                to="backup_recovery.backupstoragetarget",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="schedules",
            ),
        ),
        migrations.AlterField(
            "backupschedule",
            "retention_policy",
            models.ForeignKey(
                to="backup_recovery.backupretentionpolicy",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="schedules",
            ),
        ),
        migrations.AlterField(
            "backuparchive",
            "backup_job",
            models.OneToOneField(
                to="backup_recovery.backupjob",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="archive",
            ),
        ),
        migrations.AlterField(
            "backuparchive",
            "lifecycle",
            models.CharField(
                max_length=20,
                choices=[("available", "Available"), ("expired", "Expired"), ("purged", "Purged")],
                default="available",
            ),
        ),
        migrations.AlterField(
            "backuparchive",
            "integrity_status",
            models.CharField(
                max_length=20,
                choices=[
                    ("unknown", "Unknown"),
                    ("verifying", "Verifying"),
                    ("verified", "Verified"),
                    ("corrupt", "Corrupt"),
                ],
                default="unknown",
            ),
        ),
        migrations.AlterField("backuparchive", "captured_at", models.DateTimeField()),
        migrations.AddConstraint(
            "backupstoragetarget",
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_target_active_name_uq"
            ),
        ),
        migrations.AddConstraint(
            "backupstoragetarget",
            models.UniqueConstraint(
                fields=("tenant_id",),
                condition=Q(is_deleted=False, is_active=True, is_default=True),
                name="br_target_one_default_uq",
            ),
        ),
        migrations.AddConstraint(
            "backupstoragetarget",
            models.CheckConstraint(
                condition=Q(adapter_key__regex=r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$"), name="br_target_adapter_key_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupretentionpolicy",
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_policy_active_name_uq"
            ),
        ),
        migrations.AddConstraint(
            "backupretentionpolicy",
            models.CheckConstraint(
                condition=Q(retention_days__gte=1, retention_days__lte=3650), name="br_policy_retention_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupretentionpolicy",
            models.CheckConstraint(
                condition=Q(archive_after_days__isnull=True) | Q(archive_after_days__lt=models.F("retention_days")),
                name="br_policy_archive_lt_ret_ck",
            ),
        ),
        migrations.AddConstraint(
            "backupretentionpolicy",
            models.CheckConstraint(condition=Q(keep_last_successful__gte=1), name="br_policy_keep_last_ck"),
        ),
        migrations.AddConstraint(
            "backupschedule",
            models.UniqueConstraint(
                fields=("tenant_id", "name"), condition=Q(is_deleted=False), name="br_schedule_active_name_uq"
            ),
        ),
        migrations.AddConstraint(
            "backupschedule",
            models.CheckConstraint(
                condition=Q(day_of_week__isnull=True) | Q(day_of_week__range=(0, 6)), name="br_schedule_weekday_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupschedule",
            models.CheckConstraint(
                condition=Q(day_of_month__isnull=True) | Q(day_of_month__range=(1, 28)), name="br_schedule_monthday_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupschedule",
            models.CheckConstraint(
                condition=Q(
                    frequency="hourly", schedule_time__isnull=True, day_of_week__isnull=True, day_of_month__isnull=True
                )
                | Q(frequency="daily", schedule_time__isnull=False, day_of_week__isnull=True, day_of_month__isnull=True)
                | Q(
                    frequency="weekly",
                    schedule_time__isnull=False,
                    day_of_week__isnull=False,
                    day_of_month__isnull=True,
                )
                | Q(
                    frequency="monthly",
                    schedule_time__isnull=False,
                    day_of_week__isnull=True,
                    day_of_month__isnull=False,
                ),
                name="br_schedule_frequency_ck",
            ),
        ),
        migrations.AddConstraint(
            "backupjob", models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="br_job_idempotency_uq")
        ),
        migrations.AddConstraint(
            "backupjob",
            models.CheckConstraint(condition=Q(size_bytes__isnull=True) | Q(size_bytes__gte=0), name="br_job_size_ck"),
        ),
        migrations.AddConstraint(
            "backupjob",
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(started_at__isnull=False), name="br_job_completed_started_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupjob",
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=models.F("started_at")),
                name="br_job_completion_order_ck",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddConstraint(
                    "backupjob",
                    models.CheckConstraint(
                        condition=~Q(status="pending") | (Q(started_at__isnull=True) & Q(completed_at__isnull=True)),
                        name="br_job_pending_times_ck",
                    ),
                ),
                migrations.AddConstraint(
                    "backupjob",
                    models.CheckConstraint(
                        condition=~Q(status="completed")
                        | (
                            Q(completed_at__isnull=False)
                            & Q(data_cutoff_at__isnull=False)
                            & Q(size_bytes__isnull=False)
                        ),
                        name="br_job_completed_fields_ck",
                    ),
                ),
                migrations.AddConstraint(
                    "backupjob",
                    models.CheckConstraint(
                        condition=~Q(status="failed") | (Q(completed_at__isnull=False) & ~Q(error_code="")),
                        name="br_job_failed_fields_ck",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            "backuparchive", models.CheckConstraint(condition=Q(size_bytes__gte=0), name="br_archive_size_ck")
        ),
        migrations.AddConstraint(
            "backuparchive",
            models.CheckConstraint(condition=Q(checksum_algorithm="sha256"), name="br_archive_sha256_ck"),
        ),
        migrations.AddConstraint(
            "backuparchive",
            models.CheckConstraint(condition=Q(checksum_digest__regex=r"^[0-9a-f]{64}$"), name="br_archive_digest_ck"),
        ),
        migrations.AddConstraint(
            "backuparchive",
            models.CheckConstraint(
                condition=~Q(lifecycle="purged") | Q(purged_at__isnull=False), name="br_archive_purged_ck"
            ),
        ),
        migrations.AddConstraint(
            "backupverification",
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="br_verify_idempotency_uq"),
        ),
        migrations.AddConstraint(
            "backupverification",
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=models.F("started_at")),
                name="br_verify_completion_ck",
            ),
        ),
        migrations.AddConstraint(
            "backupverification",
            models.CheckConstraint(
                condition=~Q(status="passed")
                | (
                    Q(checksum_matches=True)
                    & Q(artifact_available=True)
                    & Q(encryption_metadata_valid=True)
                    & Q(provider_acknowledged=True)
                ),
                name="br_verify_passed_ck",
            ),
        ),
        migrations.AddConstraint(
            "backupverification",
            models.CheckConstraint(condition=~Q(status="failed") | ~Q(error_code=""), name="br_verify_failed_ck"),
        ),
        *[
            migrations.AddIndex(model_name, models.Index(fields=fields, name=name))
            for model_name, fields, name in (
                ("backupstoragetarget", ("tenant_id", "is_active", "is_default"), "br_target_active_default_ix"),
                ("backupstoragetarget", ("tenant_id", "adapter_key"), "br_target_adapter_ix"),
                ("backupstoragetarget", ("tenant_id", "is_deleted", "created_at"), "br_target_deleted_ix"),
                ("backupretentionpolicy", ("tenant_id", "is_active"), "br_policy_active_ix"),
                ("backupretentionpolicy", ("tenant_id", "name"), "br_policy_name_ix"),
                ("backupretentionpolicy", ("tenant_id", "is_deleted", "created_at"), "br_policy_deleted_ix"),
                ("backupschedule", ("tenant_id", "is_active", "next_run_at"), "br_schedule_due_ix"),
                ("backupschedule", ("tenant_id", "scope_type", "scope_ref"), "br_schedule_scope_ix"),
                ("backupschedule", ("tenant_id", "backup_type", "frequency"), "br_schedule_type_freq_ix"),
                ("backupschedule", ("tenant_id", "is_deleted", "created_at"), "br_schedule_deleted_ix"),
                ("backupjob", ("tenant_id", "status", "requested_at"), "br_job_status_ix"),
                ("backupjob", ("tenant_id", "backup_type", "requested_at"), "br_job_type_ix"),
                ("backupjob", ("tenant_id", "schedule", "requested_at"), "br_job_schedule_ix"),
                ("backupjob", ("tenant_id", "scope_type", "scope_ref", "requested_at"), "br_job_scope_ix"),
                ("backupjob", ("tenant_id", "is_deleted", "created_at"), "br_job_deleted_ix"),
                ("backuparchive", ("tenant_id", "lifecycle", "expires_at"), "br_archive_lifecycle_ix"),
                ("backuparchive", ("tenant_id", "integrity_status", "captured_at"), "br_archive_integrity_ix"),
                ("backuparchive", ("tenant_id", "captured_at"), "br_archive_captured_ix"),
                ("backupverification", ("tenant_id", "status", "requested_at"), "br_verify_status_ix"),
                ("backupverification", ("tenant_id", "archive", "requested_at"), "br_verify_archive_ix"),
            )
        ],
        migrations.RunPython(add_tenant_guards, drop_tenant_guards),
        # Keep these state-only alterations last. On SQLite, any later schema
        # operation can rebuild the archive table from migration state and
        # accidentally enforce NOT NULL against preserved legacy evidence.
        state_only_alter("backuparchive", "adapter_key", models.CharField(max_length=120)),
        state_only_alter("backuparchive", "size_bytes", models.BigIntegerField()),
        state_only_alter("backuparchive", "checksum_algorithm", models.CharField(max_length=20, default="sha256")),
        state_only_alter("backuparchive", "checksum_digest", models.CharField(max_length=64)),
        state_only_alter("backuparchive", "provider_acknowledgement", models.CharField(max_length=255)),
        state_only_alter("backuparchive", "data_cutoff_at", models.DateTimeField()),
    ]
