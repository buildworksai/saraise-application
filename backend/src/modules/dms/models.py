"""Canonical, tenant-safe persistence for the document-management foundation.

Storage bytes are deliberately represented only by immutable
:class:`DocumentVersion` rows.  Mutable document metadata, ACL grants and share
lifecycle state remain separate so extensions can consume stable version IDs
without acquiring direct access to storage topology.
"""

from __future__ import annotations

import json
import unicodedata
import uuid
from datetime import timedelta
from typing import Any

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel

from .managers import DmsManager, DocumentVersionManager, ImmutableVersionError

MAX_FOLDER_DEPTH = 10
MAX_DOCUMENT_TAGS = 50
MAX_TAG_LENGTH = 64
MAX_METADATA_BYTES = 32 * 1024
MAX_SHARE_LIFETIME = timedelta(days=30)
MAX_SHARE_ACCESS_COUNT = 10_000
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def generate_uuid() -> str:
    """Retain the callable imported by deployed migrations ``0001``/``0002``."""

    return str(uuid.uuid4())


def _normalized_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError({field: "Must be a string."}, code="invalid_text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValidationError({field: "Must not be blank."}, code="blank")
    return normalized


def _relation_belongs_to_tenant(instance: TenantScopedModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None or instance.tenant_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record does not belong to this tenant."},
            code="cross_tenant_reference",
        )


class MutableDmsModel(TenantScopedModel, TimestampedModel):
    """UUID identity, ownership, audit timestamps and reversible deletion."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = DmsManager()

    class Meta:
        abstract = True


class Folder(MutableDmsModel):
    """A bounded materialized-path node in a tenant-owned folder tree."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    path = models.CharField(max_length=2000)
    depth = models.PositiveSmallIntegerField(default=0)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "dms_folders"
        constraints = [
            models.CheckConstraint(
                condition=Q(depth__gte=0, depth__lte=MAX_FOLDER_DEPTH),
                name="dms_folder_depth_range",
            ),
            models.CheckConstraint(
                condition=~Q(id=F("parent_id")),
                name="dms_folder_not_self_parent",
            ),
            models.UniqueConstraint(
                Lower("name"),
                F("tenant_id"),
                condition=Q(parent__isnull=True, is_deleted=False),
                name="dms_folder_root_name_ci_uq",
            ),
            models.UniqueConstraint(
                Lower("name"),
                F("tenant_id"),
                F("parent"),
                condition=Q(parent__isnull=False, is_deleted=False),
                name="dms_folder_child_name_ci_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "parent", "is_deleted", "sort_order", "name"],
                name="dms_folder_contents_idx",
            ),
            models.Index(fields=["tenant_id", "path"], name="dms_folder_path_idx"),
            models.Index(fields=["tenant_id", "updated_at"], name="dms_folder_updated_idx"),
        ]
        ordering = ("sort_order", "name", "id")

    def clean(self) -> None:
        super().clean()
        self.name = _normalized_text(self.name, field="name")
        self.path = unicodedata.normalize("NFC", self.path).strip("/")
        if self.parent_id == self.id:
            raise ValidationError({"parent": "A folder cannot parent itself."}, code="self_parent")
        if not 0 <= self.depth <= MAX_FOLDER_DEPTH:
            raise ValidationError(
                {"depth": f"Folder depth must be between 0 and {MAX_FOLDER_DEPTH}."},
                code="folder_depth",
            )
        _relation_belongs_to_tenant(self, "parent")
        if self.parent_id and self.parent and self.parent.is_deleted:
            raise ValidationError({"parent": "The parent folder has been deleted."}, code="deleted_parent")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.path or self.name


class Document(MutableDmsModel):
    """Mutable document metadata pointing at one immutable current version."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    folder = models.ForeignKey(
        Folder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    current_version = models.ForeignKey(
        "DocumentVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_documents",
    )
    version_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "dms_documents"
        constraints = [
            models.CheckConstraint(condition=Q(version_count__gte=0), name="dms_doc_version_count_gte0"),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "folder", "is_deleted", "updated_at"],
                name="dms_doc_folder_updated_idx",
            ),
            models.Index(
                fields=["tenant_id", "created_by", "is_deleted"],
                name="dms_doc_owner_alive_idx",
            ),
            models.Index(fields=["tenant_id", "name"], name="dms_doc_name_idx"),
            GinIndex(fields=["tags"], name="dms_doc_tags_gin"),
            GinIndex(
                SearchVector("name", "description", "metadata", config="simple"),
                name="dms_doc_search_gin",
            ),
        ]
        ordering = ("-updated_at", "name", "id")

    def clean(self) -> None:
        super().clean()
        self.name = _normalized_text(self.name, field="name")
        _relation_belongs_to_tenant(self, "folder")
        if self.folder_id and self.folder and self.folder.is_deleted:
            raise ValidationError({"folder": "The target folder has been deleted."}, code="deleted_folder")

        if not isinstance(self.tags, list):
            raise ValidationError({"tags": "Tags must be an array."}, code="invalid_tags")
        if len(self.tags) > MAX_DOCUMENT_TAGS:
            raise ValidationError({"tags": f"At most {MAX_DOCUMENT_TAGS} tags are allowed."}, code="too_many_tags")
        normalized_tags: list[str] = []
        seen: set[str] = set()
        for tag in self.tags:
            normalized = _normalized_text(tag, field="tags")
            if len(normalized) > MAX_TAG_LENGTH:
                raise ValidationError(
                    {"tags": f"Each tag must be at most {MAX_TAG_LENGTH} characters."},
                    code="tag_too_long",
                )
            key = normalized.casefold()
            if key in seen:
                raise ValidationError({"tags": "Tags must be unique."}, code="duplicate_tag")
            seen.add(key)
            normalized_tags.append(normalized)
        self.tags = normalized_tags

        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Metadata must be a JSON object."}, code="invalid_metadata")
        try:
            encoded_metadata = json.dumps(
                self.metadata,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"metadata": "Metadata must contain JSON-compatible values only."},
                code="invalid_metadata",
            ) from exc
        if len(encoded_metadata) > MAX_METADATA_BYTES:
            raise ValidationError(
                {"metadata": f"Metadata must not exceed {MAX_METADATA_BYTES} UTF-8 bytes."},
                code="metadata_too_large",
            )

        _relation_belongs_to_tenant(self, "current_version")
        if self.current_version_id and self.current_version.document_id != self.id:
            raise ValidationError(
                {"current_version": "The current version must belong to this document."},
                code="version_document_mismatch",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        if not self._state.adding:
            previous_owner = type(self)._base_manager.filter(pk=self.pk).values_list("created_by", flat=True).first()
            if previous_owner is not None and previous_owner != self.created_by:
                raise ValidationError({"created_by": "Document ownership is immutable."}, code="immutable_owner")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class DocumentVersion(TenantScopedModel):
    """Append-only storage and integrity evidence for one document revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    storage_backend = models.CharField(max_length=100, default="django", db_index=True)
    storage_key = models.CharField(max_length=2000)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(
        max_length=64,
        validators=[RegexValidator(SHA256_PATTERN, "Checksum must be a lowercase SHA-256 digest.")],
    )
    change_note = models.CharField(max_length=1000, blank=True, default="")
    source_version = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restored_versions",
    )
    created_by = models.UUIDField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DocumentVersionManager()

    class Meta:
        db_table = "dms_document_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "document", "version_number"],
                name="dms_version_tenant_doc_no_uq",
            ),
            models.CheckConstraint(condition=Q(version_number__gte=1), name="dms_version_number_gte1"),
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="dms_version_size_gt0"),
            models.CheckConstraint(
                condition=Q(checksum_sha256__regex=SHA256_PATTERN),
                name="dms_version_checksum_sha256",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "document", "-version_number"],
                name="dms_version_doc_number_idx",
            ),
            models.Index(
                fields=["tenant_id", "checksum_sha256"],
                name="dms_version_checksum_idx",
            ),
            models.Index(fields=["tenant_id", "created_at"], name="dms_version_created_idx"),
        ]
        ordering = ("-version_number", "-created_at", "id")

    def clean(self) -> None:
        super().clean()
        _relation_belongs_to_tenant(self, "document")
        _relation_belongs_to_tenant(self, "source_version")
        self.storage_backend = _normalized_text(self.storage_backend, field="storage_backend")
        self.storage_key = _normalized_text(self.storage_key, field="storage_key")
        self.original_filename = _normalized_text(self.original_filename, field="original_filename")
        self.mime_type = _normalized_text(self.mime_type, field="mime_type")
        if self.version_number < 1:
            raise ValidationError({"version_number": "Version number must be at least 1."})
        if self.size_bytes < 1:
            raise ValidationError({"size_bytes": "Stored content must not be empty."})
        if self.source_version_id and self.source_version.document_id != self.document_id:
            raise ValidationError(
                {"source_version": "A restore source must belong to the same document."},
                code="source_document_mismatch",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableVersionError(
                "Document versions are append-only and cannot be updated.",
                code="immutable_version",
            )
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableVersionError(
            "Document versions are retained and cannot be deleted.",
            code="immutable_version",
        )

    def __str__(self) -> str:
        return f"{self.document_id} v{self.version_number}"


class PrincipalType(models.TextChoices):
    USER = "user", "User"
    ROLE = "role", "Role"
    GROUP = "group", "Group"


class PermissionLevel(models.TextChoices):
    READ = "read", "Read"
    WRITE = "write", "Write"
    DELETE = "delete", "Delete"
    SHARE = "share", "Share"
    MANAGE = "manage", "Manage"


PERMISSION_IMPLICATIONS: dict[str, frozenset[str]] = {
    PermissionLevel.READ: frozenset({PermissionLevel.READ}),
    PermissionLevel.WRITE: frozenset({PermissionLevel.WRITE, PermissionLevel.READ}),
    PermissionLevel.DELETE: frozenset({PermissionLevel.DELETE, PermissionLevel.WRITE, PermissionLevel.READ}),
    PermissionLevel.SHARE: frozenset({PermissionLevel.SHARE, PermissionLevel.READ}),
    PermissionLevel.MANAGE: frozenset(PermissionLevel.values),
}


class DocumentPermission(MutableDmsModel):
    """Auditable, soft-revocable document ACL grant."""

    PRINCIPAL_TYPE_CHOICES = PrincipalType.choices
    PERMISSION_CHOICES = PermissionLevel.choices

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="permissions")
    principal_type = models.CharField(max_length=20, choices=PrincipalType.choices)
    principal_id = models.UUIDField()
    permission = models.CharField(max_length=20, choices=PermissionLevel.choices)

    class Meta:
        db_table = "dms_document_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "document", "principal_type", "principal_id", "permission"],
                condition=Q(is_deleted=False),
                name="dms_permission_live_grant_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "document", "is_deleted"],
                name="dms_perm_document_alive_idx",
            ),
            models.Index(
                fields=["tenant_id", "principal_type", "principal_id", "is_deleted"],
                name="dms_perm_principal_alive_idx",
            ),
            models.Index(
                fields=["tenant_id", "permission", "is_deleted"],
                name="dms_perm_level_alive_idx",
            ),
        ]
        ordering = ("principal_type", "principal_id", "permission", "id")

    @property
    def implied_permissions(self) -> frozenset[str]:
        return PERMISSION_IMPLICATIONS.get(self.permission, frozenset())

    def grants(self, permission: str) -> bool:
        return not self.is_deleted and permission in self.implied_permissions

    def clean(self) -> None:
        super().clean()
        _relation_belongs_to_tenant(self, "document")
        if (
            self.document_id
            and self.principal_type == PrincipalType.USER
            and self.principal_id == self.document.created_by
        ):
            raise ValidationError(
                {"principal_id": "Document owners already have implicit access and cannot receive a grant."},
                code="owner_grant",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.document_id}:{self.principal_type}:{self.principal_id}:{self.permission}"


