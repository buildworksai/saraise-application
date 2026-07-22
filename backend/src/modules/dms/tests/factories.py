"""Small deterministic model builders shared by DMS domain tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from src.modules.dms.models import Document, DocumentShare, DocumentVersion, Folder


@dataclass(frozen=True)
class DocumentGraph:
    document: Document
    version: DocumentVersion


def make_folder(*, tenant_id: uuid.UUID, actor_id: uuid.UUID, name: str = "Documents", **kwargs) -> Folder:
    return Folder.objects.create(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=name,
        path=kwargs.pop("path", name),
        **kwargs,
    )


def make_document_graph(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str = "Quarterly report.pdf",
    folder: Folder | None = None,
) -> DocumentGraph:
    document = Document.objects.create(
        tenant_id=tenant_id,
        created_by=actor_id,
        name=name,
        folder=folder,
    )
    version = DocumentVersion.objects.create(
        tenant_id=tenant_id,
        document=document,
        version_number=1,
        storage_backend="django",
        storage_key=f"tenants/{tenant_id}/dms/2026/07/{document.id}/{uuid.uuid4()}",
        original_filename=name,
        mime_type="application/pdf",
        size_bytes=128,
        checksum_sha256="a" * 64,
        created_by=actor_id,
    )
    Document.objects.filter(pk=document.pk).update(current_version=version, version_count=1)
    document.refresh_from_db()
    return DocumentGraph(document=document, version=version)


def make_share(*, graph: DocumentGraph, actor_id: uuid.UUID, **kwargs) -> DocumentShare:
    token = kwargs.pop("token", "clear-token-that-is-never-stored")
    import hashlib

    return DocumentShare.objects.create(
        tenant_id=graph.document.tenant_id,
        document=graph.document,
        version=graph.version,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        token_prefix=token[:12],
        expires_at=kwargs.pop("expires_at", timezone.now() + timedelta(days=1)),
        created_by=actor_id,
        **kwargs,
    )


__all__ = ["DocumentGraph", "make_document_graph", "make_folder", "make_share"]
