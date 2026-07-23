"""Stable transactional events and extension contracts for DMS.

Event payloads are allowlisted at creation time.  This is intentionally safer
than attempting to scrub arbitrary dictionaries after filenames, document
content, credentials, or bearer tokens may already have entered the outbox.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, Protocol, TypeAlias

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue, get_handler
from src.core.observability import get_correlation_id, get_task_context

SCHEMA_VERSION: Final[int] = 1

FOLDER_CREATED: Final[str] = "dms.folder.created"
FOLDER_MOVED: Final[str] = "dms.folder.moved"
FOLDER_DELETED: Final[str] = "dms.folder.deleted"
DOCUMENT_UPLOADED: Final[str] = "dms.document.uploaded"
DOCUMENT_METADATA_UPDATED: Final[str] = "dms.document.metadata_updated"
DOCUMENT_MOVED: Final[str] = "dms.document.moved"
DOCUMENT_DOWNLOADED: Final[str] = "dms.document.downloaded"
DOCUMENT_DELETED: Final[str] = "dms.document.deleted"
VERSION_CREATED: Final[str] = "dms.version.created"
VERSION_RESTORED: Final[str] = "dms.version.restored"
PERMISSION_GRANTED: Final[str] = "dms.permission.granted"
PERMISSION_UPDATED: Final[str] = "dms.permission.updated"
PERMISSION_REVOKED: Final[str] = "dms.permission.revoked"
SHARE_CREATED: Final[str] = "dms.share.created"
SHARE_CONSUMED: Final[str] = "dms.share.consumed"
SHARE_REVOKED: Final[str] = "dms.share.revoked"
STORAGE_CLEANUP_REQUIRED: Final[str] = "dms.storage.cleanup_required"
QUOTA_COMPENSATION_REQUIRED: Final[str] = "dms.quota.compensation_required"

EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        FOLDER_CREATED,
        FOLDER_MOVED,
        FOLDER_DELETED,
        DOCUMENT_UPLOADED,
        DOCUMENT_METADATA_UPDATED,
        DOCUMENT_MOVED,
        DOCUMENT_DOWNLOADED,
        DOCUMENT_DELETED,
        VERSION_CREATED,
        VERSION_RESTORED,
        PERMISSION_GRANTED,
        PERMISSION_UPDATED,
        PERMISSION_REVOKED,
        SHARE_CREATED,
        SHARE_CONSUMED,
        SHARE_REVOKED,
        STORAGE_CLEANUP_REQUIRED,
        QUOTA_COMPENSATION_REQUIRED,
    }
)

SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "folder_id",
        "parent_id",
        "previous_parent_id",
        "depth",
        "document_id",
        "version_id",
        "document_version_id",
        "source_version_id",
        "version_number",
        "size_bytes",
        "mime_type",
        "permission_id",
        "principal_type",
        "permission",
        "old_permission",
        "new_permission",
        "previous_grant_id",
        "quota_resource",
        "quota_cost",
        "share_id",
        "expires_at",
        "max_access_count",
        "access_count",
        "storage_backend",
        "storage_key",
        "failure_code",
    }
)


JsonScalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class FolderEventData:
    folder_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    previous_parent_id: uuid.UUID | None = None
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class DocumentEventData:
    document_id: uuid.UUID
    version_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    previous_parent_id: uuid.UUID | None = None
    version_number: int | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    storage_backend: str | None = None


@dataclass(frozen=True, slots=True)
class VersionEventData:
    document_id: uuid.UUID
    version_id: uuid.UUID
    document_version_id: uuid.UUID
    version_number: int
    source_version_id: uuid.UUID | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    storage_backend: str | None = None


@dataclass(frozen=True, slots=True)
class PermissionEventData:
    document_id: uuid.UUID
    permission_id: uuid.UUID
    principal_type: str
    permission: str


@dataclass(frozen=True, slots=True)
class ShareEventData:
    document_id: uuid.UUID
    share_id: uuid.UUID
    version_id: uuid.UUID | None = None
    expires_at: str | None = None
    max_access_count: int | None = None
    access_count: int | None = None


@dataclass(frozen=True, slots=True)
class StorageCleanupEventData:
    """Internal compensation command; its opaque key is never API serialized."""

    storage_backend: str
    storage_key: str
    failure_code: str
    document_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None


EventData: TypeAlias = (
    FolderEventData
    | DocumentEventData
    | VersionEventData
    | PermissionEventData
    | ShareEventData
    | StorageCleanupEventData
)


@dataclass(frozen=True, slots=True)
class DmsEventPayload:
    """Versioned envelope persisted verbatim in the transactional outbox."""

    schema_version: int
    event_id: uuid.UUID
    tenant_id: uuid.UUID
    aggregate_id: uuid.UUID
    actor_id: uuid.UUID | None
    correlation_id: str
    occurred_at: datetime
    data: Mapping[str, JsonScalar] = field(default_factory=dict)
    causation_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": str(self.event_id),
            "tenant_id": str(self.tenant_id),
            "aggregate_id": str(self.aggregate_id),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "correlation_id": self.correlation_id,
            "occurred_at": self.occurred_at.isoformat(),
            "causation_id": self.causation_id,
            "data": {key: _json_value(value) for key, value in self.data.items() if value is not None},
        }


def _as_uuid(value: object, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _json_value(value: object) -> JsonScalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (uuid.UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError("DMS event data accepts only identifiers and JSON scalar metadata.")


def _event_data(payload: Mapping[str, object] | EventData | None) -> dict[str, JsonScalar]:
    supplied: Mapping[str, object]
    if payload is None:
        supplied = {}
    elif isinstance(payload, Mapping):
        supplied = payload
    else:
        supplied = asdict(payload)
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"DMS event contains non-allowlisted data: {', '.join(sorted(unsafe))}")
    return {key: _json_value(value) for key, value in supplied.items() if value is not None}


def publish_domain_event(
    tenant_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None,
    payload: Mapping[str, object] | EventData | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> OutboxEvent:
    """Persist one DMS event inside the caller's active transaction."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported DMS event type: {event_type}")
    if not isinstance(aggregate_type, str) or not aggregate_type.strip() or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    tenant_uuid = _as_uuid(tenant_id, "tenant_id")
    aggregate_uuid = _as_uuid(aggregate_id, "aggregate_id")
    actor_uuid = _as_uuid(actor_id, "actor_id") if actor_id is not None else None
    task_context = get_task_context()
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    cause = causation_id or (task_context.causation_id if task_context else None)
    event_id = uuid.uuid4()
    envelope = DmsEventPayload(
        schema_version=SCHEMA_VERSION,
        event_id=event_id,
        tenant_id=tenant_uuid,
        aggregate_id=aggregate_uuid,
        actor_id=actor_uuid,
        correlation_id=correlation,
        occurred_at=datetime.now(timezone.utc),
        causation_id=cause,
        data=_event_data(payload),
    )
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_uuid,
        aggregate_type=aggregate_type.strip(),
        aggregate_id=aggregate_uuid,
        event_type=event_type,
        payload=envelope.to_dict(),
    )