class DocumentShare(MutableDmsModel):
    """Digest-only bearer grant pinned to one immutable document version."""

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="shares")
    version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="shares")
    token_digest = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(SHA256_PATTERN, "Token digest must be a lowercase SHA-256 digest.")],
    )
    token_prefix = models.CharField(max_length=12, db_index=True)
    expires_at = models.DateTimeField()
    max_access_count = models.PositiveIntegerField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "dms_document_shares"
        constraints = [
            models.CheckConstraint(
                condition=Q(max_access_count__isnull=True)
                | Q(max_access_count__gte=1, max_access_count__lte=MAX_SHARE_ACCESS_COUNT),
                name="dms_share_max_access_range",
            ),
            models.CheckConstraint(
                condition=Q(max_access_count__isnull=True) | Q(access_count__lte=F("max_access_count")),
                name="dms_share_access_not_over",
            ),
            models.CheckConstraint(condition=Q(access_count__gte=0), name="dms_share_access_gte0"),
            models.CheckConstraint(
                condition=Q(token_digest__regex=SHA256_PATTERN),
                name="dms_share_digest_sha256",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "document", "revoked_at", "expires_at"],
                name="dms_share_doc_validity_idx",
            ),
        ]
        ordering = ("-created_at", "id")

    def clean(self) -> None:
        super().clean()
        _relation_belongs_to_tenant(self, "document")
        _relation_belongs_to_tenant(self, "version")
        if self.version_id and self.version.document_id != self.document_id:
            raise ValidationError(
                {"version": "A share must target a version of its document."},
                code="share_version_mismatch",
            )
        if len(self.token_prefix) != 12:
            raise ValidationError({"token_prefix": "Token prefix must contain exactly 12 characters."})
        baseline = self.created_at if self.created_at else timezone.now()
        if self.expires_at <= baseline:
            raise ValidationError({"expires_at": "Share expiry must be in the future."}, code="expired_share")
        if self.expires_at > baseline + MAX_SHARE_LIFETIME:
            raise ValidationError(
                {"expires_at": "Share expiry cannot be more than 30 days after creation."},
                code="share_expiry_too_long",
            )
        if self.max_access_count is not None and not 1 <= self.max_access_count <= MAX_SHARE_ACCESS_COUNT:
            raise ValidationError(
                {"max_access_count": f"Access limit must be between 1 and {MAX_SHARE_ACCESS_COUNT}."},
                code="share_access_limit",
            )
        if self.max_access_count is not None and self.access_count > self.max_access_count:
            raise ValidationError({"access_count": "Access count exceeds this share's limit."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_exhausted(self) -> bool:
        return self.max_access_count is not None and self.access_count >= self.max_access_count

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_available(self) -> bool:
        return not (
            self.is_deleted or self.document.is_deleted or self.is_revoked or self.is_expired or self.is_exhausted
        )

    def __str__(self) -> str:
        return f"Share {self.id} for version {self.version_id}"


__all__ = [
    "Document",
    "DocumentPermission",
    "DocumentShare",
    "DocumentVersion",
    "Folder",
    "ImmutableVersionError",
    "MutableDmsModel",
    "PERMISSION_IMPLICATIONS",
    "PermissionLevel",
    "PrincipalType",
    "generate_uuid",
]
