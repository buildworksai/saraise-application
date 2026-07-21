"""Durable handler registration and tenant-context worker tests."""

from __future__ import annotations

import inspect
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from src.core.async_jobs.services import get_handler
from src.core.tenancy import MissingTenantContext
from src.modules.document_intelligence import tasks
from src.modules.document_intelligence.models import (
    DocumentClassification,
    DocumentExtraction,
    ExtractionStatus,
)

from .factories import (
    AsyncJobFactory,
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DocumentClassificationFactory,
    DocumentExtractionFactory,
)

pytestmark = pytest.mark.django_db


COMMANDS = {
    "document_intelligence.extract",
    "document_intelligence.classify",
    "document_intelligence.train_classifier",
    "document_intelligence.cancel_stale_jobs",
    "document_intelligence.enforce_retention",
}


def test_all_commands_have_registered_handlers() -> None:
    for command in COMMANDS:
        assert callable(get_handler(command))


@pytest.mark.parametrize(
    "worker",
    [
        tasks.run_extraction_task,
        tasks.run_classification_task,
        tasks.run_training_task,
        tasks.cancel_stale_jobs_task,
        tasks.enforce_retention_task,
    ],
)
def test_worker_signatures_are_tenant_first_keyword_only(worker: object) -> None:
    parameters = list(inspect.signature(worker).parameters.values())
    assert parameters[0].name == "tenant_id"
    assert parameters[0].kind == inspect.Parameter.KEYWORD_ONLY
    assert getattr(worker, "isolation_contract") == "tenant_context"


def test_missing_worker_tenant_fails_before_service_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    service = Mock()
    monkeypatch.setattr(tasks, "DocumentExtractionService", Mock(return_value=service))
    with pytest.raises(MissingTenantContext):
        tasks.run_extraction_task(extraction_id=uuid.uuid4(), async_job_id=uuid.uuid4())
    service.run_extraction.assert_not_called()


def test_extract_handler_parses_identifiers_and_propagates_job_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    extraction_id = uuid.uuid4()
    job = AsyncJobFactory(
        tenant_id=tenant_id,
        command="document_intelligence.extract",
        payload={"extraction_id": str(extraction_id)},
    )
    task = Mock(return_value={"extraction_id": str(extraction_id), "status": "completed"})
    monkeypatch.setattr(tasks, "run_extraction_task", task)

    result = get_handler("document_intelligence.extract")(job)

    assert result["status"] == "completed"
    task.assert_called_once_with(
        tenant_id=tenant_id,
        extraction_id=extraction_id,
        async_job_id=job.id,
    )


def test_invalid_handler_payload_fails_before_worker_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    job = AsyncJobFactory(command="document_intelligence.classify", payload={"classification_id": "not-uuid"})
    worker = Mock()
    monkeypatch.setattr(tasks, "run_classification_task", worker)
    with pytest.raises(ValueError, match="classification_id"):
        get_handler("document_intelligence.classify")(job)
    worker.assert_not_called()


def test_duplicate_terminal_extraction_delivery_returns_stored_result() -> None:
    tenant_id = uuid.uuid4()
    job = AsyncJobFactory(tenant_id=tenant_id, command="document_intelligence.extract")
    extraction = CompletedDocumentExtractionFactory(tenant_id=tenant_id, async_job_id=job.id)
    job.payload = {"extraction_id": str(extraction.id)}
    job.save(update_fields=["payload", "updated_at"])

    first = get_handler("document_intelligence.extract")(job)
    second = get_handler("document_intelligence.extract")(job)

    assert first == second == {"extraction_id": str(extraction.id), "status": ExtractionStatus.COMPLETED}
    assert extraction.pages.count() == 0


def test_stale_recovery_is_tenant_scoped() -> None:
    tenant_id = uuid.uuid4()
    foreign_tenant = uuid.uuid4()
    actor = uuid.uuid4()
    own_job = AsyncJobFactory(tenant_id=tenant_id, actor_id=str(actor))
    foreign_job = AsyncJobFactory(tenant_id=foreign_tenant, actor_id=str(actor))
    own = DocumentExtractionFactory(
        tenant_id=tenant_id,
        created_by=actor,
        async_job_id=own_job.id,
        status=ExtractionStatus.QUEUED,
    )
    foreign = DocumentExtractionFactory(
        tenant_id=foreign_tenant,
        created_by=actor,
        async_job_id=foreign_job.id,
        status=ExtractionStatus.QUEUED,
    )
    cutoff = timezone.now() - timedelta(hours=24)
    DocumentExtraction.objects.filter(pk__in=[own.id, foreign.id]).update(updated_at=cutoff - timedelta(minutes=1))

    result = tasks.cancel_stale_jobs_task(tenant_id=tenant_id, cutoff=cutoff)

    own.refresh_from_db()
    foreign.refresh_from_db()
    assert result["extractions"] == 1
    assert own.status == ExtractionStatus.CANCELLED
    assert foreign.status == ExtractionStatus.QUEUED


def test_retention_archives_only_terminal_evidence_for_requested_tenant() -> None:
    tenant_id = uuid.uuid4()
    foreign_tenant = uuid.uuid4()
    own_extraction = CompletedDocumentExtractionFactory(tenant_id=tenant_id)
    foreign_extraction = CompletedDocumentExtractionFactory(tenant_id=foreign_tenant)
    own_training = ClassifierTrainingJobFactory(tenant_id=tenant_id)
    own_model = ClassifierModelVersionFactory(tenant_id=tenant_id, training_job=own_training)
    own_classification = DocumentClassificationFactory(tenant_id=tenant_id, model_version=own_model)
    foreign_training = ClassifierTrainingJobFactory(tenant_id=foreign_tenant)
    foreign_model = ClassifierModelVersionFactory(tenant_id=foreign_tenant, training_job=foreign_training)
    foreign_classification = DocumentClassificationFactory(tenant_id=foreign_tenant, model_version=foreign_model)
    cutoff = timezone.now() - timedelta(days=30)
    DocumentExtraction.objects.filter(pk__in=[own_extraction.id, foreign_extraction.id]).update(
        completed_at=cutoff - timedelta(days=1)
    )
    DocumentClassification.objects.filter(pk__in=[own_classification.id, foreign_classification.id]).update(
        completed_at=cutoff - timedelta(days=1)
    )

    result = tasks.enforce_retention_task(tenant_id=tenant_id, cutoff=cutoff)

    for record in (own_extraction, foreign_extraction, own_classification, foreign_classification):
        record.refresh_from_db()
    assert result == {"extractions": 1, "classifications": 1}
    assert own_extraction.is_deleted is True
    assert own_classification.is_deleted is True
    assert foreign_extraction.is_deleted is False
    assert foreign_classification.is_deleted is False


def test_dms_consumer_is_disabled_by_default_and_idempotency_is_event_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    event_id = uuid.uuid4()
    service = Mock()
    monkeypatch.setattr(tasks, "DocumentClassificationService", Mock(return_value=service))
    tasks.configure_auto_classification_policy(lambda _tenant: False)
    assert (
        tasks.consume_dms_document_uploaded(
            tenant_id,
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            event_id=event_id,
        )
        is None
    )
    service.request_classification.assert_not_called()

    tasks.configure_auto_classification_policy(lambda candidate: candidate == tenant_id)
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    tasks.consume_dms_version_created(
        tenant_id,
        document_id=document_id,
        document_version_id=version_id,
        actor_id=actor_id,
        event_id=event_id,
    )
    service.request_classification.assert_called_once_with(
        tenant_id,
        actor_id,
        document_id,
        version_id,
        f"dms.document.uploaded:{event_id}",
    )
