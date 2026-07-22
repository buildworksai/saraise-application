"""Duplicate-safe provider registries and the open-source local adapter."""

from __future__ import annotations

import hashlib
import os
import queue
import random
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Generic, TypeVar, cast
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from src.core.health import HealthCheckResult
from src.core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError

from .ports import (
    ArtifactValidationResult,
    BackupArtifactDescriptor,
    BackupCatalogPort,
    BackupRequestReceipt,
    BackupScheduleSnapshot,
    BackupStatus,
    BackupStatusSnapshot,
    BackupType,
    RestoreCompensationResult,
    RestorePreflightResult,
    RestoreProviderReceipt,
    RestoreTarget,
    RestoreVerificationResult,
    ScopeType,
    StorageRecoveryAdapter,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    """Validated tenant policy applied uniformly to every provider call."""

    timeout_seconds: float
    max_attempts: int
    initial_backoff_seconds: float
    max_backoff_seconds: float
    jitter_seconds: float
    circuit_failure_threshold: int
    circuit_reset_seconds: float
    checksum_chunk_bytes: int
    local_filesystem_restore_modes: frozenset[str]


class ProviderTimeoutError(TimeoutError):
    """Raised when a provider does not complete inside its tenant limit."""


_active_policy: ContextVar[ResiliencePolicy | None] = ContextVar("bdr_resilience_policy", default=None)


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ProviderConfigurationError(f"{field} must be a positive number")
    return float(value)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProviderConfigurationError(f"{field} must be a positive integer")
    return value


def _policy_for(tenant_id: UUID | None) -> ResiliencePolicy:
    from .services import DEFAULT_CONFIGURATION_DOCUMENT, get_configuration

    document = get_configuration(tenant_id).document if tenant_id is not None else DEFAULT_CONFIGURATION_DOCUMENT
    resilience = document.get("resilience")
    providers = document.get("providers")
    if not isinstance(resilience, Mapping) or not isinstance(providers, Mapping):
        raise ProviderConfigurationError("provider resilience configuration is unavailable")
    raw_modes = providers.get("local_filesystem_restore_modes")
    if (
        not isinstance(raw_modes, (list, tuple))
        or not raw_modes
        or not all(isinstance(item, str) for item in raw_modes)
    ):
        raise ProviderConfigurationError("local filesystem restore modes are unavailable")
    policy = ResiliencePolicy(
        timeout_seconds=_positive_number(resilience.get("timeout_seconds"), "resilience.timeout_seconds"),
        max_attempts=_positive_integer(resilience.get("max_attempts"), "resilience.max_attempts"),
        initial_backoff_seconds=_positive_number(
            resilience.get("initial_backoff_seconds"), "resilience.initial_backoff_seconds"
        ),
        max_backoff_seconds=_positive_number(resilience.get("max_backoff_seconds"), "resilience.max_backoff_seconds"),
        jitter_seconds=_positive_number(resilience.get("jitter_seconds"), "resilience.jitter_seconds"),
        circuit_failure_threshold=_positive_integer(
            resilience.get("circuit_failure_threshold"), "resilience.circuit_failure_threshold"
        ),
        circuit_reset_seconds=_positive_number(
            resilience.get("circuit_reset_seconds"), "resilience.circuit_reset_seconds"
        ),
        checksum_chunk_bytes=_positive_integer(
            resilience.get("checksum_chunk_bytes"), "resilience.checksum_chunk_bytes"
        ),
        local_filesystem_restore_modes=frozenset(item.strip().lower() for item in raw_modes if item.strip()),
    )
    if not policy.local_filesystem_restore_modes:
        raise ProviderConfigurationError("local filesystem restore modes are unavailable")
    if policy.initial_backoff_seconds > policy.max_backoff_seconds:
        raise ProviderConfigurationError("initial provider backoff exceeds its maximum")
    return policy


class ProviderInvocationExecutor:
    """Bound every logical invocation and isolate repeated dependency failure."""

    def __init__(self) -> None:
        self._breakers: dict[tuple[UUID | None, str, int, float], CircuitBreaker[object]] = {}
        self._lock = threading.RLock()

    def _breaker(self, tenant_id: UUID | None, dependency: str, policy: ResiliencePolicy) -> CircuitBreaker[object]:
        key = (
            tenant_id,
            dependency,
            policy.circuit_failure_threshold,
            policy.circuit_reset_seconds,
        )
        with self._lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(
                    dependency=f"{tenant_id or 'global'}:{dependency}",
                    failure_threshold=policy.circuit_failure_threshold,
                    reset_timeout=policy.circuit_reset_seconds,
                )
                self._breakers[key] = breaker
            return breaker

    @staticmethod
    def _bounded(operation: Callable[[], T], timeout_seconds: float) -> T:
        outcomes: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        execution_context = copy_context()

        def invoke() -> None:
            try:
                outcomes.put_nowait((True, execution_context.run(operation)))
            except Exception as exc:
                outcomes.put_nowait((False, exc))

        worker = threading.Thread(target=invoke, name="bdr-provider-invocation", daemon=True)
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            raise ProviderTimeoutError("provider invocation exceeded its configured timeout")
        try:
            successful, result = outcomes.get_nowait()
        except queue.Empty as exc:
            raise ProviderOperationError("provider invocation produced no result") from exc
        if not successful:
            if isinstance(result, BaseException):
                raise result
            raise ProviderOperationError("provider invocation failed without an exception")
        return cast(T, result)

    def execute(self, tenant_id: UUID | None, dependency: str, operation: Callable[[], T]) -> T:
        if tenant_id is not None and not isinstance(tenant_id, UUID):
            raise ProviderConfigurationError("provider invocation requires a tenant UUID")
        policy = _policy_for(tenant_id)
        breaker = self._breaker(tenant_id, _required_text(dependency, "dependency"), policy)

        def attempt_all() -> T:
            token = _active_policy.set(policy)
            try:
                for attempt in range(policy.max_attempts):
                    try:
                        return self._bounded(operation, policy.timeout_seconds)
                    except Exception:
                        if attempt + 1 >= policy.max_attempts:
                            raise
                        exponential = policy.initial_backoff_seconds * (2**attempt)
                        delay = min(exponential, policy.max_backoff_seconds)
                        time.sleep(delay + random.uniform(0.0, policy.jitter_seconds))
                raise ProviderOperationError("provider retry policy completed without a result")
            finally:
                _active_policy.reset(token)

        return cast(T, breaker.call(attempt_all))

    def circuit_state(self, tenant_id: UUID | None, dependency: str) -> str:
        policy = _policy_for(tenant_id)
        return self._breaker(tenant_id, dependency, policy).state.value


provider_executor = ProviderInvocationExecutor()


def execute_provider_call(tenant_id: UUID | None, dependency: str, operation: Callable[[], T]) -> T:
    """Public, centrally governed invocation boundary for health/extensions."""

    return provider_executor.execute(tenant_id, dependency, operation)


def provider_circuit_state(tenant_id: UUID | None, dependency: str) -> str:
    return provider_executor.circuit_state(tenant_id, dependency)


class AdapterRegistryError(RuntimeError):
    """Base error for extension registration and lookup."""


class AdapterAlreadyRegistered(AdapterRegistryError):
    """Raised when import order would otherwise replace an adapter."""


class AdapterNotRegistered(AdapterRegistryError):
    """Raised when a required integration is unavailable."""


class ProviderConfigurationError(AdapterRegistryError):
    """Raised when a provider cannot operate with its current configuration."""


class ProviderOperationError(AdapterRegistryError):
    """Raised for a stable, sanitized provider failure."""


class _Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._entries: dict[str, T] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("registration key must be a non-empty string")
        normalized = key.strip().lower()
        if len(normalized) > 120:
            raise ValueError("registration key must not exceed 120 characters")
        return normalized

    def register(self, key: str, value: T, *, replace: bool = False) -> T:
        normalized = self._key(key)
        with self._lock:
            if normalized in self._entries and not replace:
                raise AdapterAlreadyRegistered(f"{self.kind} {normalized!r} is already registered")
            self._entries[normalized] = value
        return value

    def get(self, key: str) -> T:
        normalized = self._key(key)
        with self._lock:
            try:
                return self._entries[normalized]
            except KeyError as exc:
                raise AdapterNotRegistered(f"{self.kind} {normalized!r} is not registered") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._entries))

    def unregister(self, key: str) -> T | None:
        """Remove a registration for controlled tests and application shutdown."""
        with self._lock:
            return self._entries.pop(self._key(key), None)


