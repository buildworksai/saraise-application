from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

import pytest
from django.core.exceptions import ValidationError

from ..adapter_registry import BackupScopeProvider, DuplicateRegistration, ExtensionRegistry
from ..factories import retention_policy_factory, storage_target_factory
from ..models import BackupJob
from ..ports import BackupType
from ..services import BackupScheduleService, DomainConflict, RetentionPolicyService

pytestmark = pytest.mark.django_db


def test_extension_registry_normalizes_keys_and_fails_closed_for_missing_entries() -> None:
    registry = ExtensionRegistry[object]()
    value = object()

    assert registry.register(" provider ", value) is value
    assert registry.keys() == ("provider",)
    assert registry.get("provider") is value
    with pytest.raises(DuplicateRegistration):
        registry.register("provider", object())
    replacement = object()
    assert registry.register("provider", replacement, replace=True) is replacement
    assert registry.unregister("provider") is replacement
    with pytest.raises(Exception) as exc:
        registry.get("provider")
    assert getattr(exc.value, "capability", "") == "backup-capture-adapter:provider"
    with pytest.raises(ValueError):
        registry.register("", object())


def test_scope_provider_contract_preserves_validation_and_entitlement_metadata() -> None:
    seen: list[str] = []
    provider = BackupScopeProvider(
        key="files",
        owning_module="backup_recovery",
        display_label="Files",
        supported_backup_types=(BackupType.FULL,),
        selector_schema={"type": "object"},
        entitlement_capability="backup.files",
        validate=seen.append,
    )

    provider.validate("/srv/data")

    assert seen == ["/srv/data"]
    assert provider.supported_backup_types == (BackupType.FULL,)
    assert provider.entitlement_capability == "backup.files"


def test_retention_policy_deactivation_and_delete_block_active_catalog_work(tmp_path) -> None:
    tenant = uuid.uuid4()
    target = storage_target_factory(tenant, locator_prefix_ref=str(tmp_path), is_default=True)
    policy = retention_policy_factory(tenant)
    BackupJob.objects.create(
        tenant_id=tenant,
        backup_type="full",
        scope_type="files",
        scope_ref=str(tmp_path),
        storage_target=target,
        retention_policy=policy,
        status="pending",
        idempotency_key="active-retention",
        created_by="actor",
    )

    service = RetentionPolicyService()
    with pytest.raises(DomainConflict):
        service.deactivate(tenant, "actor", policy.id)
    with pytest.raises(DomainConflict):
        service.delete(tenant, "actor", policy.id)


def test_schedule_computation_rejects_naive_time_unknown_zone_and_missing_time(tmp_path) -> None:
    tenant = uuid.uuid4()
    target = storage_target_factory(tenant, locator_prefix_ref=str(tmp_path), is_default=True)
    policy = retention_policy_factory(tenant)
    service = BackupScheduleService()
    schedule = service.create(
        tenant,
        "actor",
        {
            "name": "Weekly",
            "scope_type": "files",
            "scope_ref": str(tmp_path),
            "backup_type": "full",
            "frequency": "weekly",
            "day_of_week": 1,
            "schedule_time": time(9, 0),
            "timezone": "UTC",
            "is_active": False,
            "storage_target": target,
            "retention_policy": policy,
        },
    )

    with pytest.raises(ValidationError):
        service.compute_next_run(schedule, after=datetime(2026, 8, 3, 12, 0))

    schedule.timezone = "Not/AZone"
    with pytest.raises(ValidationError):
        service.compute_next_run(schedule, after=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))

    schedule.timezone = "UTC"
    schedule.schedule_time = None
    with pytest.raises(ValidationError):
        service.compute_next_run(schedule, after=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))
