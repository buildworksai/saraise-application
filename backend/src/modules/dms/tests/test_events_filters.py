"""Stable event, extension, and bounded-filter contract tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from django.http import QueryDict
from django.utils import timezone

from src.modules.dms import events
from src.modules.dms.events import (
    DmsOperation,
    DocumentEventData,
    ExtensionCommand,
    ExtensionOperationError,
    FolderEventData,
    GuardDecision,
    PermissionEventData,
    ShareEventData,
    VersionEventData,
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
    DocumentShareFilterSet,
    DocumentVersionFilterSet,
    FilterValidationError,
    FolderFilterSet,
    RequiredDocumentFilterSet,
)
from src.modules.dms.models import Document, DocumentPermission, DocumentShare, DocumentVersion, Folder

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
def test_domain_event_accepts_all_typed_payload_variants():
    tenant_id, actor_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    version_id, document_version_id = uuid.uuid4(), uuid.uuid4()
    permission_id, share_id = uuid.uuid4(), uuid.uuid4()

    uploaded = publish_domain_event(
        tenant_id,
        events.DOCUMENT_UPLOADED,
        "document",
        document_id,
        actor_id=actor_id,
        payload=DocumentEventData(
            document_id=document_id,
            version_id=version_id,
            document_version_id=document_version_id,
            version_number=1,
            size_bytes=42,
            mime_type="application/pdf",
            storage_backend="django",
        ),
    )
    assert uploaded.payload["data"] == {
        "document_id": str(document_id),
        "version_id": str(version_id),
        "document_version_id": str(document_version_id),
        "version_number": 1,
        "size_bytes": 42,
        "mime_type": "application/pdf",
        "storage_backend": "django",
    }

    restored = publish_domain_event(
        tenant_id,
        events.VERSION_RESTORED,
        "version",
        document_version_id,
        actor_id=actor_id,
        payload=VersionEventData(
            document_id=document_id,
            version_id=version_id,
            document_version_id=document_version_id,
            version_number=2,
            source_version_id=version_id,
        ),
    )
    assert restored.payload["data"]["source_version_id"] == str(version_id)

    granted = publish_domain_event(
        tenant_id,
        events.PERMISSION_GRANTED,
        "permission",
        permission_id,
        actor_id=actor_id,
        payload=PermissionEventData(
            document_id=document_id,
            permission_id=permission_id,
            principal_type="user",
            permission="read",
        ),
    )
    assert granted.payload["data"]["principal_type"] == "user"

    shared = publish_domain_event(
        tenant_id,
        events.SHARE_CREATED,
        "share",
        share_id,
        actor_id=actor_id,
        payload=ShareEventData(
            document_id=document_id,
            share_id=share_id,
            version_id=version_id,
            expires_at="2026-08-02T00:00:00Z",
            max_access_count=3,
            access_count=0,
        ),
    )
    assert shared.payload["data"]["max_access_count"] == 3


@pytest.mark.django_db
def test_event_boundary_rejects_unsupported_types_identifiers_and_secrets():
    valid = uuid.uuid4()
    with pytest.raises(ValueError, match="Unsupported"):
        publish_domain_event(valid, "dms.fake", "folder", valid, actor_id=None)
    with pytest.raises(ValueError, match="aggregate_type"):
        publish_domain_event(valid, events.FOLDER_CREATED, "", valid, actor_id=None)
    with pytest.raises(ValueError, match="tenant_id"):
        publish_domain_event("bad", events.FOLDER_CREATED, "folder", valid, actor_id=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="aggregate_id"):
        publish_domain_event(valid, events.FOLDER_CREATED, "folder", "bad", actor_id=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="actor_id"):
        publish_domain_event(valid, events.FOLDER_CREATED, "folder", valid, actor_id="bad")  # type: ignore[arg-type]
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


@pytest.mark.django_db
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


def test_required_operation_without_configured_guard_fails_closed(monkeypatch):
    from src.modules.dms.services import DmsConfigurationService

    monkeypatch.setattr(
        DmsConfigurationService,
        "runtime_values",
        staticmethod(lambda tenant_id: {"governance_required_operations": ["download"]}),
    )
    configure_operation_guards({})

    with pytest.raises(ExtensionOperationError) as unavailable:
        run_operation_guards(uuid.uuid4(), DmsOperation.DOWNLOAD, uuid.uuid4())

    assert unavailable.value.code == "guard_unavailable"


@pytest.mark.parametrize("required_operations", ["download", 7])
def test_required_operations_policy_must_be_a_sequence(
    monkeypatch: pytest.MonkeyPatch, required_operations: object
) -> None:
    from src.modules.dms.services import DmsConfigurationService

    monkeypatch.setattr(
        DmsConfigurationService,
        "runtime_values",
        staticmethod(lambda tenant_id: {"governance_required_operations": required_operations}),
    )
    configure_operation_guards({})

    with pytest.raises(ExtensionOperationError) as invalid:
        run_operation_guards(uuid.uuid4(), DmsOperation.DOWNLOAD, uuid.uuid4())

    assert invalid.value.code == "invalid_required_operations"


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
    with pytest.raises(TypeError, match="JSON scalar"):
        enqueue_extension_command(
            ExtensionCommand(
                command="dms.extension.preview",
                idempotency_key="preview-2",
                options={"pages": [1]},
                **values,
            )
        )


def test_base_filters_reject_unknown_ordering_missing_queryset_and_long_search():
    unsupported = BaseFilterSet({"unexpected": "1"}, Document.objects.all())
    assert not unsupported.is_valid()
    assert unsupported.errors == {"query": "Unsupported filters: unexpected."}
    with pytest.raises(ValueError, match="queryset"):
        BaseFilterSet({}).qs
    invalid = BaseFilterSet({"ordering": "name"}, Document.objects.all())
    assert not invalid.is_valid()
    assert invalid.errors == {"ordering": "Ordering field is not allowed."}
    too_long = BaseFilterSet({"search": "x" * 201}, Document.objects.all())
    assert not too_long.is_valid()
    assert too_long.errors == {"search": "Search exceeds tenant policy."}


def test_base_filter_getlist_supports_empty_csv_and_native_list_inputs() -> None:
    assert BaseFilterSet({"tags": ""})._getlist("tags") == []
    assert BaseFilterSet({"tags": " legal, ,finance "})._getlist("tags") == ["legal", "finance"]
    assert BaseFilterSet({"tags": ["legal", "finance"]})._getlist("tags") == ["legal", "finance"]


@pytest.mark.parametrize("policy_value", [True, "200"])
def test_base_filter_rejects_non_integer_search_policy(monkeypatch: pytest.MonkeyPatch, policy_value: object) -> None:
    from src.modules.dms.services import DmsConfigurationService

    monkeypatch.setattr(
        DmsConfigurationService,
        "runtime_values",
        staticmethod(lambda tenant_id: {"collection_search_max_length": policy_value}),
    )

    filters = BaseFilterSet({"search": "policy"}, Document.objects.all())

    assert not filters.is_valid()
    assert filters.errors == {"collection_search_max_length": "Configured policy value must be an integer."}


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
def test_folder_filter_distinguishes_root_empty_and_specific_parent() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    root = Folder.objects.create(
        tenant_id=tenant_id,
        name="Root",
        description="",
        path="Root",
        depth=0,
        created_by=actor_id,
    )
    child = Folder.objects.create(
        tenant_id=tenant_id,
        name="Child",
        description="",
        path="Root/Child",
        depth=1,
        parent=root,
        created_by=actor_id,
    )

    roots = FolderFilterSet({"parent_id": "root"}, Folder.objects.all())
    assert roots.is_valid()
    assert list(roots.qs) == [root]

    specific = FolderFilterSet({"parent_id": str(root.id)}, Folder.objects.all())
    assert specific.is_valid()
    assert list(specific.qs) == [child]

    unbounded = FolderFilterSet({"parent_id": ""}, Folder.objects.all())
    assert unbounded.is_valid()
    assert set(unbounded.qs) == {root, child}


@pytest.mark.django_db
def test_document_tag_filters_allow_exact_tenant_policy_boundaries():
    tags = [f"tag{i}" for i in range(10)]
    exact_count = DocumentFilterSet({"tags": ",".join(tags)}, Document.objects.all())
    assert exact_count.is_valid(), exact_count.errors

    exact_length = DocumentFilterSet({"tags": "x" * 64}, Document.objects.all())
    assert exact_length.is_valid(), exact_length.errors


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


@pytest.mark.django_db
def test_required_document_filters_share_the_same_exact_document_id_contract() -> None:
    document_id = uuid.uuid4()
    filters: list[RequiredDocumentFilterSet] = [
        DocumentVersionFilterSet({"document_id": str(document_id)}, DocumentVersion.objects.all()),
        DocumentPermissionFilterSet({"document_id": str(document_id)}, DocumentPermission.objects.all()),
        DocumentShareFilterSet({"document_id": str(document_id)}, DocumentShare.objects.all()),
    ]

    for filter_set in filters:
        assert filter_set.is_valid(), filter_set.errors
        assert str(filter_set.qs.query).count(str(document_id).replace("-", "")) >= 1

    invalid = DocumentShareFilterSet({"document_id": "bad"}, DocumentShare.objects.all())
    assert not invalid.is_valid()
    assert invalid.errors == {"document_id": "Must be a valid UUID."}