def publish_storage_cleanup_event(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    aggregate_id: uuid.UUID,
    storage_backend: str,
    storage_key: str,
    document_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    failure_code: str = "compensation_failed",
) -> OutboxEvent:
    """Durably schedule cleanup when immediate transaction compensation fails."""

    return publish_domain_event(
        tenant_id,
        STORAGE_CLEANUP_REQUIRED,
        "stored_object",
        aggregate_id,
        actor_id=actor_id,
        payload=StorageCleanupEventData(
            storage_backend=storage_backend,
            storage_key=storage_key,
            failure_code=failure_code,
            document_id=document_id,
            version_id=version_id,
        ),
    )


class DmsOperation(str, Enum):
    """Stable interception points for installed compliance/scanner modules."""

    UPLOAD = "upload"
    DOWNLOAD = "download"
    DELETE = "delete"
    RESTORE = "restore"
    SHARE = "share"
    MOVE = "move"


@dataclass(frozen=True, slots=True)
class OperationContext:
    tenant_id: uuid.UUID
    operation: DmsOperation
    document_id: uuid.UUID
    version_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    code: str = "allowed"


class OperationGuard(Protocol):
    """Paid modules implement this without importing DMS models."""

    def evaluate(self, context: OperationContext) -> GuardDecision:
        """Return an explicit decision; exceptions deny the protected operation."""


