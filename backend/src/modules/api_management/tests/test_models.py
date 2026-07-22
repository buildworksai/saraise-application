"""Persistence boundary tests for API management."""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from src.modules.api_management.models import ApiManagementAuditRecord, TenantBaseModel


@pytest.mark.django_db
class TestTenantBaseModelModel:
    def test_create_resource_uses_native_uuid_boundaries(self):
        tenant_id = uuid.uuid4()
        resource = TenantBaseModel.objects.create(
            tenant_id=tenant_id,
            name="Test Resource",
            description="Test description",
            created_by="user-123",
            is_active=True,
            idempotency_key=uuid.uuid4(),
        )
        assert isinstance(resource.id, uuid.UUID)
        assert resource.tenant_id == tenant_id

    def test_resource_str_representation(self):
        resource = TenantBaseModel.objects.create(
            tenant_id=uuid.uuid4(),
            name="Test Resource",
            created_by="user-123",
            is_active=True,
            idempotency_key=uuid.uuid4(),
        )
        assert str(resource) == f"Test Resource ({resource.id})"

    def test_resource_config_field_round_trips_json(self):
        resource = TenantBaseModel.objects.create(
            tenant_id=uuid.uuid4(),
            name="Configured",
            config={"key": "value"},
            created_by="user-123",
            is_active=True,
            idempotency_key=uuid.uuid4(),
        )
        resource.refresh_from_db()
        assert resource.config == {"key": "value"}

    def test_resource_rejects_missing_tenant(self):
        resource = TenantBaseModel(
            name="Test Resource",
            created_by="user-123",
            is_active=True,
            idempotency_key=uuid.uuid4(),
        )
        with pytest.raises(ValidationError):
            resource.save()

    def test_audit_record_rejects_update_and_delete(self):
        record = ApiManagementAuditRecord.objects.create(
            tenant_id=uuid.uuid4(),
            target_type="resource",
            target_id=uuid.uuid4(),
            action="create",
            actor_id="actor",
            correlation_id="req_test",
            idempotency_key=uuid.uuid4(),
            before_value=None,
            after_value={"name": "safe"},
            version=1,
        )
        record.action = "tampered"
        with pytest.raises(ValidationError):
            record.save()
        with pytest.raises(ValidationError):
            record.delete()
        with pytest.raises(ValidationError):
            ApiManagementAuditRecord.objects.filter(pk=record.pk).update(action="tampered")

    def test_database_trigger_rejects_raw_audit_update_and_delete(self):
        record = ApiManagementAuditRecord.objects.create(
            tenant_id=uuid.uuid4(),
            target_type="resource",
            target_id=uuid.uuid4(),
            action="create",
            actor_id="actor",
            correlation_id="req_db",
            idempotency_key=uuid.uuid4(),
            before_value=None,
            after_value={},
            version=1,
        )
        with pytest.raises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE api_management_audit_records SET action = %s WHERE id = %s",
                    ["tampered", record.id.hex],
                )
        with pytest.raises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM api_management_audit_records WHERE id = %s", [record.id.hex])
