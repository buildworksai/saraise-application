"""Persistence invariants for the UUID-native DMS domain."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.dms.managers import ImmutableVersionError
from src.modules.dms.models import (
    Document,
    DocumentPermission,
    DocumentShare,
    DocumentVersion,
    Folder,
    PermissionLevel,
)
from src.modules.dms.tests.factories import make_document_graph, make_folder, make_share

pytest_plugins = ["src.core.testing"]


@pytest.fixture
def identities() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest.mark.django_db
def test_domain_uses_uuid_identity_canonical_tenancy_and_soft_delete_manager(identities) -> None:
    tenant_id, actor_id, _ = identities
    folder = make_folder(tenant_id=tenant_id, actor_id=actor_id)

    assert isinstance(folder, TenantScopedModel)
    assert isinstance(folder, TimestampedModel)
    assert isinstance(folder.id, uuid.UUID)
    assert Folder._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
    assert Folder._meta.get_field("tenant_id").db_index is True
    assert Folder.objects.for_tenant(tenant_id).alive().get() == folder

    folder.is_deleted = True
    folder.deleted_at = timezone.now()
    folder.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    assert not Folder.objects.for_tenant(tenant_id).alive().exists()


@pytest.mark.django_db
def test_folder_normalization_relationship_depth_and_self_parent(identities) -> None:
    tenant_id, actor_id, _ = identities
    root = make_folder(tenant_id=tenant_id, actor_id=actor_id, name="  Café  ")
    child = make_folder(
        tenant_id=tenant_id,
        actor_id=actor_id,
        name="Child",
        parent=root,
        path=f"{root.path}/Child",
        depth=1,
    )
    assert root.name == "Café"
    assert child.parent == root
    assert list(root.children.all()) == [child]

    child.parent = child
    with pytest.raises(ValidationError):
        child.save()
    child.parent = root
    child.depth = 11
    with pytest.raises(ValidationError):
        child.save()


@pytest.mark.django_db
def test_folder_live_root_and_child_names_are_case_insensitively_unique(identities) -> None:
    tenant_id, actor_id, _ = identities
    root = make_folder(tenant_id=tenant_id, actor_id=actor_id, name="Finance")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_folder(tenant_id=tenant_id, actor_id=actor_id, name="FINANCE")

    make_folder(tenant_id=tenant_id, actor_id=actor_id, name="Reports", parent=root, path="Finance/Reports", depth=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_folder(
            tenant_id=tenant_id, actor_id=actor_id, name="reports", parent=root, path="Finance/reports", depth=1
        )

    root.is_deleted = True
    root.deleted_at = timezone.now()
    root.save()
    make_folder(tenant_id=tenant_id, actor_id=actor_id, name="finance")


@pytest.mark.django_db
def test_cross_tenant_folder_and_document_version_relationships_fail(identities) -> None:
    tenant_a, actor_id, tenant_b = identities
    foreign_folder = make_folder(tenant_id=tenant_b, actor_id=actor_id)
    with pytest.raises(ValidationError):
        Document.objects.create(
            tenant_id=tenant_a,
            created_by=actor_id,
            name="Foreign filing.pdf",
            folder=foreign_folder,
        )

    graph = make_document_graph(tenant_id=tenant_a, actor_id=actor_id)
    graph.document.current_version = DocumentVersion(
        tenant_id=tenant_b,
        document=graph.document,
        version_number=2,
        storage_key="opaque",
        original_filename="other.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        checksum_sha256="b" * 64,
        created_by=actor_id,
    )
    with pytest.raises(ValidationError):
        graph.document.save()


@pytest.mark.django_db
def test_document_tags_metadata_and_owner_are_guarded(identities) -> None:
    tenant_id, actor_id, replacement_owner = identities
    document = Document.objects.create(
        tenant_id=tenant_id,
        created_by=actor_id,
        name="  Evidence  ",
        tags=[" Café ", "Legal"],
        metadata={"case": {"number": 42}, "approved": True},
    )
    assert document.name == "Evidence"
    assert document.tags == ["Café", "Legal"]

    document.tags = ["tag", "TAG"]
    with pytest.raises(ValidationError):
        document.save()
    document.tags = []
    document.metadata = {"payload": "x" * (32 * 1024)}
    with pytest.raises(ValidationError):
        document.save()
    document.metadata = {}
    document.created_by = replacement_owner
    with pytest.raises(ValidationError):
        document.save()


@pytest.mark.django_db
def test_version_is_tenant_scoped_unique_and_append_only(identities) -> None:
    tenant_id, actor_id, _ = identities
    graph = make_document_graph(tenant_id=tenant_id, actor_id=actor_id)
    version = graph.version
    assert version.storage_backend == "django"
    assert DocumentVersion.objects.for_tenant(tenant_id).get() == version

    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentVersion.objects.create(
            tenant_id=tenant_id,
            document=graph.document,
            version_number=1,
            storage_key="another-key",
            original_filename="another.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            checksum_sha256="b" * 64,
            created_by=actor_id,
        )

    version.change_note = "rewrite"
    with pytest.raises(ImmutableVersionError):
        version.save()
    with pytest.raises(ImmutableVersionError):
        DocumentVersion.objects.filter(pk=version.pk).update(change_note="rewrite")
    with pytest.raises(ImmutableVersionError):
        version.delete()
    with pytest.raises(ImmutableVersionError):
        DocumentVersion.objects.filter(pk=version.pk).delete()


@pytest.mark.django_db
def test_restore_source_must_be_same_tenant_and_document(identities) -> None:
    tenant_id, actor_id, _ = identities
    first = make_document_graph(tenant_id=tenant_id, actor_id=actor_id, name="first.pdf")
    second = make_document_graph(tenant_id=tenant_id, actor_id=actor_id, name="second.pdf")
    with pytest.raises(ValidationError):
        DocumentVersion.objects.create(
            tenant_id=tenant_id,
            document=first.document,
            source_version=second.version,
            version_number=2,
            storage_key="opaque-restore",
            original_filename="first.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            checksum_sha256="c" * 64,
            created_by=actor_id,
        )


@pytest.mark.django_db
def test_permission_live_uniqueness_owner_exclusion_and_implication(identities) -> None:
    tenant_id, owner_id, principal_id = identities
    graph = make_document_graph(tenant_id=tenant_id, actor_id=owner_id)
    grant = DocumentPermission.objects.create(
        tenant_id=tenant_id,
        document=graph.document,
        principal_type="user",
        principal_id=principal_id,
        permission=PermissionLevel.MANAGE,
        created_by=owner_id,
    )
    assert grant.grants("read")
    assert grant.grants("write")
    assert grant.grants("delete")
    assert grant.grants("share")
    assert grant.grants("manage")

    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentPermission.objects.create(
            tenant_id=tenant_id,
            document=graph.document,
            principal_type="user",
            principal_id=principal_id,
            permission=PermissionLevel.MANAGE,
            created_by=owner_id,
        )
    with pytest.raises(ValidationError):
        DocumentPermission.objects.create(
            tenant_id=tenant_id,
            document=graph.document,
            principal_type="user",
            principal_id=owner_id,
            permission="read",
            created_by=owner_id,
        )

    grant.is_deleted = True
    grant.deleted_at = timezone.now()
    grant.save()
    assert not grant.grants("read")
    DocumentPermission.objects.create(
        tenant_id=tenant_id,
        document=graph.document,
        principal_type="user",
        principal_id=principal_id,
        permission=PermissionLevel.MANAGE,
        created_by=owner_id,
    )


@pytest.mark.django_db
def test_share_is_digest_only_version_pinned_and_bounded(identities) -> None:
    tenant_id, actor_id, _ = identities
    graph = make_document_graph(tenant_id=tenant_id, actor_id=actor_id)
    share = make_share(graph=graph, actor_id=actor_id, max_access_count=2)
    field_names = {field.name for field in DocumentShare._meta.get_fields()}
    assert "share_token" not in field_names
    assert share.version == graph.version
    assert len(share.token_digest) == 64
    assert share.is_available

    share.access_count = 2
    share.save()
    assert share.is_exhausted
    assert not share.is_available
    share.revoked_at = timezone.now()
    share.save()
    assert share.is_revoked

    with pytest.raises(ValidationError):
        make_share(
            graph=graph,
            actor_id=actor_id,
            token="different-token-never-stored",
            expires_at=timezone.now() + timedelta(days=31),
        )
    with pytest.raises(ValidationError):
        make_share(
            graph=graph,
            actor_id=actor_id,
            token="another-token-never-stored",
            max_access_count=10_001,
        )


def test_required_indexes_and_constraints_are_declared() -> None:
    assert {constraint.name for constraint in Folder._meta.constraints} >= {
        "dms_folder_root_name_ci_uq",
        "dms_folder_child_name_ci_uq",
        "dms_folder_depth_range",
        "dms_folder_not_self_parent",
    }
    assert {index.name for index in Document._meta.indexes} >= {
        "dms_doc_folder_updated_idx",
        "dms_doc_owner_alive_idx",
        "dms_doc_name_idx",
        "dms_doc_tags_gin",
        "dms_doc_search_gin",
    }
    assert {constraint.name for constraint in DocumentVersion._meta.constraints} >= {
        "dms_version_tenant_doc_no_uq",
        "dms_version_number_gte1",
        "dms_version_size_gt0",
        "dms_version_checksum_sha256",
    }
    assert {constraint.name for constraint in DocumentShare._meta.constraints} >= {
        "dms_share_max_access_range",
        "dms_share_access_not_over",
        "dms_share_digest_sha256",
    }
