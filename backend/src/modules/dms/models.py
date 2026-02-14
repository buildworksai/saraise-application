"""
Dms Models.

Defines data models for Dms module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "dms"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Folder(TenantBaseModel):
    """Folder model for organizing documents in a hierarchical structure."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent folder (null for root folder)",
    )
    path = models.CharField(
        max_length=2000,
        db_index=True,
        help_text="Full path from root (e.g., '/Documents/Projects/2024')",
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "dms"
        db_table = "dms_folders"
        indexes = [
            models.Index(fields=["tenant_id", "parent"]),
            models.Index(fields=["tenant_id", "path"]),
        ]
        unique_together = [["tenant_id", "parent", "name"]]

    def __str__(self) -> str:
        return f"{self.path}/{self.name}"

    def save(self, *args, **kwargs):
        """Generate path on save."""
        if self.parent:
            parent_path = self.parent.path if self.parent.path else ""
            parent_name = self.parent.name
            if parent_path:
                self.path = f"{parent_path}/{parent_name}"
            else:
                self.path = parent_name
        else:
            self.path = ""
        super().save(*args, **kwargs)


class Document(TenantBaseModel):
    """Document model for storing file metadata."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    folder = models.ForeignKey(
        Folder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    file_path = models.CharField(
        max_length=2000,
        help_text="Storage path relative to media root",
    )
    mime_type = models.CharField(max_length=255, help_text="MIME type of the file")
    size = models.BigIntegerField(help_text="File size in bytes")
    checksum = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of file content",
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "dms"
        db_table = "dms_documents"
        indexes = [
            models.Index(fields=["tenant_id", "folder"]),
            models.Index(fields=["tenant_id", "name"]),
            models.Index(fields=["tenant_id", "checksum"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class DocumentVersion(models.Model):
    """Document version model for tracking file versions."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.IntegerField(help_text="Version number (1, 2, 3, ...)")
    file_path = models.CharField(
        max_length=2000,
        help_text="Storage path for this version",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "dms"
        db_table = "dms_document_versions"
        indexes = [
            models.Index(fields=["document", "version_number"]),
        ]
        unique_together = [["document", "version_number"]]

    def __str__(self) -> str:
        return f"{self.document.name} v{self.version_number}"


class DocumentPermission(TenantBaseModel):
    """Document permission model for access control."""

    PERMISSION_CHOICES = [
        ("read", "Read"),
        ("write", "Write"),
        ("delete", "Delete"),
        ("share", "Share"),
    ]

    PRINCIPAL_TYPE_CHOICES = [
        ("user", "User"),
        ("role", "Role"),
        ("group", "Group"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    principal_type = models.CharField(
        max_length=20,
        choices=PRINCIPAL_TYPE_CHOICES,
        help_text="Type of principal (user, role, group)",
    )
    principal_id = models.CharField(
        max_length=36,
        db_index=True,
        help_text="ID of user, role, or group",
    )
    permission = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        help_text="Permission level",
    )

    class Meta:
        app_label = "dms"
        db_table = "dms_document_permissions"
        indexes = [
            models.Index(fields=["tenant_id", "document"]),
            models.Index(fields=["tenant_id", "principal_id"]),
        ]
        unique_together = [["document", "principal_type", "principal_id", "permission"]]

    def __str__(self) -> str:
        return f"{self.document.name} - {self.principal_type}:{self.principal_id} - {self.permission}"


class DocumentShare(TenantBaseModel):
    """Document share model for creating shareable links."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    share_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique token for share link",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Expiration date (null for no expiration)",
    )
    permissions = models.JSONField(
        default=list,
        help_text="List of permissions (read, write, etc.)",
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "dms"
        db_table = "dms_document_shares"
        indexes = [
            models.Index(fields=["tenant_id", "document"]),
            models.Index(fields=["share_token"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Share {self.share_token[:8]}... for {self.document.name}"

    @property
    def is_expired(self) -> bool:
        """Check if share link is expired."""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at
