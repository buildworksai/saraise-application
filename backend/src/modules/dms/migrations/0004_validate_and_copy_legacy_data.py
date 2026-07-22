"""Validate legacy evidence completely, then copy it into UUID shadow tables.

Legacy v1 did not retain per-version integrity metadata or permission grantor
identity.  This migration therefore aborts with a remediation message when
those values cannot be proven; it never invents owners, checksums or locators.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import timedelta
from uuid import UUID

from django.db import migrations

BATCH_SIZE = 500
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _abort(message: str) -> None:
    raise RuntimeError(f"DMS v2 migration refused legacy data: {message}")


def _uuid(value: object, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"DMS v2 migration refused legacy data: {label} is not a UUID") from exc


def _name(value: object, label: str) -> str:
    if not isinstance(value, str):
        _abort(f"{label} is not text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > 255 or "/" in normalized or "\x00" in normalized:
        _abort(f"{label} is blank or unsafe")
    return normalized


def _validate_quarantined_resources(schema_editor) -> None:
    """Validate UUID ownership even for retained, non-served generic rows."""

    quoted_table = schema_editor.quote_name("dms_resources_legacy")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, tenant_id, created_by FROM {quoted_table} ORDER BY id")
        while rows := cursor.fetchmany(BATCH_SIZE):
            for identifier, tenant_id, created_by in rows:
                resource_id = _uuid(identifier, "dms_resource.id")
                _uuid(tenant_id, f"dms resource {resource_id} tenant_id")
                _uuid(created_by, f"dms resource {resource_id} created_by")


def _validate_legacy(apps) -> None:
    Folder = apps.get_model("dms", "Folder")
    Document = apps.get_model("dms", "Document")
    Version = apps.get_model("dms", "DocumentVersion")
    Permission = apps.get_model("dms", "DocumentPermission")
    Share = apps.get_model("dms", "DocumentShare")

    sibling_names: set[tuple[UUID, str | None, str]] = set()
    for folder in Folder.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        folder_id = _uuid(folder.pk, "folder.id")
        tenant_id = _uuid(folder.tenant_id, f"folder {folder_id} tenant_id")
        _uuid(folder.created_by, f"folder {folder_id} created_by")
        normalized_name = _name(folder.name, f"folder {folder_id} name")
        parent_key = str(folder.parent_id) if folder.parent_id else None
        sibling_key = (tenant_id, parent_key, normalized_name.casefold())
        if sibling_key in sibling_names:
            _abort(f"folder {folder_id} has a duplicate case-insensitive live sibling name")
        sibling_names.add(sibling_key)

        ancestor_id = folder.parent_id
        visited = {str(folder.pk)}
        depth = 0
        while ancestor_id is not None:
            ancestor_key = str(ancestor_id)
            if ancestor_key in visited:
                _abort(f"folder {folder_id} participates in a parent cycle")
            visited.add(ancestor_key)
            try:
                ancestor = Folder.objects.get(pk=ancestor_id)
            except Folder.DoesNotExist:
                _abort(f"folder {folder_id} references a missing parent")
            if _uuid(ancestor.tenant_id, f"folder {ancestor.pk} tenant_id") != tenant_id:
                _abort(f"folder {folder_id} references a parent in another tenant")
            depth += 1
            if depth > 10:
                _abort(f"folder {folder_id} exceeds the maximum depth of 10")
            ancestor_id = ancestor.parent_id

    for document in Document.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        document_id = _uuid(document.pk, "document.id")
        tenant_id = _uuid(document.tenant_id, f"document {document_id} tenant_id")
        _uuid(document.created_by, f"document {document_id} created_by")
        _name(document.name, f"document {document_id} name")
        if document.folder_id is not None:
            try:
                folder = Folder.objects.get(pk=document.folder_id)
            except Folder.DoesNotExist:
                _abort(f"document {document_id} references a missing folder")
            if _uuid(folder.tenant_id, f"folder {folder.pk} tenant_id") != tenant_id:
                _abort(f"document {document_id} references a folder in another tenant")
        if not isinstance(document.file_path, str) or not document.file_path.strip():
            _abort(f"document {document_id} has no provable storage locator")
        if not isinstance(document.mime_type, str) or not document.mime_type.strip():
            _abort(f"document {document_id} has no provable MIME type")
        if document.size is None or int(document.size) <= 0:
            _abort(f"document {document_id} has no positive measured size")
        if not SHA256_RE.fullmatch(str(document.checksum)):
            _abort(f"document {document_id} has no valid lowercase SHA-256 checksum")

        versions = Version.objects.filter(document_id=document.pk).order_by("version_number", "pk")
        if not versions.exists():
            _abort(f"document {document_id} has no version row; remediate legacy storage evidence before retrying")
        numbers: set[int] = set()
        for version in versions.iterator(chunk_size=BATCH_SIZE):
            version_id = _uuid(version.pk, "document_version.id")
            _uuid(version.created_by, f"document version {version_id} created_by")
            number = int(version.version_number)
            if number < 1 or number in numbers:
                _abort(f"document {document_id} has invalid or duplicate version numbers")
            numbers.add(number)
            if version.document_id != document.pk:
                _abort(f"document version {version_id} has an invalid document reference")
            if version.file_path != document.file_path:
                _abort(
                    f"document version {version_id} lacks independent filename/MIME/size/checksum evidence; "
                    "restore that evidence before retrying"
                )

    # v1 permissions did not contain created_by.  Guessing the owner or an
    # administrator would falsify the audit trail, so populated rows require a
    # separately reviewed remediation export/import.
    if Permission.objects.exists():
        for permission in Permission.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
            permission_id = _uuid(permission.pk, "document_permission.id")
            _uuid(permission.tenant_id, f"permission {permission_id} tenant_id")
            _uuid(permission.principal_id, f"permission {permission_id} principal_id")
            try:
                document = Document.objects.get(pk=permission.document_id)
            except Document.DoesNotExist:
                _abort(f"permission {permission_id} references a missing document")
            if str(document.tenant_id) != str(permission.tenant_id):
                _abort(f"permission {permission_id} references a document in another tenant")
        _abort("permission grants have no grantor identity; export/remediate grants before retrying")

    for share in Share.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        share_id = _uuid(share.pk, "document_share.id")
        tenant_id = _uuid(share.tenant_id, f"share {share_id} tenant_id")
        _uuid(share.created_by, f"share {share_id} created_by")
        try:
            document = Document.objects.get(pk=share.document_id)
        except Document.DoesNotExist:
            _abort(f"share {share_id} references a missing document")
        if _uuid(document.tenant_id, f"document {document.pk} tenant_id") != tenant_id:
            _abort(f"share {share_id} references a document in another tenant")
        if not isinstance(share.share_token, str) or len(share.share_token) < 12:
            _abort(f"share {share_id} has an invalid bearer token")
        if share.expires_at is None:
            _abort(f"share {share_id} has no expiry; revoke or set a bounded expiry before retrying")
        if share.expires_at <= share.created_at:
            _abort(f"share {share_id} expires no later than its creation time")
        if share.expires_at > share.created_at + timedelta(days=30):
            _abort(f"share {share_id} exceeds the maximum 30-day lifetime")
        if not Version.objects.filter(document_id=document.pk).exists():
            _abort(f"share {share_id} cannot be pinned because its document has no version")

    # Validate every remaining legacy PK/tenant pair, including versions whose
    # tenant will be derived from their already-validated document.
    for version in Version.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        version_id = _uuid(version.pk, "document_version.id")
        try:
            document = Document.objects.get(pk=version.document_id)
        except Document.DoesNotExist:
            _abort(f"document version {version_id} references a missing document")
        _uuid(document.tenant_id, f"document version {version_id} derived tenant_id")


def copy_legacy_data(apps, schema_editor) -> None:
    _validate_quarantined_resources(schema_editor)
    _validate_legacy(apps)

    Folder = apps.get_model("dms", "Folder")
    Document = apps.get_model("dms", "Document")
    Version = apps.get_model("dms", "DocumentVersion")
    Share = apps.get_model("dms", "DocumentShare")
    FolderV2 = apps.get_model("dms", "FolderV2")
    DocumentV2 = apps.get_model("dms", "DocumentV2")
    VersionV2 = apps.get_model("dms", "DocumentVersionV2")
    ShareV2 = apps.get_model("dms", "DocumentShareV2")

    total_folders = Folder.objects.count()
    while FolderV2.objects.count() < total_folders:
        copied_this_pass = 0
        for folder in Folder.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
            identifier = _uuid(folder.pk, "folder.id")
            if FolderV2.objects.filter(pk=identifier).exists():
                continue
            parent = None
            if folder.parent_id is not None:
                parent = FolderV2.objects.filter(pk=_uuid(folder.parent_id, "folder.parent_id")).first()
                if parent is None:
                    continue
            name = _name(folder.name, f"folder {identifier} name")
            path = f"{parent.path}/{name}" if parent else name
            created = FolderV2.objects.create(
                id=identifier,
                tenant_id=_uuid(folder.tenant_id, f"folder {identifier} tenant_id"),
                created_by=_uuid(folder.created_by, f"folder {identifier} created_by"),
                name=name,
                description="",
                parent_id=parent.pk if parent else None,
                path=path,
                depth=(parent.depth + 1) if parent else 0,
                sort_order=0,
                is_deleted=False,
            )
            FolderV2.objects.filter(pk=created.pk).update(
                created_at=folder.created_at,
                updated_at=folder.updated_at,
            )
            copied_this_pass += 1
        if copied_this_pass == 0 and FolderV2.objects.count() != total_folders:
            _abort("folder topology could not be copied")

    for document in Document.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        identifier = _uuid(document.pk, "document.id")
        created = DocumentV2.objects.create(
            id=identifier,
            tenant_id=_uuid(document.tenant_id, f"document {identifier} tenant_id"),
            created_by=_uuid(document.created_by, f"document {identifier} created_by"),
            name=_name(document.name, f"document {identifier} name"),
            description="",
            folder_id=_uuid(document.folder_id, "document.folder_id") if document.folder_id else None,
            tags=[],
            metadata={},
            version_count=0,
            is_deleted=False,
        )
        DocumentV2.objects.filter(pk=created.pk).update(
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    for version in Version.objects.select_related("document").order_by("pk").iterator(chunk_size=BATCH_SIZE):
        document = version.document
        identifier = _uuid(version.pk, "document_version.id")
        created = VersionV2.objects.create(
            id=identifier,
            tenant_id=_uuid(document.tenant_id, f"version {identifier} tenant_id"),
            document_id=_uuid(document.pk, f"version {identifier} document_id"),
            version_number=version.version_number,
            storage_backend="django",
            storage_key=version.file_path,
            original_filename=_name(document.name, f"document {document.pk} name"),
            mime_type=document.mime_type.strip(),
            size_bytes=document.size,
            checksum_sha256=document.checksum,
            change_note="Migrated from the retained v1 evidence record.",
            source_version_id=None,
            created_by=_uuid(version.created_by, f"version {identifier} created_by"),
        )
        VersionV2.objects.filter(pk=created.pk).update(created_at=version.created_at)

    for document in Document.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        latest = (
            Version.objects.filter(document_id=document.pk).order_by("-version_number", "-created_at", "pk").first()
        )
        count = Version.objects.filter(document_id=document.pk).count()
        DocumentV2.objects.filter(pk=_uuid(document.pk, "document.id")).update(
            current_version_id=_uuid(latest.pk, "current version.id"),
            version_count=count,
        )

    for share in Share.objects.select_related("document").order_by("pk").iterator(chunk_size=BATCH_SIZE):
        identifier = _uuid(share.pk, "document_share.id")
        latest = (
            Version.objects.filter(document_id=share.document_id)
            .order_by("-version_number", "-created_at", "pk")
            .first()
        )
        digest = hashlib.sha256(share.share_token.encode("utf-8")).hexdigest()
        created = ShareV2.objects.create(
            id=identifier,
            tenant_id=_uuid(share.tenant_id, f"share {identifier} tenant_id"),
            document_id=_uuid(share.document_id, f"share {identifier} document_id"),
            version_id=_uuid(latest.pk, f"share {identifier} version_id"),
            token_digest=digest,
            token_prefix=share.share_token[:12],
            expires_at=share.expires_at,
            max_access_count=None,
            access_count=0,
            last_accessed_at=None,
            revoked_at=None,
            created_by=_uuid(share.created_by, f"share {identifier} created_by"),
            is_deleted=False,
        )
        ShareV2.objects.filter(pk=created.pk).update(
            created_at=share.created_at,
            updated_at=share.updated_at,
        )


def delete_copied_shadow_rows(apps, schema_editor) -> None:
    del schema_editor
    Folder = apps.get_model("dms", "Folder")
    Document = apps.get_model("dms", "Document")
    Version = apps.get_model("dms", "DocumentVersion")
    Permission = apps.get_model("dms", "DocumentPermission")
    Share = apps.get_model("dms", "DocumentShare")
    FolderV2 = apps.get_model("dms", "FolderV2")
    DocumentV2 = apps.get_model("dms", "DocumentV2")
    VersionV2 = apps.get_model("dms", "DocumentVersionV2")
    PermissionV2 = apps.get_model("dms", "DocumentPermissionV2")
    ShareV2 = apps.get_model("dms", "DocumentShareV2")

    for share in Share.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        ShareV2.objects.filter(pk=_uuid(share.pk, "document_share.id")).delete()
    for permission in Permission.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        PermissionV2.objects.filter(pk=_uuid(permission.pk, "document_permission.id")).delete()

    document_ids = [
        _uuid(value, "document.id")
        for value in Document.objects.order_by("pk").values_list("pk", flat=True).iterator(chunk_size=BATCH_SIZE)
    ]
    DocumentV2.objects.filter(pk__in=document_ids).update(current_version_id=None)
    for version in Version.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE):
        VersionV2.objects.filter(pk=_uuid(version.pk, "document_version.id")).delete()
    for identifier in document_ids:
        DocumentV2.objects.filter(pk=identifier).delete()

    legacy_folder_ids = {
        _uuid(value, "folder.id")
        for value in Folder.objects.order_by("pk").values_list("pk", flat=True).iterator(chunk_size=BATCH_SIZE)
    }
    for shadow in (
        FolderV2.objects.filter(pk__in=legacy_folder_ids).order_by("-depth", "pk").iterator(chunk_size=BATCH_SIZE)
    ):
        shadow.delete()


class Migration(migrations.Migration):
    dependencies = [("dms", "0003_create_v2_shadow_schema")]

    operations = [migrations.RunPython(copy_legacy_data, delete_copied_shadow_rows)]
