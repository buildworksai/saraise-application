"""Transactional and failure-path tests for every public DMS service."""

from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.dms.models import Document, DocumentVersion
from src.modules.dms.services import (
    DmsConflict,
    DmsNotFound,
    DmsPermissionDenied,
    DmsValidationError,
    DocumentService,
    FolderService,
    PermissionService,
    PrincipalSummary,
    ShareService,
    VersionService,
)
from src.modules.dms.storage import StorageHealth, StoredObject

pytest_plugins = ["src.core.testing"]


@dataclass
class QuotaResult:
    allowed: bool
    remaining: int = 10_000_000


class AllowQuota:
    def consume(self, tenant_id, resource, *, cost=1):
        del tenant_id, resource, cost
        return QuotaResult(True)


class DenyQuota:
    def consume(self, tenant_id, resource, *, cost=1):
        del tenant_id, resource, cost
        return QuotaResult(False, 0)


class MemoryStorage:
    backend_name = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_save = False
        self.fail_delete = False

    def save(self, key, stream, *, declared_size=None, max_size_bytes=None, declared_mime_type=None):
        del max_size_bytes
        if self.fail_save:
            raise RuntimeError("storage unavailable")
        data = stream.read()
        if declared_size is not None and declared_size != len(data):
            raise ValueError("size mismatch")
        self.objects[key] = data
        return StoredObject(
            key=key,
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            mime_type=declared_mime_type or "text/plain",
        )

    def open(self, key):
        return io.BytesIO(self.objects[key])

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        if self.fail_delete:
            raise RuntimeError("cleanup unavailable")
        self.deleted.append(key)
        self.objects.pop(key, None)

    def health_probe(self):
        return StorageHealth(True, "healthy", 0.1, "ready")


class Directory:
    def __init__(self, principal_id: uuid.UUID) -> None:
        self.principal_id = principal_id

    def validate_principal(self, tenant_id, principal_type, principal_id):
        del tenant_id
        return principal_type == "user" and principal_id == self.principal_id

    def principals_for_actor(self, tenant_id, actor_id):
        del tenant_id
        return {("user", actor_id)}

    def search(self, tenant_id, query, principal_type, limit):
        del tenant_id, query, principal_type, limit
        return [PrincipalSummary(self.principal_id, "user", "Reader")]


@pytest.fixture
def identities() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


def upload_file(name: str = "evidence.txt", content: bytes = b"durable evidence") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="text/plain")


@pytest.mark.django_db
def test_folder_service_create_list_update_move_and_guarded_delete(identities) -> None:
    tenant, owner, _, _ = identities
    service = FolderService()
    root = service.create_folder(tenant, owner, name=" Finance ")
    child = service.create_folder(tenant, owner, name="Reports", parent_id=root.id)
    grandchild = service.create_folder(tenant, owner, name="2026", parent_id=child.id)

    assert root.path == "Finance"
    assert child.path == "Finance/Reports"
    assert service.list_contents(tenant, owner, folder_id=root.id).folders == [child]
    renamed = service.update_folder(tenant, owner, root.id, name="Treasury")
    grandchild.refresh_from_db()
    assert renamed.path == "Treasury"
    assert grandchild.path == "Treasury/Reports/2026"

    with pytest.raises(DmsValidationError):
        service.move_folder(tenant, owner, root.id, parent_id=grandchild.id)
    with pytest.raises(DmsConflict):
        service.delete_folder(tenant, owner, root.id)

    moved = service.move_folder(tenant, owner, child.id, parent_id=None)
    assert moved.depth == 0
    grandchild.refresh_from_db()
    assert grandchild.path == "Reports/2026"
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="dms.folder.moved").exists()


