"""Typed, resilient adapters for optional compliance-risk dependencies.

There is no cross-module ORM coupling here.  Missing adapters remain visibly
``unavailable``; evidence verification is the one fail-closed operation and
never treats absence, timeout, a circuit-open response, or malformed JSON as
successful verification.
"""

from __future__ import annotations

import hmac
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, NoReturn, Protocol, runtime_checkable
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from src.core.resilience.circuit_breaker import CircuitBreakerError
from src.core.resilience.http import ResilientHttpClient, ResilientHttpError

DEPENDENCIES: Final[tuple[str, ...]] = (
    "workflow_automation",
    "notifications",
    "audit_trail",
    "dms",
    "reporting_analytics",
)


class IntegrationError(RuntimeError):
    """Base error for all integration-boundary failures."""

    code = "INTEGRATION_ERROR"


class IntegrationUnavailable(IntegrationError):
    code = "INTEGRATION_UNAVAILABLE"


class InvalidIntegrationResponse(IntegrationError):
    code = "INVALID_INTEGRATION_RESPONSE"


class EvidenceValidationError(IntegrationError):
    code = "EVIDENCE_INVALID"


class EvidenceVerificationUnavailable(IntegrationUnavailable):
    code = "EVIDENCE_VERIFICATION_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    """Sanitized dependency state suitable for a readiness response."""

    name: str
    available: bool
    code: str
    circuit_state: str
    checked_at: datetime
    configured: bool

    @property
    def status(self) -> str:
        return "healthy" if self.available else "unavailable"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "code": self.code,
            "circuit_state": self.circuit_state,
            "configured": self.configured,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class IntegrationResult:
    """Truthful outcome of an optional cross-module operation."""

    status: str
    code: str
    external_id: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status in {"accepted", "completed"}


class IntegrationAdapter(Protocol):
    name: str

    def health(self) -> DependencyHealth: ...


@runtime_checkable
class DMSAdapterContract(IntegrationAdapter, Protocol):
    def verify_version(
        self,
        tenant_id: UUID | str,
        document_id: UUID | str,
        version_id: UUID | str,
        checksum: str,
    ) -> bool: ...


@runtime_checkable
class NotificationAdapterContract(IntegrationAdapter, Protocol):
    def enqueue_reminder(
        self,
        tenant_id: UUID | str,
        entry_id: UUID | str,
        assigned_to_id: UUID | str,
        idempotency_key: str,
    ) -> IntegrationResult: ...


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def _bounded_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise EvidenceValidationError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise EvidenceValidationError(f"{field} must contain between 1 and {maximum} characters")
    return normalized


def _number(configuration: Mapping[str, object], field: str, default: float) -> float:
    value = configuration.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _integer(configuration: Mapping[str, object], field: str, default: int) -> int:
    value = configuration.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def validate_evidence_shape(evidence: object) -> list[dict[str, str]]:
    """Validate the exact non-secret evidence-reference document shape."""

    if not isinstance(evidence, list):
        raise EvidenceValidationError("evidence must be an array")
    if len(evidence) > 100:
        raise EvidenceValidationError("evidence cannot contain more than 100 references")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[UUID, UUID]] = set()
    expected = {"document_id", "version_id", "label", "checksum"}
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping) or set(item) != expected:
            raise EvidenceValidationError(f"evidence[{index}] must contain exactly {', '.join(sorted(expected))}")
        document_id = _uuid(item["document_id"], f"evidence[{index}].document_id")
        version_id = _uuid(item["version_id"], f"evidence[{index}].version_id")
        label = _bounded_text(item["label"], f"evidence[{index}].label", 255)
        checksum = _bounded_text(item["checksum"], f"evidence[{index}].checksum", 128).lower()
        if not all(character in "0123456789abcdef" for character in checksum) or len(checksum) not in {64, 128}:
            raise EvidenceValidationError(f"evidence[{index}].checksum must be a SHA-256 or SHA-512 hex digest")
        key = (document_id, version_id)
        if key in seen:
            raise EvidenceValidationError("evidence contains a duplicate document version")
        seen.add(key)
        normalized.append(
            {
                "document_id": str(document_id),
                "version_id": str(version_id),
                "label": label,
                "checksum": checksum,
            }
        )
    return normalized


class UnavailableAdapter:
    """Explicit absence object; it never returns fabricated success."""

    def __init__(self, name: str, code: str = "not_configured") -> None:
        self.name = name
        self.code = code

    def health(self) -> DependencyHealth:
        return DependencyHealth(self.name, False, self.code, "unknown", timezone.now(), False)

    def _unavailable(self) -> NoReturn:
        raise IntegrationUnavailable(f"{self.name} integration is unavailable")

    def verify_version(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        self._unavailable()

    def enqueue_reminder(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        self._unavailable()

    def __getattr__(self, operation: str) -> object:
        if operation.startswith("_"):
            raise AttributeError(operation)

        def unavailable(*args: object, **kwargs: object) -> IntegrationResult:
            del args, kwargs
            self._unavailable()

        return unavailable


class ResilientJsonAdapter:
    """HTTP JSON adapter with foundation SSRF, timeout, retry, and circuit controls."""

    health_path = "/health/ready/"

    def __init__(self, name: str, configuration: Mapping[str, object]) -> None:
        if name not in DEPENDENCIES:
            raise ValueError(f"Unknown compliance-risk dependency: {name}")
        self.name = name
        base_url = configuration.get("base_url")
        allowed_hosts = configuration.get("allowed_hosts")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError(f"{name}.base_url must be configured")
        if not isinstance(allowed_hosts, Sequence) or isinstance(allowed_hosts, (str, bytes)) or not allowed_hosts:
            raise ValueError(f"{name}.allowed_hosts must be a non-empty array")
        self.client = ResilientHttpClient(
            {
                name: {
                    "base_url": base_url,
                    "allowed_hosts": list(allowed_hosts),
                }
            },
            connect_timeout=_number(configuration, "connect_timeout", 2.0),
            read_timeout=_number(configuration, "read_timeout", 5.0),
            max_retries=_integer(configuration, "max_retries", 2),
            retry_backoff=_number(configuration, "retry_backoff", 0.1),
            failure_threshold=_integer(configuration, "failure_threshold", 5),
            reset_timeout=_number(configuration, "reset_timeout", 60.0),
        )

    @property
    def circuit_state(self) -> str:
        return self.client.get_breaker(self.name).state.value

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        accepted_statuses: frozenset[int] = frozenset({200}),
    ) -> Mapping[str, object]:
        try:
            response = self.client.request(method, path, dependency=self.name, json=dict(payload or {}))
        except (CircuitBreakerError, ResilientHttpError) as exc:
            raise IntegrationUnavailable(f"{self.name} dependency is unavailable") from exc
        if response.status_code not in accepted_statuses:
            raise IntegrationUnavailable(f"{self.name} dependency rejected the operation")
        try:
            document = response.json()
        except (TypeError, ValueError) as exc:
            raise InvalidIntegrationResponse(f"{self.name} returned invalid JSON") from exc
        if not isinstance(document, Mapping):
            raise InvalidIntegrationResponse(f"{self.name} returned an invalid document")
        return document

    def health(self) -> DependencyHealth:
        try:
            response = self.client.get(self.health_path, dependency=self.name)
            available = 200 <= response.status_code < 300
            code = "ready" if available else "dependency_unavailable"
        except CircuitBreakerError:
            available, code = False, "circuit_open"
        except ResilientHttpError:
            available, code = False, "dependency_unavailable"
        return DependencyHealth(self.name, available, code, self.circuit_state, timezone.now(), True)


class DMSIntegrationAdapter(ResilientJsonAdapter):
    verification_path = "/api/v2/dms/evidence/verify/"

    def verify_version(
        self,
        tenant_id: UUID | str,
        document_id: UUID | str,
        version_id: UUID | str,
        checksum: str,
    ) -> bool:
        """Verify one version for the service-layer evidence contract."""

        tenant = _uuid(tenant_id, "tenant_id")
        expected_checksum = _bounded_text(checksum, "checksum", 128).lower()
        document = self._json_request(
            "POST",
            self.verification_path,
            payload={
                "tenant_id": str(tenant),
                "document_id": str(_uuid(document_id, "document_id")),
                "version_id": str(_uuid(version_id, "version_id")),
                "checksum": expected_checksum,
            },
        )
        data = document.get("data")
        if not isinstance(data, Mapping):
            raise EvidenceVerificationUnavailable("DMS evidence verification returned an invalid document")
        verified_checksum = str(data.get("checksum", "")).lower()
        return (
            data.get("valid") is True
            and str(data.get("tenant_id")) == str(tenant)
            and hmac.compare_digest(verified_checksum, expected_checksum)
        )

    def validate_evidence(self, tenant_id: UUID | str, evidence: object) -> list[dict[str, str]]:
        """Verify every reference and its checksum belongs to the active tenant."""

        tenant = _uuid(tenant_id, "tenant_id")
        references = validate_evidence_shape(evidence)
        for reference in references:
            try:
                document = self._json_request(
                    "POST",
                    self.verification_path,
                    payload={"tenant_id": str(tenant), **reference},
                )
            except IntegrationError as exc:
                raise EvidenceVerificationUnavailable("DMS evidence verification is unavailable") from exc
            data = document.get("data")
            if not isinstance(data, Mapping):
                raise EvidenceVerificationUnavailable("DMS evidence verification returned an invalid document")
            if data.get("valid") is not True or str(data.get("tenant_id")) != str(tenant):
                raise EvidenceValidationError("Evidence is invalid or belongs to another tenant")
            verified_checksum = str(data.get("checksum", "")).lower()
            if not hmac.compare_digest(verified_checksum, reference["checksum"]):
                raise EvidenceValidationError("Evidence checksum does not match the verified DMS version")
        return references


class NotificationIntegrationAdapter(ResilientJsonAdapter):
    reminder_path = "/api/v2/notifications/reminders/"

    def enqueue_reminder(
        self,
        tenant_id: UUID | str,
        entry_id: UUID | str,
        assigned_to_id: UUID | str,
        idempotency_key: str,
    ) -> IntegrationResult:
        document = self._json_request(
            "POST",
            self.reminder_path,
            payload={
                "tenant_id": str(_uuid(tenant_id, "tenant_id")),
                "calendar_entry_id": str(_uuid(entry_id, "entry_id")),
                "assigned_to_id": str(_uuid(assigned_to_id, "assigned_to_id")),
                "idempotency_key": _bounded_text(idempotency_key, "idempotency_key", 255),
            },
            accepted_statuses=frozenset({200, 201, 202}),
        )
        data = document.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("id"), str):
            raise InvalidIntegrationResponse("Notification acknowledgement is invalid")
        return IntegrationResult("accepted", "queued", data["id"])


class WorkflowIntegrationAdapter(ResilientJsonAdapter):
    workflow_path = "/api/v2/workflow-automation/requests/"

    def start_workflow(self, tenant_id: UUID | str, payload: Mapping[str, object]) -> IntegrationResult:
        document = self._json_request(
            "POST",
            self.workflow_path,
            payload={"tenant_id": str(_uuid(tenant_id, "tenant_id")), **dict(payload)},
            accepted_statuses=frozenset({200, 201, 202}),
        )
        data = document.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("id"), str):
            raise InvalidIntegrationResponse("Workflow acknowledgement is invalid")
        return IntegrationResult("accepted", "queued", data["id"])


class AuditIntegrationAdapter(ResilientJsonAdapter):
    audit_path = "/api/v2/audit-trail/events/"

    def publish_audit_projection(self, tenant_id: UUID | str, payload: Mapping[str, object]) -> IntegrationResult:
        document = self._json_request(
            "POST",
            self.audit_path,
            payload={"tenant_id": str(_uuid(tenant_id, "tenant_id")), **dict(payload)},
            accepted_statuses=frozenset({200, 201, 202}),
        )
        data = document.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("id"), str):
            raise InvalidIntegrationResponse("Audit acknowledgement is invalid")
        return IntegrationResult("accepted", "queued", data["id"])


class ReportingIntegrationAdapter(ResilientJsonAdapter):
    projection_path = "/api/v2/reporting-analytics/projections/"

    def publish_projection(self, tenant_id: UUID | str, payload: Mapping[str, object]) -> IntegrationResult:
        document = self._json_request(
            "POST",
            self.projection_path,
            payload={"tenant_id": str(_uuid(tenant_id, "tenant_id")), **dict(payload)},
            accepted_statuses=frozenset({200, 201, 202}),
        )
        data = document.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("id"), str):
            raise InvalidIntegrationResponse("Reporting acknowledgement is invalid")
        return IntegrationResult("accepted", "queued", data["id"])


ADAPTER_TYPES: Final[Mapping[str, type[ResilientJsonAdapter]]] = {
    "workflow_automation": WorkflowIntegrationAdapter,
    "notifications": NotificationIntegrationAdapter,
    "audit_trail": AuditIntegrationAdapter,
    "dms": DMSIntegrationAdapter,
    "reporting_analytics": ReportingIntegrationAdapter,
}


class IntegrationRegistry:
    """Thread-safe adapter registry and explicit paid-extension seam."""

    def __init__(self) -> None:
        self._adapters: dict[str, IntegrationAdapter] = {}
        self._lock = threading.RLock()

    def register(self, name: str, adapter: IntegrationAdapter, *, replace: bool = False) -> None:
        if name not in DEPENDENCIES:
            raise ValueError(f"Unknown compliance-risk dependency: {name}")
        if getattr(adapter, "name", None) != name:
            raise ValueError("Adapter name does not match its registration key")
        with self._lock:
            if name in self._adapters and not replace:
                raise ValueError(f"An adapter is already registered for {name}")
            self._adapters[name] = adapter

    def get(self, name: str) -> IntegrationAdapter:
        if name not in DEPENDENCIES:
            raise ValueError(f"Unknown compliance-risk dependency: {name}")
        with self._lock:
            return self._adapters.get(name, UnavailableAdapter(name))

    def health(self) -> dict[str, DependencyHealth]:
        results: dict[str, DependencyHealth] = {}
        for name in DEPENDENCIES:
            try:
                results[name] = self.get(name).health()
            except Exception:
                results[name] = DependencyHealth(name, False, "probe_failed", "unknown", timezone.now(), True)
        return results


def build_integration_registry(configuration: object | None = None) -> IntegrationRegistry:
    """Build adapters from an allow-listed document; malformed entries stay unavailable."""

    source = configuration
    if source is None:
        source = getattr(settings, "COMPLIANCE_RISK_INTEGRATIONS", {})
    if not isinstance(source, Mapping):
        raise ValueError("COMPLIANCE_RISK_INTEGRATIONS must be an object")
    unknown = set(source) - set(DEPENDENCIES)
    if unknown:
        raise ValueError(f"Unknown compliance-risk integrations: {', '.join(sorted(unknown))}")
    registry = IntegrationRegistry()
    for name, raw_configuration in source.items():
        if not isinstance(raw_configuration, Mapping) or raw_configuration.get("enabled") is not True:
            continue
        registry.register(name, ADAPTER_TYPES[name](name, raw_configuration))
    return registry


_registry: IntegrationRegistry | None = None
_registry_lock = threading.RLock()


def get_integration_registry(*, refresh: bool = False) -> IntegrationRegistry:
    global _registry
    with _registry_lock:
        if refresh or _registry is None:
            _registry = build_integration_registry()
        return _registry


def set_integration_registry(registry: IntegrationRegistry) -> None:
    """Install a validated runtime registry for tests or configuration publication."""

    if not isinstance(registry, IntegrationRegistry):
        raise TypeError("registry must be an IntegrationRegistry")
    global _registry
    with _registry_lock:
        _registry = registry


def get_dms_adapter() -> DMSAdapterContract:
    adapter = get_integration_registry().get("dms")
    if isinstance(adapter, DMSAdapterContract):
        return adapter
    raise IntegrationUnavailable("Registered DMS adapter does not implement the DMS contract")


def get_notification_adapter() -> NotificationAdapterContract:
    adapter = get_integration_registry().get("notifications")
    if isinstance(adapter, NotificationAdapterContract):
        return adapter
    raise IntegrationUnavailable("Registered notification adapter does not implement the reminder contract")


# Concise public aliases for service and paid-module consumers.
DMSAdapter = DMSIntegrationAdapter
NotificationAdapter = NotificationIntegrationAdapter
WorkflowAdapter = WorkflowIntegrationAdapter
AuditAdapter = AuditIntegrationAdapter
ReportingAdapter = ReportingIntegrationAdapter

__all__ = [
    "AuditAdapter",
    "DEPENDENCIES",
    "DMSAdapter",
    "DMSAdapterContract",
    "DependencyHealth",
    "EvidenceValidationError",
    "EvidenceVerificationUnavailable",
    "IntegrationError",
    "IntegrationRegistry",
    "IntegrationResult",
    "IntegrationUnavailable",
    "InvalidIntegrationResponse",
    "NotificationAdapter",
    "NotificationAdapterContract",
    "ReportingAdapter",
    "UnavailableAdapter",
    "WorkflowAdapter",
    "build_integration_registry",
    "get_integration_registry",
    "get_dms_adapter",
    "get_notification_adapter",
    "set_integration_registry",
    "validate_evidence_shape",
]
