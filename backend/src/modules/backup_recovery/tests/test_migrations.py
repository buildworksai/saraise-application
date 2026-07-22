"""Migration contract tests, including typed PostgreSQL RLS statements."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

LATEST = ("backup_recovery", "0007_enable_catalog_rls")
LEGACY = ("backup_recovery", "0001_initial")


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_rows_without_fabricated_evidence() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    apps = executor.loader.project_state([LEGACY]).apps
    tenant_id = str(uuid.uuid4())
    Job = apps.get_model("backup_recovery", "BackupJob")
    Archive = apps.get_model("backup_recovery", "BackupArchive")
    job = Job.objects.create(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        backup_type="full",
        status="running",
        storage_location="legacy-location",
        created_by="legacy-user",
    )
    archive_id = str(uuid.uuid4())
    Archive.objects.create(
        id=archive_id,
        tenant_id=tenant_id,
        backup_job_id=job.id,
        archive_location="legacy-locator",
        created_by="legacy-user",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    latest_apps = executor.loader.project_state([LATEST]).apps
    migrated = latest_apps.get_model("backup_recovery", "BackupArchive").objects.get(pk=archive_id)
    assert migrated.artifact_locator_ref == "legacy-locator"
    assert migrated.adapter_key is None
    assert migrated.checksum_digest is None
    assert migrated.provider_acknowledgement is None
    assert migrated.encryption_key_ref == ""

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    legacy_apps = executor.loader.project_state([LEGACY]).apps
    assert legacy_apps.get_model("backup_recovery", "BackupJob").objects.filter(pk=job.id).exists()
    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])


def test_invalid_uuid_preflight_is_sanitized() -> None:
    migration = importlib.import_module("src.modules.backup_recovery.migrations.0002_validate_legacy_uuid_values")
    queryset = Mock()
    queryset.values_list.return_value.iterator.return_value = [("not-a-uuid-sensitive-tail", str(uuid.uuid4()))]
    model = SimpleNamespace(objects=queryset)
    apps = Mock()
    apps.get_model.return_value = model
    with pytest.raises(RuntimeError, match="Invalid legacy UUID values") as raised:
        migration.validate_uuid_values(apps, None)
    assert "sensitive-tail" not in str(raised.value)


def test_rls_is_explicit_noop_on_sqlite_and_enabled_for_every_postgres_table() -> None:
    migration = importlib.import_module("src.modules.backup_recovery.migrations.0007_enable_catalog_rls")
    sqlite_editor = SimpleNamespace(connection=SimpleNamespace(vendor="sqlite"), execute=Mock())
    migration.enable_rls(None, sqlite_editor)
    migration.disable_rls(None, sqlite_editor)
    sqlite_editor.execute.assert_not_called()

    postgres = SimpleNamespace(
        connection=SimpleNamespace(vendor="postgresql"),
        execute=Mock(),
        quote_name=lambda value: f'"{value}"',
    )
    migration.enable_rls(None, postgres)
    assert postgres.execute.call_count == len(migration.TABLES)
    assert all("saraise_enable_rls" in call.args[0] for call in postgres.execute.call_args_list)
    migration.disable_rls(None, postgres)
    rendered = "\n".join(call.args[0] for call in postgres.execute.call_args_list)
    assert "NO FORCE ROW LEVEL SECURITY" in rendered
    assert "DISABLE ROW LEVEL SECURITY" in rendered