class ExtensionOperationError(RuntimeError):
    """A configured extension denied or could not evaluate an operation."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("A configured document operation guard denied the operation.")


_guard_lock = threading.RLock()
_operation_guards: dict[str, OperationGuard] = {}


def configure_operation_guards(guards: Mapping[str, OperationGuard]) -> None:
    """Atomically replace installed guards during explicit module wiring."""

    configured: dict[str, OperationGuard] = {}
    for name, guard in guards.items():
        normalized = name.strip().lower() if isinstance(name, str) else ""
        if not normalized or len(normalized) > 100:
            raise ValueError("Operation guard name must be a bounded non-empty string.")
        if not callable(getattr(guard, "evaluate", None)):
            raise TypeError("Operation guard must implement evaluate().")
        configured[normalized] = guard
    with _guard_lock:
        _operation_guards.clear()
        _operation_guards.update(configured)


def register_operation_guard(name: str, guard: OperationGuard, *, replace: bool = False) -> None:
    normalized = name.strip().lower() if isinstance(name, str) else ""
    if not normalized or len(normalized) > 100:
        raise ValueError("Operation guard name must be a bounded non-empty string.")
    if not callable(getattr(guard, "evaluate", None)):
        raise TypeError("Operation guard must implement evaluate().")
    with _guard_lock:
        if normalized in _operation_guards and not replace:
            raise ValueError(f"Operation guard {normalized!r} is already registered.")
        _operation_guards[normalized] = guard


def unregister_operation_guard(name: str) -> OperationGuard | None:
    with _guard_lock:
        return _operation_guards.pop(name.strip().lower(), None)


def run_operation_guards(
    tenant_id: uuid.UUID,
    operation: DmsOperation | str,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> None:
    """Run tenant-required guards and fail closed when evaluation is absent."""

    try:
        operation_value = operation if isinstance(operation, DmsOperation) else DmsOperation(operation)
    except ValueError as exc:
        raise ExtensionOperationError("unsupported_operation") from exc
    context = OperationContext(
        tenant_id=_as_uuid(tenant_id, "tenant_id"),
        operation=operation_value,
        document_id=_as_uuid(document_id, "document_id"),
        version_id=_as_uuid(version_id, "version_id") if version_id is not None else None,
    )
    with _guard_lock:
        guards: Sequence[OperationGuard] = tuple(_operation_guards.values())
    from .services import DmsConfigurationService

    required_operations = DmsConfigurationService.runtime_values(context.tenant_id)["governance_required_operations"]
    if operation_value.value in required_operations and not guards:
        raise ExtensionOperationError("guard_unavailable")
    for guard in guards:
        try:
            decision = guard.evaluate(context)
        except Exception as exc:
            raise ExtensionOperationError("guard_unavailable") from exc
        if not isinstance(decision, GuardDecision):
            raise ExtensionOperationError("invalid_guard_decision")
        if not decision.allowed:
            raise ExtensionOperationError(decision.code or "guard_denied")


@dataclass(frozen=True, slots=True)
class ExtensionCommand:
    """Tenant-first immutable-version command for async paid capabilities."""

    command: str
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    idempotency_key: str
    options: Mapping[str, JsonScalar] = field(default_factory=dict)


def enqueue_extension_command(command: ExtensionCommand) -> AsyncJob:
    """Atomically create the extension job and broker outbox request."""

    if not isinstance(command, ExtensionCommand):
        raise TypeError("command must be an ExtensionCommand")
    if not command.command.startswith("dms.extension."):
        raise ValueError("DMS extension command names must use the dms.extension namespace.")
    # Refuse a queued-looking success when no worker capability exists.
    get_handler(command.command)
    payload = {
        "tenant_id": str(_as_uuid(command.tenant_id, "tenant_id")),
        "document_id": str(_as_uuid(command.document_id, "document_id")),
        "version_id": str(_as_uuid(command.version_id, "version_id")),
        "options": {key: _json_value(value) for key, value in command.options.items()},
    }
    return enqueue(
        command.tenant_id,
        command.actor_id,
        command.command,
        payload,
        command.idempotency_key,
    )


__all__ = [
    "DOCUMENT_DELETED",
    "DOCUMENT_DOWNLOADED",
    "DOCUMENT_METADATA_UPDATED",
    "DOCUMENT_MOVED",
    "DOCUMENT_UPLOADED",
    "DmsEventPayload",
    "DmsOperation",
    "EVENT_TYPES",
    "ExtensionCommand",
    "ExtensionOperationError",
    "FOLDER_CREATED",
    "FOLDER_DELETED",
    "FOLDER_MOVED",
    "FolderEventData",
    "GuardDecision",
    "OperationContext",
    "PERMISSION_GRANTED",
    "PERMISSION_REVOKED",
    "PermissionEventData",
    "SCHEMA_VERSION",
    "SHARE_CONSUMED",
    "SHARE_CREATED",
    "SHARE_REVOKED",
    "STORAGE_CLEANUP_REQUIRED",
    "ShareEventData",
    "StorageCleanupEventData",
    "VERSION_CREATED",
    "VERSION_RESTORED",
    "VersionEventData",
    "configure_operation_guards",
    "enqueue_extension_command",
    "publish_domain_event",
    "publish_storage_cleanup_event",
    "register_operation_guard",
    "run_operation_guards",
    "unregister_operation_guard",
]