_backup_catalogs: _Registry[BackupCatalogPort] = _Registry("backup catalog")
_storage_adapters: _Registry[StorageRecoveryAdapter] = _Registry("storage adapter")
_extension_actions: _Registry[Callable[..., object]] = _Registry("extension action")
_evidence_enrichers: _Registry[Callable[..., Mapping[str, object]]] = _Registry("evidence enricher")
_report_exporters: _Registry[Callable[..., bytes]] = _Registry("report exporter")
_readiness_rules: _Registry[Callable[..., object]] = _Registry("readiness rule")
_provider_health_probes: _Registry[Callable[[], HealthCheckResult]] = _Registry("provider health probe")
_metrics_collectors: _Registry[Callable[[], None]] = _Registry("metrics collector")

_CATALOG_METHODS = (
    "request_backup",
    "get_backup_status",
    "describe_completed_artifact",
    "validate_schedule",
)
_STORAGE_METHODS = (
    "validate_artifact",
    "validate_restore_target",
    "restore",
    "verify_restore",
    "compensate_restore",
)


def _tenant_argument(args: tuple[object, ...], kwargs: Mapping[str, object]) -> UUID:
    raw = args[0] if args else kwargs.get("tenant_id")
    if not isinstance(raw, UUID):
        raise ProviderConfigurationError("provider invocation requires tenant_id as a UUID")
    return raw


