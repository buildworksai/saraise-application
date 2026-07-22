"""Stable event, extension, and bounded-filter contract tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from django.http import QueryDict
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.dms import events
from src.modules.dms.events import (
    DmsOperation,
    ExtensionCommand,
    ExtensionOperationError,
    FolderEventData,
    GuardDecision,
    configure_operation_guards,
    enqueue_extension_command,
    publish_domain_event,
    publish_storage_cleanup_event,
    register_operation_guard,
    run_operation_guards,
    unregister_operation_guard,
)
from src.modules.dms.filters import (
    BaseFilterSet,
    DocumentFilterSet,
    DocumentPermissionFilterSet,
    FilterValidationError,
    FolderFilterSet,
)
from src.modules.dms.models import Document, DocumentPermission, Folder

pytest_plugins = ["src.core.testing"]


@pytest.mark.django_db
def test_domain_event_persists_versioned_allowlisted_scalar_envelope():
    tenant_id, actor_id, folder_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event = publish_domain_event(
        tenant_id,
        events.FOLDER_CREATED,
        " folder ",
        folder_id,
        actor_id=actor_id,
        payload=FolderEventData(folder_id=folder_id, depth=0),
        correlation_id="corr-dms-event",
        causation_id="cause-1",
    )
    assert event.aggregate_type == "folder"
    assert event.payload["schema_version"] == 1
    assert event.payload["tenant_id"] == str(tenant_id)
    assert event.payload["actor_id"] == str(actor_id)
    assert event.payload["correlation_id"] == "corr-dms-event"
    assert event.payload["causation_id"] == "cause-1"
    assert event.payload["data"] == {"folder_id": str(folder_id), "depth": 0}


@pytest.mark.django_db
def test_event_boundary_rejects_unsupported_types_identifiers_and_secrets():
    valid = uuid.uuid4()
    with pytest.raises(ValueError, match="Unsupported"):
        publish_domain_event(valid, "dms.fake", "folder", valid, actor_id=None)
    with pytest.raises(ValueError, match="aggregate_type"):
        publish_domain_event(valid, events.FOLDER_CREATED, "", valid, actor_id=None)
    with pytest.raises(ValueError, match="tenant_id"):
        publish_domain_event("bad", events.FOLDER_CREATED, "folder", valid, actor_id=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-allowlisted"):
        publish_domain_event(
            valid,
            events.FOLDER_CREATED,
            "folder",
            valid,
            actor_id=None,
            payload={"share_token": "secret"},
        )
    with pytest.raises(TypeError, match="JSON scalar"):
        publish_domain_event(
            valid,
            events.FOLDER_CREATED,
            "folder",
            valid,
            actor_id=None,
            payload={"depth": [1]},
        )


@pytest.mark.django_db
def test_cleanup_command_is_durable_and_provider_qualified():
    tenant_id, actor_id, aggregate_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event = publish_storage_cleanup_event(
        tenant_id,
        actor_id,
        aggregate_id=aggregate_id,
        storage_backend="archive",
        storage_key="opaque/key",
    )
    assert event.event_type == events.STORAGE_CLEANUP_REQUIRED
    assert event.payload["data"]["storage_backend"] == "archive"
    assert event.payload["data"]["storage_key"] == "opaque/key"


@dataclass
class Guard:
    decision: object = GuardDecision(True)
    error: Exception | None = None

    def evaluate(self, context):
        if self.error:
            raise self.error
        assert context.operation in DmsOperation
        return self.decision


def test_operation_guard_registry_is_fail_closed_and_replaceable():
    tenant_id, document_id = uuid.uuid4(), uuid.uuid4()
    configure_operation_guards({})
    run_operation_guards(tenant_id, "download", document_id)
    register_operation_guard("scanner", Guard())
    with pytest.raises(ValueError, match="already registered"):
        register_operation_guard("scanner", Guard())
    register_operation_guard("scanner", Guard(GuardDecision(False, "infected")), replace=True)
    with pytest.raises(ExtensionOperationError) as denied:
        run_operation_guards(tenant_id, DmsOperation.DOWNLOAD, document_id)
    assert denied.value.code == "infected"
    register_operation_guard("scanner", Guard(object()), replace=True)
    with pytest.raises(ExtensionOperationError) as invalid:
        run_operation_guards(tenant_id, "download", document_id)
    assert invalid.value.code == "invalid_guard_decision"
    register_operation_guard("scanner", Guard(error=TimeoutError()), replace=True)
    with pytest.raises(ExtensionOperationError) as unavailable:
        run_operation_guards(tenant_id, "download", document_id)
    assert unavailable.value.code == "guard_unavailable"
    assert unregister_operation_guard("SCANNER") is not None
    assert unregister_operation_guard("missing") is None
    with pytest.raises(ExtensionOperationError) as unsupported:
        run_operation_guards(tenant_id, "unsupported", document_id)
    assert unsupported.value.code == "unsupported_operation"


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_guard_configuration_validates_extensions(name):
    with pytest.raises(ValueError):
        register_operation_guard(name, Guard())
    with pytest.raises(TypeError):
        configure_operation_guards({"invalid": object()})  # type: ignore[dict-item]


def test_extension_command_requires_worker_evidence_and_serializes(monkeypatch):
    values = {
        "tenant_id": uuid.uuid4(),
        "actor_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "version_id": uuid.uuid4(),
    }
    captured: dict[str, object] = {}
    monkeypatch.setattr(events, "get_handler", lambda command: object())

    def fake_enqueue(tenant_id, actor_id, command, payload, idempotency_key):
        captured.update(locals())
        return "job"

    monkeypatch.setattr(events, "enqueue", fake_enqueue)
    command = ExtensionCommand(
        command="dms.extension.preview",
        idempotency_key="preview-1",
        options={"page": 1},
        **values,
    )
    assert enqueue_extension_command(command) == "job"
    assert captured["payload"]["version_id"] == str(values["version_id"])
    with pytest.raises(TypeError):
        enqueue_extension_command(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="namespace"):
        enqueue_extension_command(ExtensionCommand(command="preview", idempotency_key="x", **values))


def test_base_filters_reject_unknown_ordering_missing_queryset_and_long_search():
    assert not BaseFilterSet({"unexpected": "1"}, Document.objects.all()).is_valid()
    with pytest.raises(ValueError, match="queryset"):
        BaseFilterSet({}).qs
    invalid = BaseFilterSet({"ordering": "name"}, Document.objects.all())
    assert not invalid.is_valid() and "ordering" in invalid.errors
    too_long = BaseFilterSet({"search": "x" * 201}, Document.objects.all())
    assert not too_long.is_valid() and "search" in too_long.errors


@pytest.mark.django_db
def test_folder_and_document_filters_apply_allowlisted_fields():
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    folder = Folder.objects.create(
        tenant_id=tenant_id,
        name="Policies",
        description="governed records",
        path="Policies",
        depth=0,
        created_by=actor_id,
    )
    document = Document.objects.create(
        tenant_id=tenant_id,
        name="Retention policy",
        description="regulated",
        folder=folder,
        tags=["legal"],
        metadata={"class": "policy"},
        created_by=actor_id,
    )
    folders = FolderFilterSet({"parent_id": "root", "search": "governed"}, Folder.objects.all())
    assert folders.is_valid() and list(folders.qs) == [folder]
    params = QueryDict(mutable=True)
    params.update(
        {
            "folder": str(folder.id),
            "creator": str(actor_id),
            "tags": "legal",
            "modified_after": (timezone.now() - timedelta(days=1)).date().isoformat(),
            "modified_before": (timezone.now() + timedelta(days=1)).date().isoformat(),
            "search": "policy",
            "ordering": "name",
        }
    )
    documents = DocumentFilterSet(params, Document.objects.all())
    assert documents.is_valid() and list(documents.qs) == [document]


@pytest.mark.django_db
def test_document_filter_validation_and_required_relation_filter():
    queryset = Document.objects.all()
    for params, field in [
        ({"folder": "bad"}, "folder"),
        ({"creator": "bad"}, "creator"),
        ({"mime_type": "invalid"}, "mime_type"),
        ({"tags": ",".join(["tag"] * 11)}, "tags"),
        ({"modified_after": "not-a-date"}, "modified_after"),
        ({"modified_after": "2026-07-23", "modified_before": "2026-07-22"}, "modified_after"),
    ]:
        filters = DocumentFilterSet(params, queryset)
        assert not filters.is_valid() and field in filters.errors
    required = DocumentPermissionFilterSet({}, DocumentPermission.objects.all())
    assert not required.is_valid() and "document_id" in required.errors
    with pytest.raises(FilterValidationError):
        required.qs
