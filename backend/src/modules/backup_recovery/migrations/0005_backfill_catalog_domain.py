"""Backfill deterministic v2 ownership metadata without fabricating evidence."""

from __future__ import annotations

import datetime

from django.db import migrations

MIGRATION_ACTOR = "migration:backup-recovery-v2"


def _target_for(StorageTarget, tenant_id):
    target = StorageTarget.objects.filter(tenant_id=tenant_id).order_by("created_at", "id").first()
    if target:
        return target
    return StorageTarget.objects.create(
        tenant_id=tenant_id,
        name="Legacy unconfigured target",
        adapter_key="legacy-unavailable",
        locator_prefix_ref="legacy-unconfigured",
        configuration_ref="legacy-unconfigured",
        is_active=False,
        created_by=MIGRATION_ACTOR,
    )


def _policy_for(Policy, tenant_id, retention_days=30):
    policy = Policy.objects.filter(tenant_id=tenant_id).order_by("created_at", "id").first()
    if policy:
        return policy
    return Policy.objects.create(
        tenant_id=tenant_id,
        name="Legacy retention",
        description="Imported from the pre-v2 schedule contract.",
        retention_days=max(1, min(int(retention_days or 30), 3650)),
        archive_after_days=None,
        keep_last_successful=3,
        created_by=MIGRATION_ACTOR,
    )


def forward(apps, schema_editor):
    del schema_editor
    Job = apps.get_model("backup_recovery", "BackupJob")
    Schedule = apps.get_model("backup_recovery", "BackupSchedule")
    Policy = apps.get_model("backup_recovery", "BackupRetentionPolicy")
    Archive = apps.get_model("backup_recovery", "BackupArchive")
    StorageTarget = apps.get_model("backup_recovery", "BackupStorageTarget")

    tenant_ids = set()
    for model in (Job, Schedule, Policy, Archive):
        tenant_ids.update(model.objects.values_list("tenant_id", flat=True).distinct())
    targets = {tenant_id: _target_for(StorageTarget, tenant_id) for tenant_id in tenant_ids}

    for policy in Policy.objects.all().iterator(chunk_size=2_000):
        policy.keep_last_successful = max(1, policy.keep_last_successful or 3)
        policy.save(update_fields=("keep_last_successful",))

    for schedule in Schedule.objects.all().iterator(chunk_size=2_000):
        schedule.name = f"Legacy schedule {str(schedule.id)[:8]}"
        schedule.scope_type = "tenant"
        schedule.scope_ref = str(schedule.tenant_id)
        schedule.timezone = "UTC"
        schedule.storage_target_id = targets[schedule.tenant_id].id
        schedule.retention_policy_id = _policy_for(Policy, schedule.tenant_id, schedule.retention_days).id
        if schedule.frequency == "hourly":
            schedule.schedule_time = None
            schedule.day_of_week = None
            schedule.day_of_month = None
        else:
            schedule.schedule_time = schedule.schedule_time or datetime.time(0, 0)
            schedule.day_of_week = 0 if schedule.frequency == "weekly" else None
            schedule.day_of_month = 1 if schedule.frequency == "monthly" else None
        schedule.save(
            update_fields=(
                "name",
                "scope_type",
                "scope_ref",
                "timezone",
                "storage_target",
                "retention_policy",
                "schedule_time",
                "day_of_week",
                "day_of_month",
            )
        )

    for job in Job.objects.all().iterator(chunk_size=2_000):
        job.scope_type = "tenant"
        job.scope_ref = str(job.tenant_id)
        job.storage_target_id = targets[job.tenant_id].id
        job.idempotency_key = f"legacy:{job.id}"
        job.save(update_fields=("scope_type", "scope_ref", "storage_target", "idempotency_key"))

    for archive in Archive.objects.all().iterator(chunk_size=2_000):
        # The legacy row proves only that a locator was catalogued at archived_at.
        # Adapter/checksum/provider/encryption values intentionally stay NULL.
        archive.lifecycle = "available"
        archive.integrity_status = "unknown"
        archive.captured_at = archive.archived_at
        archive.save(update_fields=("lifecycle", "integrity_status", "captured_at"))


def reverse(apps, schema_editor):
    del schema_editor
    Job = apps.get_model("backup_recovery", "BackupJob")
    Schedule = apps.get_model("backup_recovery", "BackupSchedule")
    Archive = apps.get_model("backup_recovery", "BackupArchive")
    Policy = apps.get_model("backup_recovery", "BackupRetentionPolicy")
    StorageTarget = apps.get_model("backup_recovery", "BackupStorageTarget")

    Job.objects.all().update(scope_type=None, scope_ref=None, storage_target=None, idempotency_key=None)
    Schedule.objects.all().update(
        name=None,
        scope_type=None,
        scope_ref=None,
        timezone=None,
        storage_target=None,
        retention_policy=None,
        day_of_week=None,
        day_of_month=None,
    )
    Archive.objects.all().update(lifecycle=None, integrity_status=None, captured_at=None)
    StorageTarget.objects.filter(created_by=MIGRATION_ACTOR).delete()
    Policy.objects.filter(created_by=MIGRATION_ACTOR).delete()


class Migration(migrations.Migration):
    dependencies = [("backup_recovery", "0004_add_catalog_domain_fields")]
    operations = [migrations.RunPython(forward, reverse)]