def _install_resilience(value: T, *, dependency: str, methods: tuple[str, ...]) -> T:
    """Instrument a provider in place so registry lookup preserves identity."""

    installed = getattr(value, "__bdr_resilient_methods__", frozenset())
    if not isinstance(installed, frozenset):
        raise TypeError("provider resilience metadata is invalid")
    completed = set(installed)
    for method_name in methods:
        if method_name in completed:
            continue
        original = getattr(value, method_name, None)
        if not callable(original):
            continue

        @wraps(original)
        def governed(
            *args: object, __method: Callable[..., object] = original, __name: str = method_name, **kwargs: object
        ) -> object:
            tenant_id = _tenant_argument(args, kwargs)
            return execute_provider_call(
                tenant_id,
                f"{dependency}.{__name}",
                lambda: __method(*args, **kwargs),
            )

        try:
            setattr(value, method_name, governed)
        except (AttributeError, TypeError) as exc:
            raise TypeError(f"provider method {method_name!r} cannot be resilience-wrapped") from exc
        completed.add(method_name)
    try:
        setattr(value, "__bdr_resilient_methods__", frozenset(completed))
    except (AttributeError, TypeError) as exc:
        raise TypeError("provider cannot retain resilience metadata") from exc
    return value


def register_backup_catalog(
    key: str,
    adapter: BackupCatalogPort,
    *,
    replace: bool = False,
) -> BackupCatalogPort:
    if not isinstance(adapter, BackupCatalogPort):
        raise TypeError("adapter must implement BackupCatalogPort")
    normalized = _Registry._key(key)
    governed = _install_resilience(
        adapter,
        dependency=f"backup-catalog.{normalized}",
        methods=_CATALOG_METHODS,
    )
    return _backup_catalogs.register(normalized, governed, replace=replace)


def get_backup_catalog(key: str = "default") -> BackupCatalogPort:
    return _backup_catalogs.get(key)


def register_storage_adapter(
    key: str,
    adapter: StorageRecoveryAdapter,
    *,
    replace: bool = False,
) -> StorageRecoveryAdapter:
    if not isinstance(adapter, StorageRecoveryAdapter):
        raise TypeError("adapter must implement StorageRecoveryAdapter")
    normalized = _Registry._key(key)
    governed = _install_resilience(
        adapter,
        dependency=f"storage-adapter.{normalized}",
        methods=_STORAGE_METHODS,
    )
    return _storage_adapters.register(normalized, governed, replace=replace)


def get_storage_adapter(key: str) -> StorageRecoveryAdapter:
    return _storage_adapters.get(key)


def list_storage_adapters() -> tuple[str, ...]:
    return _storage_adapters.keys()


def unregister_backup_catalog(key: str) -> BackupCatalogPort | None:
    return _backup_catalogs.unregister(key)


def unregister_storage_adapter(key: str) -> StorageRecoveryAdapter | None:
    return _storage_adapters.unregister(key)


def register_extension_action(
    key: str,
    handler: Callable[..., object],
    *,
    replace: bool = False,
) -> Callable[..., object]:
    if not callable(handler):
        raise TypeError("extension action must be callable")
    return _extension_actions.register(key, handler, replace=replace)


def get_extension_action(key: str) -> Callable[..., object]:
    return _extension_actions.get(key)


def _register_callable(
    registry: _Registry[T],
    key: str,
    value: T,
    *,
    replace: bool,
) -> T:
    if not callable(value):
        raise TypeError("extension must be callable")
    return registry.register(key, value, replace=replace)