@pytest.mark.django_db
def test_folder_service_rejects_foreign_parent_and_depth_overflow(identities) -> None:
    tenant_a, owner, tenant_b, _ = identities
    foreign = FolderService().create_folder(tenant_b, owner, name="Foreign")
    with pytest.raises(DmsNotFound):
        FolderService().create_folder(tenant_a, owner, name="Spoofed", parent_id=foreign.id)

    parent = None
    service = FolderService()
    for depth in range(11):
        parent = service.create_folder(tenant_a, owner, name=f"L{depth}", parent_id=parent.id if parent else None)
    with pytest.raises(DmsValidationError):
        service.create_folder(tenant_a, owner, name="Too deep", parent_id=parent.id)


@pytest.mark.django_db
def test_upload_creates_document_version_storage_and_outbox_atomically(identities, storage) -> None:
    tenant, owner, _, _ = identities
    folder = FolderService().create_folder(tenant, owner, name="Records")
    service = DocumentService(storage=storage, quota_service=AllowQuota())
    document = service.upload_document(
        tenant,
        owner,
        file=upload_file(),
        name="Evidence",
        folder_id=folder.id,
        tags=["Legal", "legal", " 2026 "],
        metadata={"case": 42, "reviewed": False},
    )

    document.refresh_from_db()
    assert document.folder == folder
    assert document.tags == ["legal", "2026"]
    assert document.version_count == 1
    assert document.current_version is not None
    assert document.current_version.storage_backend == "memory"
    assert storage.exists(document.current_version.storage_key)
    event = OutboxEvent.objects.for_tenant(tenant).get(event_type="dms.document.uploaded")
    assert event.payload["data"]["document_version_id"] == str(document.current_version_id)


@pytest.mark.django_db
def test_upload_validates_before_storage_and_compensates_quota_denial(identities, storage) -> None:
    tenant, owner, foreign_tenant, _ = identities
    foreign = FolderService().create_folder(foreign_tenant, owner, name="Foreign")
    service = DocumentService(storage=storage, quota_service=AllowQuota())
    with pytest.raises(DmsNotFound):
        service.upload_document(tenant, owner, file=upload_file(), name="No", folder_id=foreign.id)
    assert storage.objects == {}

    denied = DocumentService(storage=storage, quota_service=DenyQuota())
    with pytest.raises(DmsPermissionDenied):
        denied.upload_document(tenant, owner, file=upload_file(), name="Quota denied")
    assert storage.objects == {}
    assert len(storage.deleted) == 1
    assert not Document.objects.for_tenant(tenant).exists()


@pytest.mark.django_db
def test_storage_failure_never_creates_metadata(identities, storage) -> None:
    tenant, owner, _, _ = identities
    storage.fail_save = True
    with pytest.raises(RuntimeError):
        DocumentService(storage=storage, quota_service=AllowQuota()).upload_document(
            tenant, owner, file=upload_file(), name="Failure"
        )
    assert not Document.objects.for_tenant(tenant).exists()
    assert not OutboxEvent.objects.for_tenant(tenant).filter(event_type="dms.document.uploaded").exists()


@pytest.mark.django_db
def test_document_update_uses_revision_and_preserves_extension_metadata(identities, storage) -> None:
    tenant, owner, _, _ = identities
    service = DocumentService(storage=storage, quota_service=AllowQuota())
    document = service.upload_document(tenant, owner, file=upload_file(), name="Original")
    Document.objects.filter(id=document.id).update(metadata={"_extensions": {"paid.ocr": {"schema_version": 1}}})
    document.refresh_from_db()

    stale_revision = document.updated_at - timedelta(seconds=1)
    with pytest.raises(DmsConflict):
        service.update_document(tenant, owner, document.id, expected_updated_at=stale_revision, name="Lost update")
    updated = service.update_document(
        tenant,
        owner,
        document.id,
        expected_updated_at=document.updated_at,
        name="Renamed",
        metadata={"customer": "A"},
    )
    assert updated.metadata["customer"] == "A"
    assert "paid.ocr" in updated.metadata["_extensions"]


