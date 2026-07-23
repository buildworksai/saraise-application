"""Model invariants for Regional tenant data and immutable evidence."""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

from src.modules.regional.models import RegionalAuditRecord, RegionalResource


@pytest.mark.django_db
class TestRegionalModels:
    def test_resource_uses_uuid_tenant_and_soft_delete_guard(self):
        tenant = uuid.uuid4()
        resource = RegionalResource.objects.create(
            tenant_id=tenant,
            name="Test Resource",
            description="Test description",
            is_active=True,
            created_by="user-123",
        )
        assert resource.id is not None
        assert resource.tenant_id == tenant
        assert str(resource) == f"Test Resource ({resource.id})"
        with pytest.raises(ProtectedError):
            resource.delete()

    def test_resource_requires_valid_tenant_uuid(self):
        with pytest.raises(ValidationError):
            RegionalResource.objects.create(
                tenant_id="not-a-uuid",
                name="Test Resource",
                is_active=True,
                created_by="user-123",
            )

    def test_audit_records_are_immutable(self):
        record = RegionalAuditRecord.objects.create(
            tenant_id=uuid.uuid4(),
            actor_id="user-123",
            correlation_id=uuid.uuid4(),
            operation="resource.create",
            entity_type="resource",
            entity_id=uuid.uuid4(),
            before_value={},
            after_value={"name": "Test"},
        )
        record.operation = "tampered"
        with pytest.raises(ValidationError):
            record.save()
        with pytest.raises(ProtectedError):
            RegionalAuditRecord.objects.filter(pk=record.pk).delete()