def register_evidence_enricher(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_evidence_enrichers, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_report_exporter(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_report_exporters, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_readiness_rule(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_readiness_rules, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_provider_health_probe(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(  # type: ignore[arg-type,return-value]
        _provider_health_probes, key, value, replace=replace
    )


def register_metrics_collector(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_metrics_collectors, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def get_evidence_enricher(key: str) -> Callable[..., Mapping[str, object]]:
    return _evidence_enrichers.get(key)


def get_report_exporter(key: str) -> Callable[..., bytes]:
    return _report_exporters.get(key)


def get_readiness_rule(key: str) -> Callable[..., object]:
    return _readiness_rules.get(key)


def get_provider_health_probe(key: str) -> Callable[[], HealthCheckResult]:
    return _provider_health_probes.get(key)


def get_metrics_collector(key: str) -> Callable[[], None]:
    return _metrics_collectors.get(key)


def _required_text(value: object, field: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderOperationError(f"{field} is unavailable")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ProviderOperationError(f"{field} exceeds the supported length")
    return normalized


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProviderOperationError(f"{field} is not a valid UUID") from exc


def _status(value: object) -> BackupStatus:
    if isinstance(value, BackupStatus):
        return value
    try:
        return BackupStatus(str(value))
    except ValueError as exc:
        raise ProviderOperationError("backup catalog returned an unsupported status") from exc


class BackupRecoveryCatalogAdapter:
    """Normalize ``backup_recovery`` service results without importing its ORM.

    A service instance can be injected by paid modules and tests.  Importing the
    legacy service is intentionally lazy so this module never creates a reverse
    model dependency during Django application loading.
    """

    def __init__(self, service: object | None = None) -> None:
        self._service = service

    def _get_service(self) -> object:
        if self._service is None:
            from src.modules.backup_recovery.services import BackupRecoveryService

            self._service = BackupRecoveryService()
        return self._service

    def request_backup(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        backup_type: BackupType,
        scope_type: ScopeType,
        scope_ref: str,
        idempotency_key: str,
    ) -> BackupRequestReceipt:
        service = self._get_service()
        scope = _required_text(scope_ref, "scope_ref")
        key = _required_text(idempotency_key, "idempotency_key")
        native = getattr(service, "request_backup", None)
        if callable(native):
            raw = native(
                tenant_id,
                actor_id,
                backup_type=backup_type,
                scope_type=scope_type,
                scope_ref=scope,
                idempotency_key=key,
            )
        else:
            create = getattr(service, "create_backup_job", None)
            if not callable(create):
                raise ProviderConfigurationError("backup catalog request capability is unavailable")
            raw = create(
                tenant_id=str(tenant_id),
                backup_type=backup_type.value,
                description=f"{scope_type.value}:{scope}",
                created_by=str(actor_id),
            )
        if isinstance(raw, BackupRequestReceipt):
            return raw
        return BackupRequestReceipt(
            backup_job_id=_uuid(getattr(raw, "id", None), "backup_job_id"),
            status=_status(getattr(raw, "status", None)),
            idempotency_key=key,
        )

    def get_backup_status(self, tenant_id: UUID, backup_job_id: UUID) -> BackupStatusSnapshot:
        service = self._get_service()
        native = getattr(service, "get_backup_status", None)
        if callable(native):
            raw = native(tenant_id, backup_job_id)
        else:
            get_job = getattr(service, "get_backup_job", None)
            if not callable(get_job):
                raise ProviderConfigurationError("backup catalog status capability is unavailable")
            raw = get_job(str(backup_job_id), str(tenant_id))
        if raw is None:
            raise ProviderOperationError("backup job was not found")
        if isinstance(raw, BackupStatusSnapshot):
            return raw
        return BackupStatusSnapshot(
            backup_job_id=_uuid(getattr(raw, "id", None), "backup_job_id"),
            status=_status(getattr(raw, "status", None)),
            completed_at=getattr(raw, "end_time", getattr(raw, "completed_at", None)),
            error_code=(
                _required_text(getattr(raw, "error_code", "") or "none", "error_code", maximum=64)
                if getattr(raw, "error_code", "")
                else ""
            ),
        )

    def describe_completed_artifact(
        self,
        tenant_id: UUID,
        backup_job_id: UUID,
    ) -> BackupArtifactDescriptor:
        service = self._get_service()
        native = getattr(service, "describe_completed_artifact", None)
        if callable(native):
            raw = native(tenant_id, backup_job_id)
        else:
            return self._describe_legacy_artifact(service, tenant_id, backup_job_id)
        if isinstance(raw, BackupArtifactDescriptor):
            return raw
        if not isinstance(raw, Mapping):
            raise ProviderOperationError("backup catalog returned an invalid artifact descriptor")
        try:
            return BackupArtifactDescriptor(
                backup_job_id=_uuid(raw["backup_job_id"], "backup_job_id"),
                backup_archive_id=(
                    _uuid(raw["backup_archive_id"], "backup_archive_id") if raw.get("backup_archive_id") else None
                ),
                adapter_key=_required_text(raw.get("adapter_key"), "adapter_key", maximum=64),
                artifact_locator_ref=_required_text(raw.get("artifact_locator_ref"), "artifact_locator_ref"),
                encryption_key_ref=str(raw["encryption_key_ref"]) if raw.get("encryption_key_ref") else None,
                scope_type=(
                    raw["scope_type"] if isinstance(raw["scope_type"], ScopeType) else ScopeType(str(raw["scope_type"]))
                ),
                scope_ref=_required_text(raw.get("scope_ref"), "scope_ref"),
                backup_type=(
                    raw["backup_type"]
                    if isinstance(raw["backup_type"], BackupType)
                    else BackupType(str(raw["backup_type"]))
                ),
                data_cutoff_at=cast(datetime, raw["data_cutoff_at"]),
                captured_at=cast(datetime, raw["captured_at"]),
                expires_at=cast(datetime | None, raw.get("expires_at")),
                size_bytes=cast(int | None, raw.get("size_bytes")),
                checksum_algorithm=_required_text(raw.get("checksum_algorithm"), "checksum_algorithm", maximum=16),
                checksum_digest=_required_text(raw.get("checksum_digest"), "checksum_digest", maximum=64),
                provider_acknowledgement=_required_text(
                    raw.get("provider_acknowledgement"), "provider_acknowledgement"
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderOperationError("backup catalog returned an invalid artifact descriptor") from exc

    @staticmethod
    def _describe_legacy_artifact(
        service: object,
        tenant_id: UUID,
        backup_job_id: UUID,
    ) -> BackupArtifactDescriptor:
        """Normalize the legacy service only when every required fact is provable."""
        get_job = getattr(service, "get_backup_job", None)
        if not callable(get_job):
            raise ProviderConfigurationError("backup catalog artifact capability is unavailable")
        job = get_job(str(backup_job_id), str(tenant_id))
        if job is None:
            raise ProviderOperationError("backup job was not found")
        if _status(getattr(job, "status", None)) is not BackupStatus.COMPLETED:
            raise ProviderOperationError("backup artifact is not provider-confirmed complete")

        description = _required_text(getattr(job, "description", None), "backup scope")
        if ":" not in description:
            raise ProviderOperationError("backup scope provenance is unavailable")
        raw_scope_type, raw_scope_ref = description.split(":", 1)
        try:
            scope_type = ScopeType(raw_scope_type)
        except ValueError as exc:
            raise ProviderOperationError("backup scope provenance is invalid") from exc
        scope_ref = _required_text(raw_scope_ref, "scope_ref")

        locator_ref = _required_text(getattr(job, "storage_location", None), "artifact locator")
        storage_root_value = getattr(settings, "BDR_LOCAL_STORAGE_ROOT", None)
        if not storage_root_value:
            raise ProviderConfigurationError("local filesystem storage root is not configured")
        storage_root = Path(storage_root_value).expanduser()
        artifact_path = LocalFilesystemStorageRecoveryAdapter._confined(
            storage_root,
            locator_ref,
            "artifact locator",
        )
        if not artifact_path.is_file():
            raise ProviderOperationError("completed backup artifact is unavailable")
        checksum, size = LocalFilesystemStorageRecoveryAdapter._checksum(artifact_path)
        reported_size = getattr(job, "backup_size_bytes", None)
        if reported_size is not None and reported_size != size:
            raise ProviderOperationError("completed backup artifact size does not match catalog evidence")

        captured_at = getattr(job, "end_time", None)
        if not isinstance(captured_at, datetime):
            raise ProviderOperationError("backup completion timestamp is unavailable")
        raw_backup_type = getattr(job, "backup_type", None)
        try:
            backup_type = raw_backup_type if isinstance(raw_backup_type, BackupType) else BackupType(raw_backup_type)
        except (TypeError, ValueError) as exc:
            raise ProviderOperationError("backup type provenance is invalid") from exc
        return BackupArtifactDescriptor(
            backup_job_id=_uuid(getattr(job, "id", None), "backup_job_id"),
            backup_archive_id=None,
            adapter_key=LocalFilesystemStorageRecoveryAdapter.key,
            artifact_locator_ref=Path(locator_ref).as_posix(),
            encryption_key_ref=None,
            scope_type=scope_type,
            scope_ref=scope_ref,
            backup_type=backup_type,
            data_cutoff_at=captured_at,
            captured_at=captured_at,
            expires_at=None,
            size_bytes=size,
            checksum_algorithm="sha256",
            checksum_digest=checksum,
            provider_acknowledgement=f"completed:{backup_job_id}:{checksum}",
        )

    def validate_schedule(self, tenant_id: UUID, backup_schedule_id: UUID) -> BackupScheduleSnapshot:
        service = self._get_service()
        native = getattr(service, "validate_schedule", None)
        if callable(native):
            raw = native(tenant_id, backup_schedule_id)
        else:
            get_schedule = getattr(service, "get_backup_schedule", None)
            if not callable(get_schedule):
                raise ProviderConfigurationError("backup schedule capability is unavailable")
            raw = get_schedule(str(backup_schedule_id), str(tenant_id))
        if raw is None:
            raise ProviderOperationError("backup schedule was not found")
        if isinstance(raw, BackupScheduleSnapshot):
            return raw
        return BackupScheduleSnapshot(
            backup_schedule_id=_uuid(getattr(raw, "id", None), "backup_schedule_id"),
            active=bool(getattr(raw, "is_active", False)),
            backup_type=(
                getattr(raw, "backup_type")
                if isinstance(getattr(raw, "backup_type", None), BackupType)
                else BackupType(str(getattr(raw, "backup_type", "")))
            ),
            frequency=_required_text(getattr(raw, "frequency", None), "frequency", maximum=64),
        )


class LocalFilesystemStorageRecoveryAdapter:
    """Constrained OSS provider with streaming checksums and atomic restores."""

    key = "local-filesystem"

    def __init__(
        self,
        *,
        storage_root: str | Path | None = None,
        restore_root: str | Path | None = None,
        breaker: CircuitBreaker[object] | None = None,
    ) -> None:
        configured_storage = storage_root or getattr(settings, "BDR_LOCAL_STORAGE_ROOT", None)
        configured_restore = restore_root or getattr(settings, "BDR_LOCAL_RESTORE_ROOT", None)
        self._storage_root = Path(configured_storage).expanduser() if configured_storage else None
        self._restore_root = Path(configured_restore).expanduser() if configured_restore else None
        self._breaker = breaker

    @property
    def circuit_state(self) -> str:
        return self._breaker.state.value if self._breaker is not None else "managed"

    def _call(self, operation: Callable[[], T]) -> T:
        if self._breaker is None:
            return operation()
        return cast(T, self._breaker.call(operation))

    @staticmethod
    def _confined(root: Path | None, reference: str, field: str) -> Path:
        if root is None:
            raise ProviderConfigurationError(f"local filesystem {field} root is not configured")
        ref = _required_text(reference, field)
        candidate_ref = Path(ref)
        if candidate_ref.is_absolute() or ".." in candidate_ref.parts:
            raise ProviderOperationError(f"{field} must be a confined relative reference")
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as exc:
            raise ProviderConfigurationError(f"local filesystem {field} root is unavailable") from exc
        try:
            candidate = (resolved_root / candidate_ref).resolve(strict=False)
        except OSError as exc:
            raise ProviderOperationError(f"{field} could not be resolved") from exc
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ProviderOperationError(f"{field} escapes its configured root")
        return candidate

    @staticmethod
    def _checksum(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("rb") as stream:
                policy = _active_policy.get()
                read_chunk = (lambda: stream.read(policy.checksum_chunk_bytes)) if policy is not None else stream.read1
                for chunk in iter(read_chunk, b""):
                    digest.update(chunk)
                    size += len(chunk)
        except OSError as exc:
            raise ProviderOperationError("local filesystem artifact could not be read") from exc
        return digest.hexdigest(), size

    def _artifact(self, descriptor: BackupArtifactDescriptor) -> Path:
        if descriptor.adapter_key != self.key:
            raise ProviderOperationError("artifact belongs to a different storage adapter")
        if descriptor.checksum_algorithm != "sha256":
            raise ProviderOperationError("unsupported checksum algorithm")
        return self._confined(self._storage_root, descriptor.artifact_locator_ref, "artifact locator")

    def validate_artifact(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        *,
        idempotency_key: str,
    ) -> ArtifactValidationResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")

        def operation() -> ArtifactValidationResult:
            path = self._artifact(descriptor)
            if not path.is_file():
                return ArtifactValidationResult(
                    valid=False,
                    checksum_matches=False,
                    artifact_available=False,
                    encryption_metadata_valid=descriptor.encryption_key_ref is None,
                    provider_acknowledged=False,
                    evidence={"algorithm": "sha256"},
                    error_code="artifact_missing",
                )
            checksum, actual_size = self._checksum(path)
            checksum_matches = checksum == descriptor.checksum_digest
            size_matches = descriptor.size_bytes is None or descriptor.size_bytes == actual_size
            encryption_valid = descriptor.encryption_key_ref is None or bool(descriptor.encryption_key_ref.strip())
            valid = checksum_matches and size_matches and encryption_valid and bool(descriptor.provider_acknowledgement)
            return ArtifactValidationResult(
                valid=valid,
                checksum_matches=checksum_matches,
                artifact_available=True,
                encryption_metadata_valid=encryption_valid,
                provider_acknowledged=bool(descriptor.provider_acknowledgement),
                evidence={"algorithm": "sha256", "size_bytes": actual_size},
                error_code="" if valid else "artifact_integrity_failed",
            )

        return self._call(operation)

    def validate_restore_target(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        target: RestoreTarget,
        *,
        idempotency_key: str,
    ) -> RestorePreflightResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")

        def operation() -> RestorePreflightResult:
            policy = _active_policy.get()
            if policy is None:
                raise ProviderConfigurationError("tenant provider policy is not bound")
            source = self._artifact(descriptor)
            destination = self._confined(self._restore_root, target.target_ref, "restore target")
            artifact_available = source.is_file()
            required_bytes = descriptor.size_bytes
            capacity_valid = (
                artifact_available
                and isinstance(required_bytes, int)
                and required_bytes >= 0
                and self._restore_root is not None
                and shutil.disk_usage(self._restore_root).free >= required_bytes
            )
            compatibility_valid = (
                target.mode.value in policy.local_filesystem_restore_modes and descriptor.checksum_algorithm == "sha256"
            )
            target_available = not destination.exists()
            if destination.is_file():
                checksum, _ = self._checksum(destination)
                target_available = checksum == descriptor.checksum_digest
            valid = capacity_valid and compatibility_valid and target_available
            return RestorePreflightResult(
                capacity_valid=capacity_valid,
                compatibility_valid=compatibility_valid,
                target_available=target_available,
                evidence={
                    "artifact_available": artifact_available,
                    "capacity_measured": isinstance(required_bytes, int),
                    "target_inspected": True,
                },
                error_code="" if valid else "restore_preflight_failed",
            )

        return self._call(operation)

    def restore(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        target: RestoreTarget,
        *,
        idempotency_key: str,
    ) -> RestoreProviderReceipt:
        del tenant_id
        key = _required_text(idempotency_key, "idempotency_key")
        policy = _active_policy.get()
        if policy is not None and target.mode.value not in policy.local_filesystem_restore_modes:
            raise ProviderOperationError("restore mode is disabled by tenant provider policy")

        def operation() -> RestoreProviderReceipt:
            source = self._artifact(descriptor)
            if not source.is_file():
                raise ProviderOperationError("artifact is unavailable")
            source_checksum, source_size = self._checksum(source)
            if source_checksum != descriptor.checksum_digest:
                raise ProviderOperationError("artifact checksum mismatch")
            destination = self._confined(self._restore_root, target.target_ref, "restore target")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not destination.is_file():
                    raise ProviderOperationError("restore target is not a regular file")
                existing_checksum, existing_size = self._checksum(destination)
                if existing_checksum != source_checksum:
                    raise ProviderOperationError("restore target already contains different data")
                return RestoreProviderReceipt(
                    operation_id=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                    accepted=True,
                    completed=True,
                    evidence={
                        "target_ref": target.target_ref,
                        "checksum_digest": existing_checksum,
                        "size_bytes": existing_size,
                    },
                )
            descriptor_fd, temporary_name = tempfile.mkstemp(prefix=".bdr-restore-", dir=destination.parent)
            os.close(descriptor_fd)
            temporary = Path(temporary_name)
            try:
                shutil.copyfile(source, temporary)
                restored_checksum, restored_size = self._checksum(temporary)
                if restored_checksum != source_checksum:
                    raise ProviderOperationError("restored artifact checksum mismatch")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            return RestoreProviderReceipt(
                operation_id=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                accepted=True,
                completed=True,
                evidence={
                    "target_ref": target.target_ref,
                    "checksum_digest": source_checksum,
                    "size_bytes": source_size,
                },
            )

        return self._call(operation)

    def verify_restore(
        self,
        tenant_id: UUID,
        receipt: RestoreProviderReceipt,
        *,
        idempotency_key: str,
    ) -> RestoreVerificationResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")
        if not receipt.accepted or not receipt.completed:
            return RestoreVerificationResult(verified=False, error_code="restore_not_completed")
        target_ref = receipt.evidence.get("target_ref")
        expected_checksum = receipt.evidence.get("checksum_digest")
        if not isinstance(target_ref, str) or not isinstance(expected_checksum, str):
            return RestoreVerificationResult(verified=False, error_code="invalid_provider_receipt")

        def operation() -> RestoreVerificationResult:
            destination = self._confined(self._restore_root, target_ref, "restore target")
            if not destination.is_file():
                return RestoreVerificationResult(verified=False, error_code="restore_missing")
            actual_checksum, size = self._checksum(destination)
            verified = actual_checksum == expected_checksum
            return RestoreVerificationResult(
                verified=verified,
                evidence={"algorithm": "sha256", "size_bytes": size},
                error_code="" if verified else "restore_checksum_mismatch",
            )

        return self._call(operation)

    def compensate_restore(
        self,
        tenant_id: UUID,
        receipt: RestoreProviderReceipt,
        *,
        idempotency_key: str,
    ) -> RestoreCompensationResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")
        target_ref = receipt.evidence.get("target_ref")
        expected_checksum = receipt.evidence.get("checksum_digest")
        if not isinstance(target_ref, str) or not isinstance(expected_checksum, str):
            raise ProviderOperationError("provider receipt lacks compensation evidence")

        def operation() -> RestoreCompensationResult:
            destination = self._confined(self._restore_root, target_ref, "restore target")
            if not destination.exists():
                return RestoreCompensationResult(True, evidence={"target_absent": True})
            if not destination.is_file():
                raise ProviderOperationError("restore target is not a regular file")
            actual_checksum, _ = self._checksum(destination)
            if actual_checksum != expected_checksum:
                raise ProviderOperationError("restore target changed after provider operation")
            try:
                destination.unlink()
            except OSError as exc:
                raise ProviderOperationError("restore target compensation failed") from exc
            return RestoreCompensationResult(True, evidence={"target_removed": True})

        return self._call(operation)

    def health(self) -> HealthCheckResult:
        checked_at = timezone.now()

        def operation() -> HealthCheckResult:
            if self._storage_root is None or self._restore_root is None:
                return HealthCheckResult(
                    healthy=False,
                    message="local filesystem provider is not configured",
                    checked_at=checked_at,
                )
            try:
                storage_root = self._storage_root.resolve(strict=True)
                restore_root = self._restore_root.resolve(strict=True)
            except OSError:
                return HealthCheckResult(False, "local filesystem provider root is unavailable", checked_at)
            healthy = (
                storage_root.is_dir()
                and restore_root.is_dir()
                and os.access(storage_root, os.R_OK)
                and os.access(restore_root, os.R_OK | os.W_OK)
            )
            return HealthCheckResult(
                healthy=healthy,
                message="" if healthy else "local filesystem provider permissions are unavailable",
                checked_at=checked_at,
                details={"adapter": self.key, "circuit_state": self.circuit_state},
            )

        try:
            return self._call(operation)
        except CircuitBreakerError:
            return HealthCheckResult(
                healthy=False,
                message="storage provider circuit is open",
                checked_at=checked_at,
                details={"adapter": self.key, "circuit_state": "open"},
            )
        except Exception:
            return HealthCheckResult(
                healthy=False,
                message="storage provider probe failed",
                checked_at=checked_at,
                details={"adapter": self.key},
            )


__all__ = [
    "AdapterAlreadyRegistered",
    "AdapterNotRegistered",
    "AdapterRegistryError",
    "BackupRecoveryCatalogAdapter",
    "LocalFilesystemStorageRecoveryAdapter",
    "ProviderConfigurationError",
    "ProviderInvocationExecutor",
    "ProviderOperationError",
    "ProviderTimeoutError",
    "ResiliencePolicy",
    "execute_provider_call",
    "get_backup_catalog",
    "get_evidence_enricher",
    "get_extension_action",
    "get_metrics_collector",
    "get_provider_health_probe",
    "get_readiness_rule",
    "get_report_exporter",
    "get_storage_adapter",
    "list_storage_adapters",
    "provider_circuit_state",
    "register_backup_catalog",
    "register_evidence_enricher",
    "register_extension_action",
    "register_metrics_collector",
    "register_provider_health_probe",
    "register_readiness_rule",
    "register_report_exporter",
    "register_storage_adapter",
    "unregister_backup_catalog",
    "unregister_storage_adapter",
]
