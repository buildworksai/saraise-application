"""Tenant-aware querysets and immutability guards for DMS persistence."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from src.core.tenancy.models import TenantQuerySet


class DmsQuerySet(TenantQuerySet):
    """Common tenant boundary plus the soft-deletion visibility contract."""

    def alive(self) -> "DmsQuerySet":
        """Return records that have not been soft deleted."""

        return self.filter(is_deleted=False)


class ImmutableVersionError(ValidationError):
    """Raised when code attempts to rewrite immutable document evidence."""


class DocumentVersionQuerySet(TenantQuerySet):
    """QuerySet that makes append-only history explicit at the ORM boundary."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableVersionError(
            "Document versions are append-only and cannot be updated.",
            code="immutable_version",
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableVersionError(
            "Document versions are retained and cannot be deleted.",
            code="immutable_version",
        )


DmsManager = DmsQuerySet.as_manager
DocumentVersionManager = DocumentVersionQuerySet.as_manager


__all__ = [
    "DmsManager",
    "DmsQuerySet",
    "DocumentVersionManager",
    "DocumentVersionQuerySet",
    "ImmutableVersionError",
]
