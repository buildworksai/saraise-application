"""Public CRM response and interactive activity DTO security tests."""

import uuid

import pytest
from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob
from src.modules.crm.serializers import (
    AccountReadSerializer,
    ActivityCreateSerializer,
    ActivityReadSerializer,
    ActivityUpdateSerializer,
    AsyncJobReadSerializer,
    ContactReadSerializer,
    LeadReadSerializer,
    OpportunityReadSerializer,
)

INTERNAL_RESPONSE_FIELDS = {
    "tenant_id",
    "created_by",
    "updated_by",
    "is_deleted",
    "deleted_at",
    "metadata",
    "external_id",
}


@pytest.mark.parametrize(
    "serializer_class",
    [
        LeadReadSerializer,
        AccountReadSerializer,
        ContactReadSerializer,
        OpportunityReadSerializer,
        ActivityReadSerializer,
    ],
)
def test_public_read_dtos_exclude_tenant_deletion_actor_and_metadata(
    serializer_class: type[serializers.Serializer],
) -> None:
    assert INTERNAL_RESPONSE_FIELDS.isdisjoint(serializer_class().fields)


@pytest.mark.parametrize("serializer_class", [ActivityCreateSerializer, ActivityUpdateSerializer])
def test_interactive_activity_dtos_reject_integration_owned_external_id(
    serializer_class: type[serializers.Serializer],
) -> None:
    serializer = serializer_class(data={"external_id": "spoofed-provider-identity"}, partial=True)
    assert serializer.is_valid() is False
    assert serializer.errors == {"external_id": ["Unknown field."]}


@pytest.mark.django_db
def test_async_job_read_dto_exposes_persisted_polling_result_and_failure() -> None:
    job = AsyncJob.objects.create(
        tenant_id=uuid.uuid4(),
        actor_id="operator",
        command="crm.score_lead",
        status="failed",
        idempotency_key="polling-test",
        payload={},
        result={"partial": "evidence"},
        error_message="Provider timed out.",
        correlation_id="polling-correlation",
    )

    data = AsyncJobReadSerializer(job).data

    assert data["id"] == str(job.id)
    assert data["status"] == "failed"
    assert data["result"] == {"partial": "evidence"}
    assert data["error"]["message"] == "Provider timed out."
    assert data["progress"] is None
