"""Transactional, tenant-safe DMS domain services.

This is the public extension surface for other modules.  Controllers and paid
modules must not mutate DMS ORM models directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import unicodedata
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, BinaryIO, Generic, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone

from src.core.access.entitlements import Quota, QuotaService
from src.core.observability import get_correlation_id

from .events import (
    DmsOperation,
    ExtensionOperationError,
    publish_domain_event,
    register_operation_guard,
    run_operation_guards,
    unregister_operation_guard,
)
from .models import (
    DmsConfiguration,
    DmsConfigurationAudit,
    DmsConfigurationVersion,
    DmsUploadIdempotency,
    Document,
    DocumentPermission,
    DocumentShare,
    DocumentVersion,
    Folder,
)
from .storage import (
    DocumentStoragePort,
    generate_storage_key,
    get_document_storage,
)

logger = logging.getLogger("saraise.dms")

DOCUMENT_ACTIONS = frozenset({"read", "write", "delete", "share", "manage", "move", "download"})
RESERVED_METADATA_NAMESPACE = "_extensions"

DEFAULT_DMS_CONFIGURATION: dict[str, object] = {
    "max_folder_depth": 10,
    "max_document_tags": 50,
    "max_tag_length": 64,
    "max_metadata_bytes": 32 * 1024,
    "max_share_lifetime_days": 30,
    "max_share_access_count": 10_000,
    "permission_implications": {
        "read": ["read"],
        "write": ["read", "write"],
        "delete": ["read", "write", "delete"],
        "share": ["read", "share"],
        "manage": ["read", "write", "delete", "share", "manage"],
    },
    "principal_search_min_limit": 1,
    "principal_search_max_limit": 50,
    "principal_search_default_limit": 20,
    "principal_query_min_length": 2,
    "principal_query_max_length": 100,
    "max_name_length": 255,
    "forbidden_name_characters": ["/", "\u0000"],
    "max_metadata_key_length": 255,
    "folder_deletion_policy": "empty_only",
    "download_verification_chunk_size": 64 * 1024,
    "storage_backend": "django",
    "max_document_search_length": 200,
    "document_ordering_fields": ["name", "-name", "updated_at", "-updated_at", "created_at", "-created_at"],
    "default_document_ordering": "-updated_at",
    "restore_note_template": "Restored from version {version_number}",
    "share_token_entropy_bytes": 32,
    "share_token_prefix_length": 12,
    "incoming_share_token_max_length": 512,
    "metadata_namespace_max_length": 100,
    "max_upload_bytes": 100 * 1024 * 1024,
    "storage_stream_chunk_size": 64 * 1024,
    "content_inspection_window_bytes": 8192,
    "storage_key_max_length": 2000,
    "blocked_file_signatures": [
        "4d5a",
        "7f454c46",
        "cafebabe",
        "feedface",
        "feedfacf",
        "cefaedfe",
        "cffaedfe",
        "2321",
    ],
    "permitted_mime_types": [
        "application/json",
        "application/pdf",
        "application/xml",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "text/csv",
        "text/markdown",
        "text/plain",
        "text/xml",
    ],
    "max_control_character_ratio_percent": 1,
    "min_control_characters": 1,
    "storage_backend_name_max_length": 64,
    "outbox_freshness_seconds": 300,
    "collection_search_max_length": 200,
    "tag_filter_max_tags": 10,
    "tag_filter_max_length": 64,
    "version_change_note_max_length": 1000,
    "api_read_quota": 100_000,
    "api_write_quota": 10_000,
    "storage_quota_bytes": 5_368_709_120,
    "folder_page_size": 100,
    "document_page_size": 25,
    "max_page_size": 100,
    "default_share_expiry_hours": 24,
    "default_share_access_count": 10,
    "text_preview_max_characters": 100_000,
    "upload_timeout_ms": 30_000,
    "upload_max_retries": 3,
    "circuit_breaker_failure_threshold": 5,
    "circuit_breaker_reset_ms": 30_000,
    "executable_extensions": [".bat", ".cmd", ".com", ".exe", ".msi", ".ps1", ".scr", ".sh"],
    "governance_required_operations": [],
    "feature_flags": {"sharing": True, "uploads": True, "permission_management": True},
    "rollout": {"enabled": True, "roles": [], "cohorts": []},
}

_INTEGER_BOUNDS: dict[str, tuple[int, int]] = {
    "max_folder_depth": (1, 10),
    "max_document_tags": (1, 500),
    "max_tag_length": (1, 255),
    "max_metadata_bytes": (1024, 1024 * 1024),
    "max_share_lifetime_days": (1, 365),
    "max_share_access_count": (1, 10_000),
    "principal_search_min_limit": (1, 100),
    "principal_search_max_limit": (1, 100),
    "principal_search_default_limit": (1, 100),
    "principal_query_min_length": (1, 100),
    "principal_query_max_length": (1, 1000),
    "max_name_length": (1, 255),
    "max_metadata_key_length": (1, 1024),
    "download_verification_chunk_size": (4096, 1024 * 1024),
    "max_document_search_length": (1, 2000),
    "share_token_entropy_bytes": (32, 64),
    "share_token_prefix_length": (8, 12),
    "incoming_share_token_max_length": (64, 2048),
    "metadata_namespace_max_length": (1, 255),
    "max_upload_bytes": (1, 1024 * 1024 * 1024),
    "storage_stream_chunk_size": (4096, 4 * 1024 * 1024),
    "content_inspection_window_bytes": (512, 1024 * 1024),
    "storage_key_max_length": (64, 2000),
    "max_control_character_ratio_percent": (0, 10),
    "min_control_characters": (0, 100),
    "storage_backend_name_max_length": (1, 100),
    "outbox_freshness_seconds": (1, 86400),
    "collection_search_max_length": (1, 2000),
    "tag_filter_max_tags": (1, 100),
    "tag_filter_max_length": (1, 255),
    "version_change_note_max_length": (1, 1000),
    "api_read_quota": (1, 10_000_000),
    "api_write_quota": (1, 10_000_000),
    "storage_quota_bytes": (1, 10 * 1024 * 1024 * 1024 * 1024),
    "folder_page_size": (1, 100),
    "document_page_size": (1, 100),
    "max_page_size": (1, 100),
    "default_share_expiry_hours": (1, 8760),
    "default_share_access_count": (1, 1_000_000),
    "text_preview_max_characters": (100, 1_000_000),
    "upload_timeout_ms": (1000, 300_000),
    "upload_max_retries": (0, 10),
    "circuit_breaker_failure_threshold": (1, 100),
    "circuit_breaker_reset_ms": (1000, 600_000),
}


class DmsError(RuntimeError):
    """Base class for sanitized domain failures."""


class DmsNotFound(DmsError):
    pass


class DmsPermissionDenied(DmsError):
    pass


class DmsConflict(DmsError):
    pass


class DmsDependencyUnavailable(DmsError):
    pass


class DmsIntegrityFailure(DmsError):
    pass


class DmsValidationError(DmsError):
    def __init__(self, message: str, *, detail: Mapping[str, object] | None = None) -> None:
        self.detail = dict(detail or {"non_field_errors": [message]})
        super().__init__(message)


class DmsConfigurationService:
    """Validate, version, audit and apply tenant DMS policy documents."""

    @staticmethod
    def _copy(values: Mapping[str, object]) -> dict[str, object]:
        return json.loads(json.dumps(dict(values), allow_nan=False))

    @classmethod
    def runtime_values(cls, tenant_id: UUID | None) -> dict[str, object]:
        if tenant_id is None:
            return cls._copy(DEFAULT_DMS_CONFIGURATION)
        environment = str(getattr(settings, "SARAISE_ENVIRONMENT", "default")).strip().lower()
        stored = (
            DmsConfiguration.objects.filter(tenant_id=tenant_id, environment=environment)
            .values_list("values", flat=True)
            .first()
        )
        return cls._copy(stored if stored is not None else DEFAULT_DMS_CONFIGURATION)

    @staticmethod
    def validate_environment(environment: object) -> str:
        normalized = str(environment).strip().lower()
        if not normalized or len(normalized) > 64 or not normalized.replace("-", "").replace("_", "").isalnum():
            raise DmsValidationError("Configuration environment must be a bounded slug.")
        return normalized

    @staticmethod
    def _correlation_uuid() -> UUID:
        value = get_correlation_id()
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return uuid.uuid4()

    @staticmethod
    def _synchronize_quotas(
        tenant_id: UUID,
        values: Mapping[str, object],
        configuration_version: int,
    ) -> None:
        """Project configured limits without restoring units already consumed."""

        resources = {
            "dms.api_reads": "api_read_quota",
            "dms.api_writes": "api_write_quota",
            "dms.storage_bytes": "storage_quota_bytes",
        }
        for resource, field in resources.items():
            new_limit = int(values[field])
            quota, created = Quota.objects.select_for_update().get_or_create(
                tenant_id=tenant_id,
                resource=resource,
                defaults={
                    "limit": new_limit,
                    "remaining": new_limit,
                    "metadata": {
                        "configuration_module": "dms",
                        "configuration_version": configuration_version,
                    },
                },
            )
            if created:
                continue
            consumed = max(int(quota.limit) - int(quota.remaining), 0)
            quota.limit = new_limit
            quota.remaining = max(new_limit - consumed, 0)
            quota.metadata = {
                **dict(quota.metadata),
                "configuration_module": "dms",
                "configuration_version": configuration_version,
            }
            quota.save(update_fields=("limit", "remaining", "metadata", "updated_at"))

    @classmethod
    def require_feature(cls, tenant_id: UUID, actor_id: UUID, feature: str) -> None:
        """Enforce tenant feature flags and server-owned role/group rollout targeting."""

        policy = cls.runtime_values(tenant_id)
        if policy["feature_flags"].get(feature) is not True:
            raise DmsPermissionDenied(f"{feature.replace('_', ' ').title()} is disabled by tenant policy.")
        rollout = policy["rollout"]
        if rollout.get("enabled") is not True:
            raise DmsPermissionDenied("DMS is disabled for the configured rollout.")
        required_roles = set(rollout.get("roles", ()))
        required_cohorts = set(rollout.get("cohorts", ()))
        if not required_roles and not required_cohorts:
            return
        directory = LocalIdentityDirectory()
        user = next(
            (
                candidate
                for candidate in directory._tenant_users(tenant_id).select_related("profile").prefetch_related("groups")
                if directory._actor_uuid(candidate.pk) == actor_id
            ),
            None,
        )
        if user is None:
            raise DmsPermissionDenied("The actor is not eligible for the configured rollout.")
        actor_role = getattr(user.profile, "tenant_role", None)
        actor_cohorts = set(user.groups.values_list("name", flat=True))
        if actor_role not in required_roles and not actor_cohorts.intersection(required_cohorts):
            raise DmsPermissionDenied("The actor is not eligible for the configured rollout.")

    @classmethod
    def validate_values(cls, supplied: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(supplied, Mapping):
            raise DmsValidationError("Configuration values must be an object.")
        expected = set(DEFAULT_DMS_CONFIGURATION)
        received = set(supplied)
        missing = sorted(expected - received)
        unknown = sorted(received - expected)
        if missing or unknown:
            detail: dict[str, list[str]] = {}
            if missing:
                detail["missing_fields"] = [", ".join(missing)]
            if unknown:
                detail["unknown_fields"] = [", ".join(unknown)]
            raise DmsValidationError("Configuration document fields are invalid.", detail=detail)
        values = cls._copy(supplied)
        errors: dict[str, list[str]] = {}
        for field, (minimum, maximum) in _INTEGER_BOUNDS.items():
            value = values[field]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                errors[field] = [f"Must be an integer between {minimum} and {maximum}."]

        if values["principal_search_min_limit"] > values["principal_search_default_limit"]:
            errors["principal_search_default_limit"] = ["Must not be below principal_search_min_limit."]
        if values["principal_search_default_limit"] > values["principal_search_max_limit"]:
            errors["principal_search_default_limit"] = ["Must not exceed principal_search_max_limit."]
        if values["principal_query_min_length"] > values["principal_query_max_length"]:
            errors["principal_query_max_length"] = ["Must not be below principal_query_min_length."]
        if values["default_share_access_count"] > values["max_share_access_count"]:
            errors["default_share_access_count"] = ["Must not exceed max_share_access_count."]
        if (
            values["folder_page_size"] > values["max_page_size"]
            or values["document_page_size"] > values["max_page_size"]
        ):
            errors["max_page_size"] = ["Must be at least both configured page sizes."]

        allowed_permissions = {"read", "write", "delete", "share", "manage"}
        implications = values["permission_implications"]
        if not isinstance(implications, dict) or set(implications) != allowed_permissions:
            errors["permission_implications"] = ["Must define exactly the supported permission levels."]
        else:
            for permission, implied in implications.items():
                if (
                    not isinstance(implied, list)
                    or permission not in implied
                    or not set(implied).issubset(allowed_permissions)
                    or "read" not in implied
                ):
                    errors["permission_implications"] = [
                        "Every level must imply itself and read, using only supported levels."
                    ]
                    break

        list_fields = {
            "forbidden_name_characters",
            "document_ordering_fields",
            "blocked_file_signatures",
            "permitted_mime_types",
            "executable_extensions",
            "governance_required_operations",
        }
        for field in list_fields:
            value = values[field]
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                if field == "governance_required_operations" and value == []:
                    continue
                errors[field] = ["Must be a list of non-empty strings."]

        safe_ordering = {"name", "-name", "updated_at", "-updated_at", "created_at", "-created_at"}
        configured_ordering = values["document_ordering_fields"]
        if isinstance(configured_ordering, list) and (
            not set(configured_ordering).issubset(safe_ordering)
            or values["default_document_ordering"] not in configured_ordering
        ):
            errors["document_ordering_fields"] = ["Contains unsupported fields or omits the default ordering."]
        signatures = values["blocked_file_signatures"]
        if isinstance(signatures, list):
            try:
                decoded_signatures = [bytes.fromhex(signature) for signature in signatures]
            except ValueError:
                errors["blocked_file_signatures"] = ["Every signature must be valid hexadecimal."]
            else:
                if any(not signature or len(signature) > 64 for signature in decoded_signatures):
                    errors["blocked_file_signatures"] = ["Every signature must encode between 1 and 64 bytes."]
        mime_types = values["permitted_mime_types"]
        if isinstance(mime_types, list) and any(
            mime_type.count("/") != 1 or any(character.isspace() for character in mime_type) for mime_type in mime_types
        ):
            errors["permitted_mime_types"] = ["Every entry must be a concrete MIME type."]
        extensions = values["executable_extensions"]
        if isinstance(extensions, list) and any(
            not extension.startswith(".") or extension != extension.lower() or "/" in extension or "\\" in extension
            for extension in extensions
        ):
            errors["executable_extensions"] = [
                "Every executable extension must be lowercase, start with a dot, and contain no path separators."
            ]
        if values["folder_deletion_policy"] not in {"empty_only", "recursive_soft_delete"}:
            errors["folder_deletion_policy"] = ["Must be empty_only or recursive_soft_delete."]
        if values["storage_backend"] not in {"django"}:
            errors["storage_backend"] = ["The configured storage adapter is not installed."]
        if (
            not isinstance(values["restore_note_template"], str)
            or "{version_number}" not in values["restore_note_template"]
        ):
            errors["restore_note_template"] = ["Must contain {version_number}."]

        operations = {"upload", "download", "delete", "move", "restore", "share"}
        required_operations = values["governance_required_operations"]
        if isinstance(required_operations, list) and not set(required_operations).issubset(operations):
            errors["governance_required_operations"] = ["Contains an unsupported operation."]
        feature_flags = values["feature_flags"]
        supported_features = {"uploads", "sharing", "permission_management"}
        if (
            not isinstance(feature_flags, dict)
            or set(feature_flags) != supported_features
            or not all(isinstance(enabled, bool) for enabled in feature_flags.values())
        ):
            errors["feature_flags"] = ["Must define uploads, sharing and permission_management as booleans."]
        rollout = values["rollout"]
        if (
            not isinstance(rollout, dict)
            or set(rollout) != {"enabled", "roles", "cohorts"}
            or not isinstance(rollout.get("enabled"), bool)
            or not isinstance(rollout.get("roles"), list)
            or not isinstance(rollout.get("cohorts"), list)
            or not all(isinstance(role, str) and role for role in rollout.get("roles", []))
            or not all(isinstance(cohort, str) and cohort for cohort in rollout.get("cohorts", []))
        ):
            errors["rollout"] = ["Must contain enabled, roles and cohorts."]
        elif (
            not set(rollout["roles"]).issubset({"tenant_admin", "tenant_user"})
            or any(len(cohort) > 100 for cohort in rollout["cohorts"])
            or len(set(rollout["roles"])) != len(rollout["roles"])
            or len(set(rollout["cohorts"])) != len(rollout["cohorts"])
        ):
            errors["rollout"] = [
                "Roles must use the tenant role allow-list; cohorts must be unique group names up to 100 characters."
            ]
        if errors:
            raise DmsValidationError("Configuration validation failed.", detail=errors)
        return values

    @classmethod
    def current(cls, tenant_id: UUID, actor_id: UUID, environment: str = "default") -> DmsConfiguration:
        environment = cls.validate_environment(environment)
        with transaction.atomic():
            configuration = (
                DmsConfiguration.objects.select_for_update()
                .filter(tenant_id=tenant_id, environment=environment)
                .first()
            )
            if configuration is None:
                values = cls.validate_values(DEFAULT_DMS_CONFIGURATION)
                configuration = DmsConfiguration.objects.create(
                    tenant_id=tenant_id,
                    environment=environment,
                    values=values,
                    version=1,
                    updated_by=actor_id,
                )
                correlation_id = cls._correlation_uuid()
                DmsConfigurationVersion.objects.create(
                    tenant_id=tenant_id,
                    configuration=configuration,
                    version=1,
                    environment=environment,
                    values=values,
                    created_by=actor_id,
                    correlation_id=correlation_id,
                )
                DmsConfigurationAudit.objects.create(
                    tenant_id=tenant_id,
                    configuration=configuration,
                    action="created",
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    from_version=None,
                    to_version=1,
                    before={},
                    after=values,
                )
            return configuration

    @classmethod
    def preview(
        cls, tenant_id: UUID, actor_id: UUID, values: Mapping[str, object], environment: str = "default"
    ) -> dict[str, object]:
        environment = cls.validate_environment(environment)
        current = cls.current(tenant_id, actor_id, environment)
        normalized = cls.validate_values(values)
        changes = [
            {"field": field, "before": current.values.get(field), "after": normalized[field]}
            for field in sorted(normalized)
            if current.values.get(field) != normalized[field]
        ]
        return {
            "valid": True,
            "normalized_values": normalized,
            "changes": changes,
            "restart_required": False,
        }

    @classmethod
    def update(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        values: Mapping[str, object],
        environment: str = "default",
        *,
        action: str = "updated",
    ) -> DmsConfiguration:
        normalized = cls.validate_values(values)
        environment = cls.validate_environment(environment)
        with transaction.atomic():
            current = cls.current(tenant_id, actor_id, environment)
            configuration = DmsConfiguration.objects.select_for_update().get(
                tenant_id=tenant_id,
                environment=environment,
            )
            before = cls._copy(configuration.values)
            from_version = configuration.version
            if before == normalized:
                cls._synchronize_quotas(tenant_id, normalized, configuration.version)
                return configuration
            configuration.values = normalized
            configuration.version += 1
            configuration.updated_by = actor_id
            configuration.save(update_fields=("values", "version", "updated_by", "updated_at"))
            correlation_id = cls._correlation_uuid()
            DmsConfigurationVersion.objects.create(
                tenant_id=tenant_id,
                configuration=configuration,
                version=configuration.version,
                environment=environment,
                values=normalized,
                created_by=actor_id,
                correlation_id=correlation_id,
            )
            DmsConfigurationAudit.objects.create(
                tenant_id=tenant_id,
                configuration=configuration,
                action=action,
                actor_id=actor_id,
                correlation_id=correlation_id,
                from_version=from_version,
                to_version=configuration.version,
                before=before,
                after=normalized,
            )
            cls._synchronize_quotas(tenant_id, normalized, configuration.version)
            return configuration

    @classmethod
    def rollback(cls, tenant_id: UUID, actor_id: UUID, version: int, environment: str = "default") -> DmsConfiguration:
        current = cls.current(tenant_id, actor_id, environment)
        prior = (
            DmsConfigurationVersion.objects.filter(
                tenant_id=tenant_id,
                configuration=current,
                version=version,
            )
            .values_list("values", flat=True)
            .first()
        )
        if prior is None:
            raise DmsNotFound("Configuration version was not found.")
        return cls.update(tenant_id, actor_id, prior, environment, action="rolled_back")

    @classmethod
    def import_document(cls, tenant_id: UUID, actor_id: UUID, document: Mapping[str, object]) -> DmsConfiguration:
        required_fields = {"schema_version", "module", "environment", "version", "values"}
        if (
            not isinstance(document, Mapping)
            or set(document) != required_fields
            or document.get("schema_version") != 1
            or document.get("module") != "dms"
            or isinstance(document.get("version"), bool)
            or not isinstance(document.get("version"), int)
            or int(document["version"]) < 1
        ):
            raise DmsValidationError("Unsupported configuration document schema.")
        return cls.update(
            tenant_id,
            actor_id,
            document.get("values", {}),
            str(document.get("environment", "default")),
            action="imported",
        )

    @classmethod
    def export_document(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        environment: str = "default",
    ) -> dict[str, object]:
        configuration = cls.current(tenant_id, actor_id, environment)
        return {
            "schema_version": 1,
            "module": "dms",
            "environment": configuration.environment,
            "version": configuration.version,
            "values": cls._copy(configuration.values),
        }

    @classmethod
    def history(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        environment: str = "default",
    ) -> QuerySet[DmsConfigurationVersion]:
        configuration = cls.current(tenant_id, actor_id, environment)
        return DmsConfigurationVersion.objects.filter(
            tenant_id=tenant_id,
            configuration=configuration,
        ).order_by("-version")

    @classmethod
    def audit(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        environment: str = "default",
    ) -> QuerySet[DmsConfigurationAudit]:
        configuration = cls.current(tenant_id, actor_id, environment)
        return DmsConfigurationAudit.objects.filter(
            tenant_id=tenant_id,
            configuration=configuration,
        ).order_by("-created_at")


@dataclass(frozen=True, slots=True)
class PrincipalSummary:
    id: UUID
    type: str
    display_name: str
    secondary_text: str = ""


@runtime_checkable
class IdentityDirectoryPort(Protocol):
    def validate_principal(self, tenant_id: UUID, principal_type: str, principal_id: UUID) -> bool: ...

    def principals_for_actor(self, tenant_id: UUID, actor_id: UUID) -> set[tuple[str, UUID]]: ...

    def search(
        self, tenant_id: UUID, query: str, principal_type: str | None, limit: int
    ) -> Sequence[PrincipalSummary]: ...


class LocalIdentityDirectory:
    """Tenant-bounded adapter over the open-source user and RBAC models."""

    @staticmethod
    def _actor_uuid(user_id: object) -> UUID:
        try:
            return UUID(str(user_id))
        except (TypeError, ValueError, AttributeError):
            return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user_id}")

    def _tenant_users(self, tenant_id: UUID) -> QuerySet[Any]:
        user_model = get_user_model()
        return user_model.objects.filter(profile__tenant_id=tenant_id, is_active=True)

    def validate_principal(self, tenant_id: UUID, principal_type: str, principal_id: UUID) -> bool:
        if principal_type == "user":
            return any(
                self._actor_uuid(value) == principal_id
                for value in self._tenant_users(tenant_id).values_list("id", flat=True)
            )
        if principal_type == "role":
            try:
                from src.modules.security_access_control.models import Role
            except ImportError:
                return False
            return Role.objects.for_tenant(tenant_id).filter(id=principal_id, is_deleted=False, is_active=True).exists()
        # The open-source identity foundation has no tenant-owned group model.
        return False

    def principals_for_actor(self, tenant_id: UUID, actor_id: UUID) -> set[tuple[str, UUID]]:
        principals: set[tuple[str, UUID]] = {("user", actor_id)}
        try:
            from src.modules.security_access_control.models import UserRole
        except ImportError:
            return principals
        now = timezone.now()
        for assignment in (
            UserRole.objects.for_tenant(tenant_id)
            .filter(
                revoked_at__isnull=True,
                valid_from__lte=now,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
            .select_related("role")
        ):
            if self._actor_uuid(assignment.user_id) == actor_id:
                principals.add(("role", assignment.role_id))
        return principals

    def search(
        self,
        tenant_id: UUID,
        query: str,
        principal_type: str | None,
        limit: int,
    ) -> Sequence[PrincipalSummary]:
        policy = DmsConfigurationService.runtime_values(tenant_id)
        if limit < policy["principal_search_min_limit"] or limit > policy["principal_search_max_limit"]:
            raise DmsValidationError("Search limit violates tenant policy.")
        normalized = query.strip()
        if (
            len(normalized) < policy["principal_query_min_length"]
            or len(normalized) > policy["principal_query_max_length"]
        ):
            raise DmsValidationError("Principal search length violates tenant policy.")
        results: list[PrincipalSummary] = []
        if principal_type in (None, "user"):
            users = self._tenant_users(tenant_id).filter(
                Q(username__icontains=normalized)
                | Q(first_name__icontains=normalized)
                | Q(last_name__icontains=normalized)
                | Q(email__icontains=normalized)
            )[:limit]
            for user in users:
                label = (user.get_full_name() or user.get_username()).strip()
                results.append(PrincipalSummary(self._actor_uuid(user.pk), "user", label, user.email or ""))
        if principal_type in (None, "role") and len(results) < limit:
            try:
                from src.modules.security_access_control.models import Role
            except ImportError:
                pass
            else:
                roles = (
                    Role.objects.for_tenant(tenant_id)
                    .filter(
                        is_deleted=False,
                        is_active=True,
                    )
                    .filter(Q(name__icontains=normalized) | Q(code__icontains=normalized))[: limit - len(results)]
                )
                results.extend(PrincipalSummary(role.id, "role", role.name, role.code) for role in roles)
        return results


_identity_lock = RLock()
_identity_directory: IdentityDirectoryPort = LocalIdentityDirectory()


def configure_identity_directory(directory: IdentityDirectoryPort) -> None:
    if not isinstance(directory, IdentityDirectoryPort):
        raise TypeError("identity directory does not satisfy IdentityDirectoryPort")
    global _identity_directory
    with _identity_lock:
        _identity_directory = directory


def get_identity_directory() -> IdentityDirectoryPort:
    with _identity_lock:
        return _identity_directory


def _authorize_extensions(tenant_id: UUID, operation: str, document_id: UUID, version_id: UUID | None = None) -> None:
    try:
        run_operation_guards(tenant_id, DmsOperation(operation), document_id, version_id)
    except ExtensionOperationError as exc:
        if exc.code in {"guard_unavailable", "invalid_guard_decision"}:
            raise DmsDependencyUnavailable("A document governance dependency is unavailable.") from exc
        raise DmsPermissionDenied("A document governance policy denied this operation.") from exc


def _normalize_name(value: str, field: str = "name", *, tenant_id: UUID | None = None) -> str:
    policy = DmsConfigurationService.runtime_values(tenant_id)
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise DmsValidationError(
            f"{field.replace('_', ' ').title()} cannot be blank.", detail={field: ["Cannot be blank."]}
        )
    if len(normalized) > policy["max_name_length"] or any(
        forbidden in normalized for forbidden in policy["forbidden_name_characters"]
    ):
        raise DmsValidationError(
            "Name is invalid.", detail={field: ["Name violates the configured length or character policy."]}
        )
    return normalized


def _normalize_tags(tags: Sequence[object] | None, *, tenant_id: UUID | None = None) -> list[str]:
    policy = DmsConfigurationService.runtime_values(tenant_id)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags or ():
        if not isinstance(raw, str):
            raise DmsValidationError("Tags must be strings.", detail={"tags": ["Every tag must be text."]})
        value = unicodedata.normalize("NFKC", raw).strip().casefold()
        if not value or len(value) > policy["max_tag_length"]:
            raise DmsValidationError("Tag is invalid.", detail={"tags": ["Tag violates the configured limit."]})
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    if len(normalized) > policy["max_document_tags"]:
        raise DmsValidationError("Too many tags.", detail={"tags": ["Configured tag count limit exceeded."]})
    return normalized


def _validate_json_primitives(
    value: object,
    path: str = "metadata",
    *,
    maximum_key_length: int = 255,
) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise DmsValidationError("Metadata contains a non-finite number.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_primitives(item, f"{path}[{index}]", maximum_key_length=maximum_key_length)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > maximum_key_length:
                raise DmsValidationError("Metadata keys must be bounded strings.")
            _validate_json_primitives(item, f"{path}.{key}", maximum_key_length=maximum_key_length)
        return
    raise DmsValidationError(f"{path} contains an unsupported JSON value.")


def _normalize_metadata(
    metadata: object | None,
    *,
    existing_extensions: object | None = None,
    tenant_id: UUID | None = None,
) -> dict[str, object]:
    policy = DmsConfigurationService.runtime_values(tenant_id)
    if metadata is None:
        value: dict[str, object] = {}
    elif isinstance(metadata, dict):
        value = dict(metadata)
    else:
        raise DmsValidationError("Metadata must be a JSON object.", detail={"metadata": ["Must be an object."]})
    if RESERVED_METADATA_NAMESPACE in value:
        raise DmsValidationError(
            "Extension metadata is read-only.",
            detail={"metadata": ["The reserved extension namespace cannot be changed by this endpoint."]},
        )
    if existing_extensions:
        value[RESERVED_METADATA_NAMESPACE] = existing_extensions
    _validate_json_primitives(value, maximum_key_length=policy["max_metadata_key_length"])
    serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(serialized) > policy["max_metadata_bytes"]:
        raise DmsValidationError("Metadata is too large.", detail={"metadata": ["Configured metadata limit exceeded."]})
    return value


def _folder_path(parent: Folder | None, name: str) -> str:
    return f"{parent.path}/{name}" if parent else f"/{name}"


def _log(event: str, outcome: str, started: float, **fields: object) -> None:
    logger.info(
        "DMS domain operation",
        extra={
            "event": event,
            "outcome": outcome,
            "correlation_id": get_correlation_id(),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            **fields,
        },
    )


def _emit(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: UUID | None,
    **payload: object,
) -> object:
    return publish_domain_event(
        tenant_id,
        event_type,
        aggregate_type,
        aggregate_id,
        actor_id=actor_id,
        payload=payload,
    )


_ModelT = TypeVar("_ModelT")


class LazyQuerySequence(Sequence[_ModelT], Generic[_ModelT]):
    """Sequence-compatible QuerySet adapter that never eagerly evaluates on construction."""

    def __init__(self, queryset: QuerySet[_ModelT]) -> None:
        self.queryset = queryset

    def __getitem__(self, index: int | slice) -> _ModelT | Sequence[_ModelT]:
        return self.queryset[index]

    def __len__(self) -> int:
        return self.queryset.count()

    def __iter__(self) -> Iterator[_ModelT]:
        return iter(self.queryset)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyQuerySequence):
            other = list(other)
        if isinstance(other, Sequence):
            return list(self) == list(other)
        return False


@dataclass(slots=True)
class FolderContents:
    folder: Folder | None
    breadcrumbs: list[Folder]
    folders: Sequence[Folder]
    documents: Sequence[Document]
    allowed_actions: frozenset[str] = frozenset()


class FolderService:
    @staticmethod
    def project_allowed_actions(actor_id: UUID, folder: Folder | None) -> frozenset[str]:
        if folder is None:
            return frozenset({"read", "create"})
        if folder.created_by == actor_id:
            return frozenset({"read", "create", "update", "move", "delete"})
        return frozenset({"read"})

    def attach_allowed_actions(self, actor_id: UUID, folders: Sequence[Folder]) -> Sequence[Folder]:
        for folder in folders:
            folder.allowed_actions = self.project_allowed_actions(actor_id, folder)
        return folders

    def create_folder(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        name: str,
        description: str = "",
        parent_id: UUID | None = None,
    ) -> Folder:
        policy = DmsConfigurationService.runtime_values(tenant_id)
        normalized = _normalize_name(name, tenant_id=tenant_id)
        with transaction.atomic():
            parent = self._parent(tenant_id, parent_id, lock=True)
            depth = parent.depth + 1 if parent else 0
            if depth > policy["max_folder_depth"]:
                raise DmsValidationError(
                    "Folder depth exceeds tenant policy.", detail={"parent_id": ["Depth limit exceeded."]}
                )
            if Folder.objects.for_tenant(tenant_id).alive().filter(parent=parent, name__iexact=normalized).exists():
                raise DmsConflict("A folder with this name already exists here.")
            folder = Folder(
                tenant_id=tenant_id,
                name=normalized,
                description=description.strip(),
                parent=parent,
                path=_folder_path(parent, normalized),
                depth=depth,
                created_by=actor_id,
            )
            folder.full_clean()
            folder.save(force_insert=True)
            _emit(
                tenant_id, "dms.folder.created", "folder", folder.id, actor_id, parent_id=parent.id if parent else None
            )
            return folder

    def _parent(self, tenant_id: UUID, parent_id: UUID | None, *, lock: bool = False) -> Folder | None:
        if parent_id is None:
            return None
        queryset = Folder.objects.for_tenant(tenant_id).alive()
        if lock:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(id=parent_id)
        except Folder.DoesNotExist as exc:
            raise DmsNotFound("Folder was not found.") from exc

    def get_folder(self, tenant_id: UUID, actor_id: UUID, folder_id: UUID) -> Folder:
        del actor_id
        try:
            return Folder.objects.for_tenant(tenant_id).alive().get(id=folder_id)
        except Folder.DoesNotExist as exc:
            raise DmsNotFound("Folder was not found.") from exc

    def list_folders(self, tenant_id: UUID, actor_id: UUID) -> QuerySet[Folder]:
        del actor_id
        return (
            Folder.objects.for_tenant(tenant_id)
            .alive()
            .annotate(
                children_count=Count("children", filter=Q(children__is_deleted=False), distinct=True),
                documents_count=Count("documents", filter=Q(documents__is_deleted=False), distinct=True),
            )
        )

    def list_contents(self, tenant_id: UUID, actor_id: UUID, *, folder_id: UUID | None = None) -> FolderContents:
        folder = self.get_folder(tenant_id, actor_id, folder_id) if folder_id else None
        folders = (
            self.list_folders(tenant_id, actor_id)
            .filter(parent=folder)
            .order_by(
                "sort_order",
                "name",
                "id",
            )
        )
        documents = DocumentService().list_documents(
            tenant_id,
            actor_id,
            filters={"folder_id": folder_id},
            search="",
            ordering="-updated_at",
        )
        breadcrumbs: list[Folder] = []
        cursor = folder
        while cursor is not None:
            breadcrumbs.append(cursor)
            cursor = cursor.parent
        breadcrumbs.reverse()
        self.attach_allowed_actions(actor_id, breadcrumbs)
        if folder is not None:
            folder.allowed_actions = self.project_allowed_actions(actor_id, folder)
        return FolderContents(
            folder,
            breadcrumbs,
            LazyQuerySequence(folders),
            LazyQuerySequence(documents),
            self.project_allowed_actions(actor_id, folder),
        )

    def update_folder(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        folder_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> Folder:
        with transaction.atomic():
            try:
                folder = Folder.objects.for_tenant(tenant_id).alive().select_for_update().get(id=folder_id)
            except Folder.DoesNotExist as exc:
                raise DmsNotFound("Folder was not found.") from exc
            old_path = folder.path
            if name is not None:
                normalized = _normalize_name(name, tenant_id=tenant_id)
                if (
                    Folder.objects.for_tenant(tenant_id)
                    .alive()
                    .filter(parent=folder.parent, name__iexact=normalized)
                    .exclude(id=folder.id)
                    .exists()
                ):
                    raise DmsConflict("A folder with this name already exists here.")
                folder.name = normalized
                folder.path = _folder_path(folder.parent, normalized)
            if description is not None:
                folder.description = description.strip()
            if sort_order is not None:
                folder.sort_order = sort_order
            folder.full_clean()
            folder.save(update_fields=("name", "description", "sort_order", "path", "updated_at"))
            if folder.path != old_path:
                self._rewrite_descendants(tenant_id, old_path, folder.path, 0)
            return folder

    def _rewrite_descendants(self, tenant_id: UUID, old_prefix: str, new_prefix: str, depth_delta: int) -> None:
        descendants = list(
            Folder.objects.for_tenant(tenant_id)
            .alive()
            .select_for_update()
            .filter(path__startswith=f"{old_prefix}/")
            .order_by("depth")
        )
        for descendant in descendants:
            descendant.path = f"{new_prefix}{descendant.path[len(old_prefix):]}"
            descendant.depth += depth_delta
            maximum_depth = DmsConfigurationService.runtime_values(tenant_id)["max_folder_depth"]
            if descendant.depth > maximum_depth:
                raise DmsValidationError("Folder move would exceed the maximum depth.")
        if descendants:
            Folder.objects.bulk_update(descendants, ("path", "depth", "updated_at"))

    def move_folder(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        folder_id: UUID,
        *,
        parent_id: UUID | None,
    ) -> Folder:
        with transaction.atomic():
            try:
                folder = Folder.objects.for_tenant(tenant_id).alive().select_for_update().get(id=folder_id)
            except Folder.DoesNotExist as exc:
                raise DmsNotFound("Folder was not found.") from exc
            parent = self._parent(tenant_id, parent_id, lock=True)
            if parent is not None and (parent.id == folder.id or parent.path.startswith(f"{folder.path}/")):
                raise DmsValidationError("A folder cannot be moved beneath itself or a descendant.")
            if (
                Folder.objects.for_tenant(tenant_id)
                .alive()
                .filter(parent=parent, name__iexact=folder.name)
                .exclude(id=folder.id)
                .exists()
            ):
                raise DmsConflict("A folder with this name already exists at the destination.")
            new_depth = parent.depth + 1 if parent else 0
            deepest = (
                Folder.objects.for_tenant(tenant_id)
                .alive()
                .filter(path__startswith=f"{folder.path}/")
                .order_by("-depth")
                .values_list("depth", flat=True)
                .first()
            )
            depth_delta = new_depth - folder.depth
            maximum_depth = DmsConfigurationService.runtime_values(tenant_id)["max_folder_depth"]
            if (deepest if deepest is not None else folder.depth) + depth_delta > maximum_depth:
                raise DmsValidationError("Folder move would exceed the maximum depth.")
            old_path = folder.path
            folder.parent = parent
            folder.depth = new_depth
            folder.path = _folder_path(parent, folder.name)
            folder.save(update_fields=("parent", "depth", "path", "updated_at"))
            self._rewrite_descendants(tenant_id, old_path, folder.path, depth_delta)
            _emit(tenant_id, "dms.folder.moved", "folder", folder.id, actor_id, parent_id=parent.id if parent else None)
            return folder

    def delete_folder(self, tenant_id: UUID, actor_id: UUID, folder_id: UUID) -> None:
        with transaction.atomic():
            try:
                folder = Folder.objects.for_tenant(tenant_id).alive().select_for_update().get(id=folder_id)
            except Folder.DoesNotExist as exc:
                raise DmsNotFound("Folder was not found.") from exc
            has_contents = folder.children.alive().exists() or folder.documents.alive().exists()
            policy = DmsConfigurationService.runtime_values(tenant_id)["folder_deletion_policy"]
            if has_contents and policy == "empty_only":
                raise DmsConflict("Folder must be empty before it can be deleted.")
            if has_contents:
                now = timezone.now()
                Folder.objects.for_tenant(tenant_id).alive().filter(path__startswith=f"{folder.path}/").update(
                    is_deleted=True,
                    deleted_at=now,
                )
                Document.objects.for_tenant(tenant_id).alive().filter(
                    Q(folder=folder) | Q(folder__path__startswith=f"{folder.path}/")
                ).update(is_deleted=True, deleted_at=now)
            folder.is_deleted = True
            folder.deleted_at = timezone.now()
            folder.save(update_fields=("is_deleted", "deleted_at", "updated_at"))
            _emit(tenant_id, "dms.folder.deleted", "folder", folder.id, actor_id)


class PermissionService:
    def __init__(self, identity_directory: IdentityDirectoryPort | None = None) -> None:
        self.identity = identity_directory or get_identity_directory()
        self._principal_cache: dict[tuple[UUID, UUID], set[tuple[str, UUID]]] = {}

    def _principals(self, tenant_id: UUID, actor_id: UUID) -> set[tuple[str, UUID]]:
        cache_key = (tenant_id, actor_id)
        if cache_key in self._principal_cache:
            return self._principal_cache[cache_key]
        try:
            principals = self.identity.principals_for_actor(tenant_id, actor_id)
        except Exception as exc:
            raise DmsDependencyUnavailable("Identity state is unavailable.") from exc
        self._principal_cache[cache_key] = principals
        return principals

    def acl_query(self, tenant_id: UUID, actor_id: UUID, permission: str) -> Q:
        principals = self._principals(tenant_id, actor_id)
        implications = DmsConfigurationService.runtime_values(tenant_id)["permission_implications"]
        accepted = {grant for grant, implied in implications.items() if permission in implied}
        principal_q = Q(pk__in=[])
        for principal_type, principal_id in principals:
            principal_q |= Q(
                permissions__tenant_id=tenant_id,
                permissions__is_deleted=False,
                permissions__principal_type=principal_type,
                permissions__principal_id=principal_id,
                permissions__permission__in=accepted,
            )
        return Q(created_by=actor_id) | principal_q

    def has_document_access(self, tenant_id: UUID, actor: object, document: Document, permission: str) -> bool:
        implications = DmsConfigurationService.runtime_values(tenant_id)["permission_implications"]
        if document.tenant_id != tenant_id or document.is_deleted or permission not in implications:
            return False
        actor_id = actor if isinstance(actor, UUID) else getattr(actor, "id", None)
        try:
            normalized_actor = actor_id if isinstance(actor_id, UUID) else UUID(str(actor_id))
        except (TypeError, ValueError, AttributeError):
            return False
        if document.created_by == normalized_actor:
            return True
        prefetched = getattr(document, "_active_permissions", None)
        if prefetched is not None:
            principals = self._principals(tenant_id, normalized_actor)
            return any(
                (grant.principal_type, grant.principal_id) in principals
                and permission in implications.get(grant.permission, ())
                for grant in prefetched
            )
        return (
            Document.objects.for_tenant(tenant_id)
            .alive()
            .filter(id=document.id)
            .filter(self.acl_query(tenant_id, normalized_actor, permission))
            .exists()
        )

    def require(self, tenant_id: UUID, actor_id: UUID, document: Document, permission: str) -> None:
        if not self.has_document_access(tenant_id, actor_id, document, permission):
            raise DmsPermissionDenied("Document access is denied.")

    def allowed_actions(self, tenant_id: UUID, actor_id: UUID, document: Document) -> frozenset[str]:
        allowed = {
            capability
            for capability in DmsConfigurationService.runtime_values(tenant_id)["permission_implications"]
            if self.has_document_access(tenant_id, actor_id, document, capability)
        }
        if "read" in allowed:
            allowed.add("download")
        if "write" in allowed:
            allowed.add("move")
        return frozenset(allowed)

    def list_permissions(self, tenant_id: UUID, actor_id: UUID, document_id: UUID) -> QuerySet[DocumentPermission]:
        document = DocumentService(permission_service=self).get_document(
            tenant_id, actor_id, document_id, permission="manage"
        )
        return (
            DocumentPermission.objects.for_tenant(tenant_id)
            .alive()
            .filter(document=document)
            .order_by("principal_type", "principal_id", "permission")
        )

    def get_permission(self, tenant_id: UUID, actor_id: UUID, permission_id: UUID) -> DocumentPermission:
        try:
            grant = (
                DocumentPermission.objects.for_tenant(tenant_id)
                .alive()
                .select_related("document")
                .get(id=permission_id)
            )
        except DocumentPermission.DoesNotExist as exc:
            raise DmsNotFound("Permission grant was not found.") from exc
        self.require(tenant_id, actor_id, grant.document, "manage")
        return grant

    def grant_permission(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        principal_type: str,
        principal_id: UUID,
        permission: str,
    ) -> DocumentPermission:
        DmsConfigurationService.require_feature(tenant_id, actor_id, "permission_management")
        document = DocumentService(permission_service=self).get_document(
            tenant_id, actor_id, document_id, permission="manage"
        )
        if principal_id == document.created_by and principal_type == "user":
            raise DmsValidationError("The document owner already has implicit access.")
        implications = DmsConfigurationService.runtime_values(tenant_id)["permission_implications"]
        if permission not in implications or principal_type not in {"user", "role", "group"}:
            raise DmsValidationError("Permission grant is invalid.")
        try:
            verified = self.identity.validate_principal(tenant_id, principal_type, principal_id)
        except Exception as exc:
            raise DmsDependencyUnavailable("Identity verification is unavailable.") from exc
        if verified is not True:
            raise DmsValidationError("Principal was not found in this tenant.")
        with transaction.atomic():
            if (
                DocumentPermission.objects.for_tenant(tenant_id)
                .alive()
                .filter(
                    document=document,
                    principal_type=principal_type,
                    principal_id=principal_id,
                    permission=permission,
                )
                .exists()
            ):
                raise DmsConflict("This live permission grant already exists.")
            grant = DocumentPermission.objects.create(
                tenant_id=tenant_id,
                document=document,
                principal_type=principal_type,
                principal_id=principal_id,
                permission=permission,
                created_by=actor_id,
            )
            _emit(
                tenant_id,
                "dms.permission.granted",
                "document_permission",
                grant.id,
                actor_id,
                document_id=document.id,
                permission=permission,
                principal_type=principal_type,
            )
            return grant

    def update_permission(
        self, tenant_id: UUID, actor_id: UUID, permission_id: UUID, *, permission: str
    ) -> DocumentPermission:
        DmsConfigurationService.require_feature(tenant_id, actor_id, "permission_management")
        if permission not in DmsConfigurationService.runtime_values(tenant_id)["permission_implications"]:
            raise DmsValidationError("Permission is invalid.")
        with transaction.atomic():
            grant = self.get_permission(tenant_id, actor_id, permission_id)
            grant = DocumentPermission.objects.select_for_update().get(id=grant.id)
            duplicate = (
                DocumentPermission.objects.for_tenant(tenant_id)
                .alive()
                .filter(
                    document=grant.document,
                    principal_type=grant.principal_type,
                    principal_id=grant.principal_id,
                    permission=permission,
                )
                .exclude(id=grant.id)
                .exists()
            )
            if duplicate:
                raise DmsConflict("This live permission grant already exists.")
            old_permission = grant.permission
            now = timezone.now()
            grant.is_deleted = True
            grant.deleted_at = now
            grant.save(update_fields=("is_deleted", "deleted_at", "updated_at"))
            replacement = DocumentPermission.objects.create(
                tenant_id=tenant_id,
                document=grant.document,
                principal_type=grant.principal_type,
                principal_id=grant.principal_id,
                permission=permission,
                created_by=actor_id,
            )
            _emit(
                tenant_id,
                "dms.permission.updated",
                "document_permission",
                replacement.id,
                actor_id,
                document_id=grant.document_id,
                previous_grant_id=grant.id,
                old_permission=old_permission,
                new_permission=permission,
            )
            return replacement

    def revoke_permission(self, tenant_id: UUID, actor_id: UUID, permission_id: UUID) -> None:
        DmsConfigurationService.require_feature(tenant_id, actor_id, "permission_management")
        with transaction.atomic():
            try:
                grant = self.get_permission(tenant_id, actor_id, permission_id)
            except DmsNotFound:
                prior = (
                    DocumentPermission.objects.for_tenant(tenant_id)
                    .select_related("document")
                    .filter(id=permission_id, is_deleted=True)
                    .first()
                )
                if prior is None:
                    raise
                self.require(tenant_id, actor_id, prior.document, "manage")
                grant = (
                    DocumentPermission.objects.for_tenant(tenant_id)
                    .alive()
                    .filter(
                        document=prior.document,
                        principal_type=prior.principal_type,
                        principal_id=prior.principal_id,
                    )
                    .order_by("-created_at")
                    .first()
                )
                if grant is None:
                    return
            grant = DocumentPermission.objects.select_for_update().get(id=grant.id)
            grant.is_deleted = True
            grant.deleted_at = timezone.now()
            grant.save(update_fields=("is_deleted", "deleted_at", "updated_at"))
            _emit(
                tenant_id,
                "dms.permission.revoked",
                "document_permission",
                grant.id,
                actor_id,
                document_id=grant.document_id,
            )


class VerifiedDownloadStream:
    """Closeable iterator that validates immutable storage evidence at EOF."""

    def __init__(self, handle: BinaryIO, expected_checksum: str, expected_size: int, chunk_size: int) -> None:
        self.handle = handle
        self.expected_checksum = expected_checksum
        self.expected_size = expected_size
        self.chunk_size = chunk_size
        self._closed = False

    def __iter__(self) -> Iterator[bytes]:
        digest = hashlib.sha256()
        measured = 0
        try:
            while True:
                chunk = self.handle.read(self.chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
                measured += len(chunk)
                yield chunk
            if measured != self.expected_size or not secrets.compare_digest(digest.hexdigest(), self.expected_checksum):
                raise DmsIntegrityFailure("Stored document integrity verification failed.")
        finally:
            self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.handle.close()


@dataclass(slots=True)
class DownloadArtifact:
    stream: VerifiedDownloadStream
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    document_id: UUID
    version_id: UUID


class DocumentService:
    def __init__(
        self,
        storage: DocumentStoragePort | None = None,
        permission_service: PermissionService | None = None,
        quota_service: Any | None = None,
    ) -> None:
        self.storage = storage
        self.permissions = permission_service or PermissionService()
        self.quota = quota_service or QuotaService()

    def _storage(self, backend: str = "django") -> DocumentStoragePort:
        return self.storage or get_document_storage(backend)

    def _folder(self, tenant_id: UUID, folder_id: UUID | None) -> Folder | None:
        if folder_id is None:
            return None
        try:
            return Folder.objects.for_tenant(tenant_id).alive().get(id=folder_id)
        except Folder.DoesNotExist as exc:
            raise DmsNotFound("Folder was not found.") from exc

    def _prepare_document_data(
        self,
        tenant_id: UUID,
        name: str,
        description: str,
        tags: Sequence[object] | None,
        metadata: object | None,
        *,
        existing_extensions: object | None = None,
    ) -> tuple[str, str, list[str], dict[str, object]]:
        return (
            _normalize_name(name, tenant_id=tenant_id),
            description.strip(),
            _normalize_tags(tags, tenant_id=tenant_id),
            _normalize_metadata(metadata, existing_extensions=existing_extensions, tenant_id=tenant_id),
        )

    def upload_document(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        file: BinaryIO,
        name: str,
        folder_id: UUID | None = None,
        description: str = "",
        tags: Sequence[object] | None = None,
        metadata: object | None = None,
        idempotency_key: str | None = None,
    ) -> Document:
        started = time.monotonic()
        DmsConfigurationService.require_feature(tenant_id, actor_id, "uploads")
        folder = self._folder(tenant_id, folder_id)
        normalized_name, normalized_description, normalized_tags, normalized_metadata = self._prepare_document_data(
            tenant_id, name, description, tags, metadata
        )
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 255):
            raise DmsValidationError("Idempotency key is invalid.")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "name": normalized_name,
                    "folder_id": str(folder_id) if folder_id else None,
                    "description": normalized_description,
                    "tags": normalized_tags,
                    "metadata": normalized_metadata,
                    "filename": str(getattr(file, "name", "")),
                    "size": getattr(file, "size", None),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
        idempotency = None
        if key_digest is not None:
            with transaction.atomic():
                idempotency = (
                    DmsUploadIdempotency.objects.select_for_update()
                    .filter(tenant_id=tenant_id, key_digest=key_digest)
                    .select_related("document")
                    .first()
                )
                if idempotency is not None:
                    if idempotency.request_fingerprint != fingerprint:
                        raise DmsConflict("Idempotency key was already used for a different upload.")
                    if idempotency.state == "completed" and idempotency.document is not None:
                        return idempotency.document
                    raise DmsConflict("An upload with this idempotency key is already in progress.")
                idempotency = DmsUploadIdempotency.objects.create(
                    tenant_id=tenant_id,
                    key_digest=key_digest,
                    request_fingerprint=fingerprint,
                )
        document_id, version_id = uuid.uuid4(), uuid.uuid4()
        _authorize_extensions(tenant_id, "upload", document_id, version_id)
        key = generate_storage_key(tenant_id, document_id, version_id)
        declared_size = getattr(file, "size", None)
        declared_mime = getattr(file, "content_type", None)
        original_filename = _normalize_name(
            str(getattr(file, "name", normalized_name)),
            "file",
            tenant_id=tenant_id,
        )
        storage = self._storage(str(DmsConfigurationService.runtime_values(tenant_id)["storage_backend"]))
        saved = storage.save(
            key,
            file,
            declared_size=declared_size,
            declared_mime_type=declared_mime,
        )
        quota_consumed = False
        try:
            quota = self.quota.consume(tenant_id, "dms.storage_bytes", cost=saved.size_bytes)
            if quota.allowed is not True:
                raise DmsPermissionDenied("Document storage quota is exhausted or unavailable.")
            quota_consumed = True
            with transaction.atomic():
                document = Document.objects.create(
                    id=document_id,
                    tenant_id=tenant_id,
                    name=normalized_name,
                    description=normalized_description,
                    folder=folder,
                    tags=normalized_tags,
                    metadata=normalized_metadata,
                    created_by=actor_id,
                    version_count=0,
                )
                version = DocumentVersion.objects.create(
                    id=version_id,
                    tenant_id=tenant_id,
                    document=document,
                    version_number=1,
                    storage_backend=storage.backend_name,
                    storage_key=saved.key,
                    original_filename=original_filename,
                    mime_type=saved.mime_type,
                    size_bytes=saved.size_bytes,
                    checksum_sha256=saved.checksum_sha256,
                    created_by=actor_id,
                )
                document.current_version = version
                document.version_count = 1
                document.save(update_fields=("current_version", "version_count", "updated_at"))
                if idempotency is not None:
                    idempotency.document = document
                    idempotency.version = version
                    idempotency.state = "completed"
                    idempotency.save(update_fields=("document", "version", "state", "updated_at"))
                _emit(
                    tenant_id,
                    "dms.document.uploaded",
                    "document",
                    document.id,
                    actor_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    version_number=1,
                    mime_type=version.mime_type,
                    size_bytes=version.size_bytes,
                )
            _log(
                "dms.document.uploaded",
                "success",
                started,
                tenant_id=str(tenant_id),
                actor_id=str(actor_id),
                document_id=str(document.id),
                version_id=str(version.id),
                size_bytes=saved.size_bytes,
            )
            return document
        except Exception:
            if quota_consumed:
                try:
                    with transaction.atomic():
                        quota_row = Quota.objects.select_for_update().get(
                            tenant_id=tenant_id,
                            resource="dms.storage_bytes",
                        )
                        quota_row.remaining = min(quota_row.limit, quota_row.remaining + saved.size_bytes)
                        quota_row.save(update_fields=("remaining", "updated_at"))
                except Exception:
                    _emit(
                        tenant_id,
                        "dms.quota.compensation_required",
                        "document",
                        document_id,
                        actor_id,
                        document_id=document_id,
                        document_version_id=version_id,
                        quota_resource="dms.storage_bytes",
                        quota_cost=saved.size_bytes,
                    )
            if idempotency is not None and idempotency.state == "pending":
                DmsUploadIdempotency.objects.filter(tenant_id=tenant_id, id=idempotency.id).delete()
            try:
                storage.delete(saved.key)
            except Exception:
                logger.error(
                    "DMS storage cleanup failed",
                    extra={
                        "event": "dms.storage.cleanup_failed",
                        "outcome": "failure",
                        "correlation_id": get_correlation_id(),
                        "tenant_id": str(tenant_id),
                        "actor_id": str(actor_id),
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "size_bytes": saved.size_bytes,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    },
                    exc_info=False,
                )
                try:
                    _emit(
                        tenant_id,
                        "dms.storage.cleanup_required",
                        "document",
                        document_id,
                        actor_id,
                        document_id=document_id,
                        document_version_id=version_id,
                        storage_backend=storage.backend_name,
                        storage_key=saved.key,
                    )
                except Exception:
                    logger.error(
                        "Durable DMS cleanup command could not be recorded",
                        extra={
                            "event": "dms.storage.cleanup_outbox_failed",
                            "outcome": "failure",
                            "correlation_id": get_correlation_id(),
                            "tenant_id": str(tenant_id),
                            "actor_id": str(actor_id),
                            "document_id": str(document_id),
                            "version_id": str(version_id),
                        },
                        exc_info=False,
                    )
            raise

    def list_documents(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        filters: Mapping[str, object] | None,
        search: str,
        ordering: str,
    ) -> QuerySet[Document]:
        queryset = (
            Document.objects.for_tenant(tenant_id)
            .alive()
            .filter(self.permissions.acl_query(tenant_id, actor_id, "read"))
            .select_related("folder", "current_version")
            .prefetch_related(
                Prefetch(
                    "permissions",
                    queryset=DocumentPermission.objects.for_tenant(tenant_id).alive(),
                    to_attr="_active_permissions",
                )
            )
            .distinct()
        )
        supplied = dict(filters or {})
        if "folder_id" in supplied:
            folder_id = supplied["folder_id"]
            queryset = queryset.filter(folder_id=folder_id) if folder_id else queryset.filter(folder__isnull=True)
        if supplied.get("mime_type"):
            queryset = queryset.filter(current_version__mime_type=supplied["mime_type"])
        if supplied.get("creator_id"):
            queryset = queryset.filter(created_by=supplied["creator_id"])
        if supplied.get("tag"):
            tag = str(supplied["tag"])
            queryset = (
                queryset.filter(tags__contains=[tag])
                if connection.features.supports_json_field_contains
                else queryset.filter(tags__icontains=f'"{tag}"')
            )
        if supplied.get("modified_after"):
            queryset = queryset.filter(updated_at__gte=supplied["modified_after"])
        if supplied.get("modified_before"):
            queryset = queryset.filter(updated_at__lte=supplied["modified_before"])
        if search:
            policy = DmsConfigurationService.runtime_values(tenant_id)
            if len(search) > policy["max_document_search_length"]:
                raise DmsValidationError("Search exceeds tenant policy.")
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        configured_ordering = DmsConfigurationService.runtime_values(tenant_id)["document_ordering_fields"]
        allowed_ordering = {field.lstrip("-") for field in configured_ordering}
        fields = [part.strip() for part in ordering.split(",") if part.strip()]
        if not fields or any(field.lstrip("-") not in allowed_ordering for field in fields):
            raise DmsValidationError("Ordering field is not allowed.")
        return queryset.order_by(*fields, "id")

    def get_document(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        permission: str = "read",
    ) -> Document:
        try:
            document = (
                Document.objects.for_tenant(tenant_id)
                .alive()
                .select_related("folder", "current_version")
                .get(id=document_id)
            )
        except Document.DoesNotExist as exc:
            raise DmsNotFound("Document was not found.") from exc
        self.permissions.require(tenant_id, actor_id, document, permission)
        document.allowed_actions = self.permissions.allowed_actions(tenant_id, actor_id, document)
        return document

    def update_document(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        expected_updated_at: datetime,
        name: str | None = None,
        description: str | None = None,
        tags: Sequence[object] | None = None,
        metadata: object | None = None,
    ) -> Document:
        with transaction.atomic():
            document = self.get_document(tenant_id, actor_id, document_id, permission="write")
            document = Document.objects.select_for_update().get(id=document.id)
            if document.updated_at != expected_updated_at:
                raise DmsConflict("Document metadata changed after it was loaded.")
            if name is not None:
                document.name = _normalize_name(name, tenant_id=tenant_id)
            if description is not None:
                document.description = description.strip()
            if tags is not None:
                document.tags = _normalize_tags(tags, tenant_id=tenant_id)
            if metadata is not None:
                extensions = (
                    document.metadata.get(RESERVED_METADATA_NAMESPACE) if isinstance(document.metadata, dict) else None
                )
                document.metadata = _normalize_metadata(
                    metadata,
                    existing_extensions=extensions,
                    tenant_id=tenant_id,
                )
            document.full_clean()
            document.save(update_fields=("name", "description", "tags", "metadata", "updated_at"))
            _emit(
                tenant_id, "dms.document.metadata_updated", "document", document.id, actor_id, document_id=document.id
            )
            document.allowed_actions = self.permissions.allowed_actions(tenant_id, actor_id, document)
            return document

    def move_document(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        folder_id: UUID | None,
        expected_updated_at: datetime | None = None,
    ) -> Document:
        target = self._folder(tenant_id, folder_id)
        with transaction.atomic():
            document = self.get_document(tenant_id, actor_id, document_id, permission="write")
            _authorize_extensions(tenant_id, "move", document.id, document.current_version_id)
            document = Document.objects.select_for_update().get(id=document.id)
            if expected_updated_at is not None and document.updated_at != expected_updated_at:
                raise DmsConflict("Document changed after it was loaded.")
            document.folder = target
            document.save(update_fields=("folder", "updated_at"))
            _emit(
                tenant_id,
                "dms.document.moved",
                "document",
                document.id,
                actor_id,
                document_id=document.id,
                folder_id=target.id if target else None,
            )
            document.allowed_actions = self.permissions.allowed_actions(tenant_id, actor_id, document)
            return document

    def _artifact(self, document: Document, version: DocumentVersion) -> DownloadArtifact:
        storage = self._storage(version.storage_backend)
        if not storage.exists(version.storage_key):
            raise DmsIntegrityFailure("Stored document content is unavailable.")
        try:
            handle = storage.open(version.storage_key)
        except Exception as exc:
            raise DmsDependencyUnavailable("Document storage is unavailable.") from exc
        return DownloadArtifact(
            VerifiedDownloadStream(
                handle,
                version.checksum_sha256,
                version.size_bytes,
                DmsConfigurationService.runtime_values(document.tenant_id)["download_verification_chunk_size"],
            ),
            version.original_filename,
            version.mime_type,
            version.size_bytes,
            version.checksum_sha256,
            document.id,
            version.id,
        )

    def download_document(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        version_id: UUID | None = None,
    ) -> DownloadArtifact:
        started = time.monotonic()
        document = self.get_document(tenant_id, actor_id, document_id, permission="read")
        if version_id is None:
            version = document.current_version
        else:
            version = DocumentVersion.objects.for_tenant(tenant_id).filter(id=version_id, document=document).first()
        if version is None:
            raise DmsNotFound("Document version was not found.")
        _authorize_extensions(tenant_id, "download", document.id, version.id)
        artifact = self._artifact(document, version)
        _emit(
            tenant_id,
            "dms.document.downloaded",
            "document",
            document.id,
            actor_id,
            document_id=document.id,
            document_version_id=version.id,
            size_bytes=version.size_bytes,
        )
        _log(
            "dms.document.downloaded",
            "authorized",
            started,
            tenant_id=str(tenant_id),
            actor_id=str(actor_id),
            document_id=str(document.id),
            version_id=str(version.id),
            size_bytes=version.size_bytes,
        )
        return artifact

    def delete_document(self, tenant_id: UUID, actor_id: UUID, document_id: UUID) -> None:
        with transaction.atomic():
            document = self.get_document(tenant_id, actor_id, document_id, permission="delete")
            _authorize_extensions(tenant_id, "delete", document.id, document.current_version_id)
            document = Document.objects.select_for_update().get(id=document.id)
            now = timezone.now()
            document.is_deleted = True
            document.deleted_at = now
            document.save(update_fields=("is_deleted", "deleted_at", "updated_at"))
            DocumentShare.objects.for_tenant(tenant_id).filter(document=document, revoked_at__isnull=True).update(
                revoked_at=now
            )
            _emit(tenant_id, "dms.document.deleted", "document", document.id, actor_id, document_id=document.id)


class VersionService:
    def __init__(self, document_service: DocumentService | None = None) -> None:
        self.documents = document_service or DocumentService()

    def create_version(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        file: BinaryIO,
        change_note: str,
        source_version: DocumentVersion | None = None,
    ) -> DocumentVersion:
        document = self.documents.get_document(tenant_id, actor_id, document_id, permission="write")
        version_id = uuid.uuid4()
        _authorize_extensions(tenant_id, "upload", document.id, version_id)
        key = generate_storage_key(tenant_id, document.id, version_id)
        policy = DmsConfigurationService.runtime_values(tenant_id)
        storage = self.documents._storage(str(policy["storage_backend"]))
        saved = storage.save(
            key,
            file,
            declared_size=getattr(file, "size", None),
            declared_mime_type=getattr(file, "content_type", None)
            or (source_version.mime_type if source_version else None),
        )
        original_filename = _normalize_name(
            str(getattr(file, "name", source_version.original_filename if source_version else document.name)),
            "file",
            tenant_id=tenant_id,
        )
        if len(change_note) > policy["version_change_note_max_length"]:
            raise DmsValidationError("Version change note exceeds tenant policy.")
        try:
            quota = self.documents.quota.consume(tenant_id, "dms.storage_bytes", cost=saved.size_bytes)
            if quota.allowed is not True:
                raise DmsPermissionDenied("Document storage quota is exhausted or unavailable.")
            with transaction.atomic():
                locked = Document.objects.for_tenant(tenant_id).alive().select_for_update().get(id=document.id)
                number = locked.version_count + 1
                version = DocumentVersion.objects.create(
                    id=version_id,
                    tenant_id=tenant_id,
                    document=locked,
                    version_number=number,
                    storage_backend=storage.backend_name,
                    storage_key=saved.key,
                    original_filename=original_filename,
                    mime_type=saved.mime_type,
                    size_bytes=saved.size_bytes,
                    checksum_sha256=saved.checksum_sha256,
                    change_note=change_note.strip(),
                    source_version=source_version,
                    created_by=actor_id,
                )
                locked.current_version = version
                locked.version_count = number
                locked.save(update_fields=("current_version", "version_count", "updated_at"))
                event_type = "dms.version.restored" if source_version else "dms.version.created"
                _emit(
                    tenant_id,
                    event_type,
                    "document_version",
                    version.id,
                    actor_id,
                    document_id=locked.id,
                    document_version_id=version.id,
                    version_number=number,
                    source_version_id=source_version.id if source_version else None,
                    mime_type=version.mime_type,
                    size_bytes=version.size_bytes,
                )
                return version
        except Exception:
            try:
                storage.delete(saved.key)
            except Exception:
                _emit(
                    tenant_id,
                    "dms.storage.cleanup_required",
                    "document",
                    document.id,
                    actor_id,
                    document_id=document.id,
                    document_version_id=version_id,
                    storage_backend=storage.backend_name,
                    storage_key=saved.key,
                )
            raise

    def list_versions(self, tenant_id: UUID, actor_id: UUID, document_id: UUID) -> QuerySet[DocumentVersion]:
        document = self.documents.get_document(tenant_id, actor_id, document_id)
        return (
            DocumentVersion.objects.for_tenant(tenant_id)
            .filter(document=document)
            .select_related("source_version")
            .order_by("-version_number")
        )

    def get_version(self, tenant_id: UUID, actor_id: UUID, version_id: UUID) -> DocumentVersion:
        try:
            version = (
                DocumentVersion.objects.for_tenant(tenant_id)
                .select_related("document", "source_version")
                .get(id=version_id)
            )
        except DocumentVersion.DoesNotExist as exc:
            raise DmsNotFound("Document version was not found.") from exc
        self.documents.permissions.require(tenant_id, actor_id, version.document, "read")
        return version

    def restore_version(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        version_id: UUID,
        *,
        change_note: str,
    ) -> DocumentVersion:
        source = self.get_version(tenant_id, actor_id, version_id)
        self.documents.permissions.require(tenant_id, actor_id, source.document, "write")
        _authorize_extensions(tenant_id, "restore", source.document_id, source.id)
        storage = self.documents._storage(source.storage_backend)
        if not storage.exists(source.storage_key):
            raise DmsIntegrityFailure("Stored document content is unavailable.")
        handle = storage.open(source.storage_key)
        try:
            return self.create_version(
                tenant_id,
                actor_id,
                source.document_id,
                file=handle,
                change_note=change_note
                or str(DmsConfigurationService.runtime_values(tenant_id)["restore_note_template"]).format(
                    version_number=source.version_number
                ),
                source_version=source,
            )
        finally:
            handle.close()


@dataclass(slots=True)
class ShareCreated:
    share: DocumentShare
    share_url: str


class ShareService:
    def __init__(self, document_service: DocumentService | None = None) -> None:
        self.documents = document_service or DocumentService()

    def create_share(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        expires_at: datetime,
        max_access_count: int | None = None,
        version_id: UUID | None = None,
    ) -> ShareCreated:
        DmsConfigurationService.require_feature(tenant_id, actor_id, "sharing")
        document = self.documents.get_document(tenant_id, actor_id, document_id, permission="share")
        policy = DmsConfigurationService.runtime_values(tenant_id)
        now = timezone.now()
        if expires_at <= now or expires_at > now + timedelta(days=policy["max_share_lifetime_days"]):
            raise DmsValidationError("Share expiry violates tenant policy.")
        if max_access_count is not None and not 1 <= max_access_count <= policy["max_share_access_count"]:
            raise DmsValidationError("Share access limit violates tenant policy.")
        if version_id is None:
            version = document.current_version
        else:
            version = DocumentVersion.objects.for_tenant(tenant_id).filter(id=version_id, document=document).first()
        if version is None:
            raise DmsNotFound("Document version was not found.")
        _authorize_extensions(tenant_id, "share", document.id, version.id)
        token = secrets.token_urlsafe(policy["share_token_entropy_bytes"])
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        prefix = token[: policy["share_token_prefix_length"]]
        with transaction.atomic():
            share = DocumentShare.objects.create(
                tenant_id=tenant_id,
                document=document,
                version=version,
                token_digest=digest,
                token_prefix=prefix,
                expires_at=expires_at,
                max_access_count=max_access_count,
                created_by=actor_id,
            )
            _emit(
                tenant_id,
                "dms.share.created",
                "document_share",
                share.id,
                actor_id,
                document_id=document.id,
                document_version_id=version.id,
                expires_at=expires_at.isoformat(),
                max_access_count=max_access_count,
            )
        return ShareCreated(share, f"/api/v2/dms/public/shares/{token}/download/")

    def list_shares(self, tenant_id: UUID, actor_id: UUID, document_id: UUID) -> QuerySet[DocumentShare]:
        document = self.documents.get_document(tenant_id, actor_id, document_id, permission="share")
        return (
            DocumentShare.objects.for_tenant(tenant_id)
            .filter(document=document)
            .select_related("version")
            .order_by("-created_at")
        )

    def get_share(self, tenant_id: UUID, actor_id: UUID, share_id: UUID) -> DocumentShare:
        try:
            share = DocumentShare.objects.for_tenant(tenant_id).select_related("document", "version").get(id=share_id)
        except DocumentShare.DoesNotExist as exc:
            raise DmsNotFound("Document share was not found.") from exc
        self.documents.permissions.require(tenant_id, actor_id, share.document, "share")
        return share

    def revoke_share(self, tenant_id: UUID, actor_id: UUID, share_id: UUID) -> DocumentShare:
        with transaction.atomic():
            share = self.get_share(tenant_id, actor_id, share_id)
            share = DocumentShare.objects.select_for_update().get(id=share.id)
            if share.revoked_at is None:
                share.revoked_at = timezone.now()
                share.save(update_fields=("revoked_at",))
                _emit(
                    tenant_id,
                    "dms.share.revoked",
                    "document_share",
                    share.id,
                    actor_id,
                    document_id=share.document_id,
                    document_version_id=share.version_id,
                )
            return share

    def consume_share(self, token: str) -> DownloadArtifact:
        if not token or len(token) > _INTEGER_BOUNDS["incoming_share_token_max_length"][1]:
            raise DmsNotFound("Shared document was not found.")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with transaction.atomic():
            try:
                share = (
                    DocumentShare.objects.select_for_update()
                    .select_related("document", "version")
                    .get(token_digest=digest)
                )
            except DocumentShare.DoesNotExist as exc:
                raise DmsNotFound("Shared document was not found.") from exc
            if len(token) > DmsConfigurationService.runtime_values(share.tenant_id)["incoming_share_token_max_length"]:
                raise DmsNotFound("Shared document was not found.")
            now = timezone.now()
            invalid = (
                share.revoked_at is not None
                or share.expires_at <= now
                or share.document.is_deleted
                or (share.max_access_count is not None and share.access_count >= share.max_access_count)
                or share.version.document_id != share.document_id
                or share.version.tenant_id != share.tenant_id
            )
            if invalid:
                raise DmsNotFound("Shared document was not found.")
            _authorize_extensions(share.tenant_id, "download", share.document_id, share.version_id)
            share.access_count += 1
            share.last_accessed_at = now
            share.save(update_fields=("access_count", "last_accessed_at"))
            _emit(
                share.tenant_id,
                "dms.share.consumed",
                "document_share",
                share.id,
                None,
                document_id=share.document_id,
                document_version_id=share.version_id,
                access_count=share.access_count,
            )
            return self.documents._artifact(share.document, share.version)


class MetadataExtensionService:
    """Namespaced paid-module metadata updates without user overwrite risk."""

    @staticmethod
    def patch_namespace(
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        *,
        namespace: str,
        schema_version: int,
        values: Mapping[str, object],
    ) -> Document:
        policy = DmsConfigurationService.runtime_values(tenant_id)
        if (
            not namespace
            or len(namespace) > policy["metadata_namespace_max_length"]
            or not all(part.isidentifier() for part in namespace.split("."))
        ):
            raise DmsValidationError("Metadata namespace is invalid.")
        if schema_version < 1:
            raise DmsValidationError("Metadata schema version must be positive.")
        _validate_json_primitives(dict(values), maximum_key_length=policy["max_metadata_key_length"])
        service = DocumentService()
        with transaction.atomic():
            document = service.get_document(tenant_id, actor_id, document_id, permission="write")
            document = Document.objects.select_for_update().get(id=document.id)
            metadata = dict(document.metadata)
            extensions = dict(metadata.get(RESERVED_METADATA_NAMESPACE, {}))
            extensions[namespace] = {"schema_version": schema_version, "values": dict(values)}
            metadata[RESERVED_METADATA_NAMESPACE] = extensions
            _validate_json_primitives(metadata, maximum_key_length=policy["max_metadata_key_length"])
            if len(json.dumps(metadata, separators=(",", ":")).encode()) > policy["max_metadata_bytes"]:
                raise DmsValidationError("Metadata is too large.")
            document.metadata = metadata
            document.save(update_fields=("metadata", "updated_at"))
            return document


class DmsDocumentIntelligenceGateway:
    """Concrete service-only gateway consumed by document intelligence."""

    def get_document(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> object:
        try:
            version = (
                DocumentVersion.objects.for_tenant(tenant_id)
                .select_related("document")
                .get(
                    id=document_version_id,
                    document_id=document_id,
                    document__is_deleted=False,
                )
            )
        except DocumentVersion.DoesNotExist as exc:
            raise DmsNotFound("Document version was not found.") from exc
        from src.modules.document_intelligence.adapters import DocumentDescriptor

        return DocumentDescriptor(
            document_id=document_id,
            document_version_id=document_version_id,
            mime_type=version.mime_type,
            byte_size=version.size_bytes,
            checksum=version.checksum_sha256,
            content_handle=str(version.id),
        )

    def open_content(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> BinaryIO:
        try:
            version = (
                DocumentVersion.objects.for_tenant(tenant_id)
                .select_related("document")
                .get(
                    id=document_version_id,
                    document_id=document_id,
                    document__is_deleted=False,
                )
            )
        except DocumentVersion.DoesNotExist as exc:
            raise DmsNotFound("Document version was not found.") from exc
        storage = get_document_storage(version.storage_backend)
        if not storage.exists(version.storage_key):
            raise DmsIntegrityFailure("Stored document content is unavailable.")
        return storage.open(version.storage_key)

    def health(self) -> object:
        from src.modules.document_intelligence.adapters import DependencyHealth

        result = get_document_storage().health_probe()
        return DependencyHealth(result.healthy, result.status, timezone.now(), "closed")


def register_document_intelligence_gateway() -> None:
    """Install the DMS gateway without replacing configured paid providers."""
    try:
        from src.modules.document_intelligence.adapters import configure_adapters, get_provider_resolver
    except ImportError:
        return
    configure_adapters(dms_gateway=DmsDocumentIntelligenceGateway(), provider_resolver=get_provider_resolver())


# Compatibility names resolve to real services; no fabricated legacy resource API remains.
DocumentStorageService = DocumentService
DmsService = DocumentService


__all__ = [
    "DmsConflict",
    "DmsDependencyUnavailable",
    "DmsDocumentIntelligenceGateway",
    "DmsError",
    "DmsIntegrityFailure",
    "DmsNotFound",
    "DmsPermissionDenied",
    "DmsValidationError",
    "DocumentService",
    "DocumentStorageService",
    "DownloadArtifact",
    "FolderContents",
    "FolderService",
    "IdentityDirectoryPort",
    "MetadataExtensionService",
    "PermissionService",
    "PrincipalSummary",
    "ShareCreated",
    "ShareService",
    "VerifiedDownloadStream",
    "VersionService",
    "configure_identity_directory",
    "get_identity_directory",
    "register_document_intelligence_gateway",
    "register_operation_guard",
    "unregister_operation_guard",
]
