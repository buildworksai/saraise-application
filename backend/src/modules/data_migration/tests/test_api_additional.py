"""Serializer separation, safe limits and filter validation for API v2."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.modules.data_migration.serializers import (
    DataMigrationConfigurationUpdateSerializer,
    ExternalConnectionManagementSerializer,
    MigrationJobCreateSerializer,
    MigrationRunSerializer,
    safe_source_config,
)


def test_safe_source_config_explicitly_removes_sensitive_fields() -> None:
    connection_id = str(uuid4())
    result = safe_source_config({"connection_id": connection_id, "table": "customer", "password": "secret", "headers": {"Authorization": "secret"}})
    assert result == {"connection_id": connection_id, "table": "customer"}


def test_client_cannot_set_tenant_actor_state_or_counters() -> None:
    serializer = MigrationJobCreateSerializer(data={
        "tenant_id": str(uuid4()), "created_by": str(uuid4()), "status": "ready", "configuration_version": 999,
        "name": "Customers", "source_type": "csv", "source_artifact_id": str(uuid4()),
        "source_config": {"batch_size": 100}, "target_adapter": "crm.customer", "target_entity": "customer",
        "write_mode": "create", "lookup_fields": [],
    })
    assert not serializer.is_valid()
    assert set(serializer.errors) >= {"tenant_id", "created_by", "status", "configuration_version"}


def test_connection_management_keeps_credential_reference_write_only() -> None:
    serializer = ExternalConnectionManagementSerializer()
    assert serializer.fields["credential_ref"].write_only is True
    assert "tenant_id" not in serializer.fields
    assert "created_by" not in serializer.fields


def test_run_serializer_never_exposes_async_payload_or_change_evidence() -> None:
    fields = set(MigrationRunSerializer().fields)
    assert "async_job_id" not in fields
    assert "payload" not in fields
    assert "changes" not in fields


@pytest.mark.parametrize(
    ("field", "value"),
    (("batch_size", 0), ("batch_size", 10001), ("connect_timeout_seconds", 121),
     ("read_timeout_seconds", 601), ("retry_count", 11), ("preview_row_limit", 101),
     ("retention_days", 3651), ("rollout_percentage", 101)),
)
def test_configuration_limits_are_unsavable(field: str, value: int) -> None:
    serializer = DataMigrationConfigurationUpdateSerializer(data={"expected_version": 1, field: value})
    assert not serializer.is_valid()
    assert field in serializer.errors


def test_configuration_update_requires_a_change_and_optimistic_version() -> None:
    empty = DataMigrationConfigurationUpdateSerializer(data={"expected_version": 1})
    assert not empty.is_valid()
    missing_version = DataMigrationConfigurationUpdateSerializer(data={"batch_size": 100})
    assert not missing_version.is_valid()
    assert "expected_version" in missing_version.errors