@pytest.mark.django_db
def test_version_create_restore_download_and_integrity(identities, storage) -> None:
    tenant, owner, _, _ = identities
    documents = DocumentService(storage=storage, quota_service=AllowQuota())
    document = documents.upload_document(tenant, owner, file=upload_file(content=b"one"), name="Versioned")
    versions = VersionService(documents)
    second = versions.create_version(
        tenant,
        owner,
        document.id,
        file=upload_file(content=b"two"),
        change_note="Replacement",
    )
    restored = versions.restore_version(tenant, owner, document.current_version_id, change_note="Restore original")

    assert second.version_number == 2
    assert restored.version_number == 3
    assert restored.source_version_id == document.current_version_id
    assert list(versions.list_versions(tenant, owner, document.id).values_list("version_number", flat=True)) == [
        3,
        2,
        1,
    ]
    artifact = documents.download_document(tenant, owner, document.id, version_id=second.id)
    assert b"".join(artifact.stream) == b"two"

    storage.objects[second.storage_key] = b"corrupt"
    corrupted = documents.download_document(tenant, owner, document.id, version_id=second.id)
    with pytest.raises(Exception, match="integrity"):
        b"".join(corrupted.stream)


@pytest.mark.django_db
def test_permission_implication_grant_update_revoke_and_acl(identities, storage) -> None:
    tenant, owner, reader, _ = identities
    directory = Directory(reader)
    permissions = PermissionService(directory)
    documents = DocumentService(storage=storage, permission_service=permissions, quota_service=AllowQuota())
    document = documents.upload_document(tenant, owner, file=upload_file(), name="Shared internally")

    grant = permissions.grant_permission(
        tenant,
        owner,
        document.id,
        principal_type="user",
        principal_id=reader,
        permission="write",
    )
    assert permissions.has_document_access(tenant, reader, document, "read")
    assert permissions.has_document_access(tenant, reader, document, "write")
    assert not permissions.has_document_access(tenant, reader, document, "delete")
    grant = permissions.update_permission(tenant, owner, grant.id, permission="manage")
    assert grant.permission == "manage"
    permissions.revoke_permission(tenant, owner, grant.id)
    assert not permissions.has_document_access(tenant, reader, document, "read")
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="dms.permission.revoked").exists()


@pytest.mark.django_db
def test_share_is_version_pinned_digest_only_consumed_and_revoked(identities, storage) -> None:
    tenant, owner, _, _ = identities
    documents = DocumentService(storage=storage, quota_service=AllowQuota())
    document = documents.upload_document(tenant, owner, file=upload_file(content=b"shared"), name="Public")
    shares = ShareService(documents)
    created = shares.create_share(
        tenant,
        owner,
        document.id,
        expires_at=timezone.now() + timedelta(days=1),
        max_access_count=1,
    )
    token = created.share_url.split("/")[-3]
    assert token not in created.share.token_digest
    assert created.share.version_id == document.current_version_id
    assert b"".join(shares.consume_share(token).stream) == b"shared"
    with pytest.raises(DmsNotFound):
        shares.consume_share(token)
    revoked = shares.revoke_share(tenant, owner, created.share.id)
    assert shares.revoke_share(tenant, owner, created.share.id).revoked_at == revoked.revoked_at


@pytest.mark.django_db
def test_document_soft_delete_retains_versions_and_revokes_shares(identities, storage) -> None:
    tenant, owner, _, _ = identities
    documents = DocumentService(storage=storage, quota_service=AllowQuota())
    document = documents.upload_document(tenant, owner, file=upload_file(), name="Retained")
    share = (
        ShareService(documents)
        .create_share(tenant, owner, document.id, expires_at=timezone.now() + timedelta(hours=1))
        .share
    )
    version_id = document.current_version_id

    documents.delete_document(tenant, owner, document.id)
    document.refresh_from_db()
    share.refresh_from_db()
    assert document.is_deleted
    assert DocumentVersion.objects.filter(id=version_id).exists()
    assert share.revoked_at is not None
    assert storage.objects
