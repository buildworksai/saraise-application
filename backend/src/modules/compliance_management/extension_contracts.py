"""Stable DTO-only extension boundary for paid compliance capabilities.

Extensions receive immutable service DTOs and the platform's SSRF-safe HTTP
client.  They never receive Django models or querysets.  Registration is exact,
collision-safe, entitlement-gated at every invocation, and failures remain
explicit instead of degrading to guessed OSS results.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from django.conf import settings

from src.core.access.entitlements import EntitlementService
from src.core.resilience.circuit_breaker import CircuitOpenError
from src.core.resilience.http import DependencyTimeoutError, ResilientHttpClient, ResilientHttpError

EXTENSION_CONTRACT_VERSION = "1.0.0"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 2
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+){2,}$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$")

JsonValue = str | int | float | bool | None | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("extension DTO values must be JSON-compatible")


def _thaw(value: JsonValue) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _identifier(value: object, label: str) -> str:
    candidate = str(value).strip()
    if not _IDENTIFIER.fullmatch(candidate):
        raise ValueError(f"{label} must be a namespaced lowercase identifier")
    return candidate


def _version(value: object) -> str:
    candidate = str(value).strip()
    if not _VERSION.fullmatch(candidate):
        raise ValueError("extension version must be semantic MAJOR.MINOR.PATCH")
    return candidate


def _digest(value: Mapping[str, JsonValue]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExtensionKind(str, Enum):
    FRAMEWORK_PACK = "framework_pack"
    EVIDENCE_COLLECTOR = "evidence_collector"
    APPLICABILITY_RULE = "applicability_rule"
    SCORING_RULE = "scoring_rule"
    REPORT_RENDERER = "report_renderer"


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    identifier: str
    kind: ExtensionKind
    version: str
    required_entitlement: str
    contract_version: str = EXTENSION_CONTRACT_VERSION
    external_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _identifier(self.identifier, "extension identifier"))
        object.__setattr__(self, "version", _version(self.version))
        object.__setattr__(self, "required_entitlement", _identifier(self.required_entitlement, "entitlement"))
        object.__setattr__(self, "contract_version", _version(self.contract_version))
        dependencies = tuple(_identifier(item, "dependency") for item in self.external_dependencies)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("external dependency identifiers must be unique")
        object.__setattr__(self, "external_dependencies", dependencies)
        if self.contract_version.split(".", 1)[0] != EXTENSION_CONTRACT_VERSION.split(".", 1)[0]:
            raise ValueError("extension contract major version is incompatible")


@dataclass(frozen=True, slots=True)
class ExtensionExecutionContext:
    tenant_id: UUID
    correlation_id: str
    actor_id: str | None
    http_client: ResilientHttpClient | None


@dataclass(frozen=True, slots=True)
class FrameworkPackRequest:
    tenant_id: UUID
    correlation_id: str
    package_key: str
    parameters: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_key", _identifier(self.package_key, "package key"))
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True, slots=True)
class FrameworkPackResult:
    extension_id: str
    extension_version: str
    schema_version: str
    package: Mapping[str, JsonValue]
    input_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "package", _freeze(self.package))
        if not self.package:
            raise ValueError("framework pack result must contain a package")


@dataclass(frozen=True, slots=True)
class EvidenceCollectionRequest:
    tenant_id: UUID
    correlation_id: str
    actor_id: str
    idempotency_key: str
    parameters: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.correlation_id.strip() or not self.idempotency_key.strip():
            raise ValueError("correlation_id and idempotency_key are required")
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True, slots=True)
class CollectedEvidence:
    stable_key: str
    evidence_type: str
    reference_kind: str
    reference: str
    sha256: str = ""
    metadata: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.stable_key.strip() or not self.reference.strip():
            raise ValueError("collected evidence requires stable_key and reference")
        if self.sha256 and (len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256)):
            raise ValueError("sha256 must be lowercase hexadecimal")
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class EvidenceCollectionResult:
    extension_id: str
    extension_version: str
    input_digest: str
    evidence: tuple[CollectedEvidence, ...]

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("successful evidence collection must contain evidence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "extension_version": self.extension_version,
            "input_digest": self.input_digest,
            "evidence": [
                {
                    "stable_key": item.stable_key,
                    "evidence_type": item.evidence_type,
                    "reference_kind": item.reference_kind,
                    "reference": item.reference,
                    "sha256": item.sha256,
                    "metadata": _thaw(item.metadata),
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True, slots=True)
class ApplicabilityRequest:
    tenant_id: UUID
    correlation_id: str
    requirement_code: str
    facts: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", _freeze(self.facts))


@dataclass(frozen=True, slots=True)
class ApplicabilityDecision:
    applicable: bool
    rationale: str
    extension_id: str
    extension_version: str
    input_digest: str

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("applicability decisions require an explainable rationale")


@dataclass(frozen=True, slots=True)
class ScoringRequest:
    tenant_id: UUID
    correlation_id: str
    statuses: tuple[str, ...]
    parameters: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True, slots=True)
class ScoringResult:
    score: float
    rationale: str
    extension_id: str
    extension_version: str
    input_digest: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0 or not self.rationale.strip():
            raise ValueError("score must be in [0, 1] with an explainable rationale")


@dataclass(frozen=True, slots=True)
class ReportRenderRequest:
    tenant_id: UUID
    correlation_id: str
    report_kind: str
    snapshot: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", _freeze(self.snapshot))


@dataclass(frozen=True, slots=True)
class RenderedComplianceReport:
    media_type: str
    content: bytes
    extension_id: str
    extension_version: str
    input_digest: str

    def __post_init__(self) -> None:
        if not self.media_type.strip() or not self.content:
            raise ValueError("rendered report must contain a media type and content")


@runtime_checkable
class FrameworkPackProvider(Protocol):
    descriptor: ExtensionDescriptor

    def provide(self, context: ExtensionExecutionContext, request: FrameworkPackRequest) -> FrameworkPackResult: ...


@runtime_checkable
class EvidenceCollector(Protocol):
    descriptor: ExtensionDescriptor

    def collect(
        self, context: ExtensionExecutionContext, request: EvidenceCollectionRequest
    ) -> EvidenceCollectionResult: ...


@runtime_checkable
class ApplicabilityRule(Protocol):
    descriptor: ExtensionDescriptor

    def evaluate(self, context: ExtensionExecutionContext, request: ApplicabilityRequest) -> ApplicabilityDecision: ...


@runtime_checkable
class ScoringRule(Protocol):
    descriptor: ExtensionDescriptor

    def score(self, context: ExtensionExecutionContext, request: ScoringRequest) -> ScoringResult: ...


@runtime_checkable
class ComplianceReportRenderer(Protocol):
    descriptor: ExtensionDescriptor

    def render(
        self, context: ExtensionExecutionContext, request: ReportRenderRequest
    ) -> RenderedComplianceReport: ...


class ExtensionContractError(RuntimeError):
    code = "EXTENSION_ERROR"


class ExtensionRegistrationCollision(ExtensionContractError):
    code = "EXTENSION_REGISTRATION_COLLISION"


class ExtensionUnavailable(ExtensionContractError):
    code = "EXTENSION_UNAVAILABLE"


class ExtensionEntitlementDenied(ExtensionContractError):
    code = "EXTENSION_ENTITLEMENT_DENIED"


class ExtensionAdapterFailure(ExtensionContractError):
    code = "EXTENSION_ADAPTER_FAILURE"


class ExtensionCircuitOpen(ExtensionAdapterFailure):
    code = "EXTENSION_CIRCUIT_OPEN"


class ExtensionTimedOut(ExtensionAdapterFailure):
    code = "EXTENSION_TIMEOUT"


Extension = FrameworkPackProvider | EvidenceCollector | ApplicabilityRule | ScoringRule | ComplianceReportRenderer
ResultT = TypeVar("ResultT")


class ComplianceExtensionRegistry:
    """Thread-safe exact registry with invocation-time entitlement checks."""

    _METHODS = {
        ExtensionKind.FRAMEWORK_PACK: "provide",
        ExtensionKind.EVIDENCE_COLLECTOR: "collect",
        ExtensionKind.APPLICABILITY_RULE: "evaluate",
        ExtensionKind.SCORING_RULE: "score",
        ExtensionKind.REPORT_RENDERER: "render",
    }

    def __init__(
        self,
        *,
        entitlement_checker: Callable[[UUID, str], bool] | None = None,
        http_client_factory: Callable[[ExtensionDescriptor], ResilientHttpClient | None] | None = None,
    ) -> None:
        self._extensions: dict[str, Extension] = {}
        self._lock = threading.RLock()
        self._entitlement_checker = entitlement_checker or self._default_entitlement_checker
        self._http_client_factory = http_client_factory or self._default_http_client

    @staticmethod
    def _default_entitlement_checker(tenant_id: UUID, entitlement: str) -> bool:
        return bool(EntitlementService().check(tenant_id, entitlement).entitled)

    @staticmethod
    def _default_http_client(descriptor: ExtensionDescriptor) -> ResilientHttpClient | None:
        if not descriptor.external_dependencies:
            return None
        allowlist = getattr(settings, "COMPLIANCE_EXTENSION_DEPENDENCIES", None)
        if not isinstance(allowlist, Mapping):
            raise ExtensionUnavailable("extension dependency allow-list is unavailable")
        selected = {key: allowlist[key] for key in descriptor.external_dependencies if key in allowlist}
        if set(selected) != set(descriptor.external_dependencies):
            raise ExtensionUnavailable("one or more declared extension dependencies are unavailable")
        return ResilientHttpClient(
            selected,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            read_timeout=DEFAULT_READ_TIMEOUT_SECONDS,
            max_retries=DEFAULT_MAX_RETRIES,
        )

    def register(self, extension: Extension) -> ExtensionDescriptor:
        descriptor = getattr(extension, "descriptor", None)
        if not isinstance(descriptor, ExtensionDescriptor):
            raise TypeError("extension must expose an ExtensionDescriptor")
        required_method = self._METHODS[descriptor.kind]
        if not callable(getattr(extension, required_method, None)):
            raise TypeError(f"{descriptor.kind.value} extension must implement {required_method}()")
        with self._lock:
            if descriptor.identifier in self._extensions:
                raise ExtensionRegistrationCollision(f"extension {descriptor.identifier!r} is already registered")
            self._extensions[descriptor.identifier] = extension
        return descriptor

    def unregister(self, identifier: str) -> Extension | None:
        with self._lock:
            return self._extensions.pop(identifier, None)

    def resolve(self, identifier: str, kind: ExtensionKind) -> Extension:
        canonical = _identifier(identifier, "extension identifier")
        with self._lock:
            extension = self._extensions.get(canonical)
        if extension is None or extension.descriptor.kind is not kind:
            raise ExtensionUnavailable(f"extension {canonical!r} is unavailable")
        return extension

    def _invoke(self, identifier: str, kind: ExtensionKind, request: object) -> object:
        extension = self.resolve(identifier, kind)
        tenant_id = getattr(request, "tenant_id", None)
        correlation_id = getattr(request, "correlation_id", "")
        if not isinstance(tenant_id, UUID) or not isinstance(correlation_id, str) or not correlation_id.strip():
            raise ValueError("extension request requires tenant_id and correlation_id")
        descriptor = extension.descriptor
        try:
            entitled = self._entitlement_checker(tenant_id, descriptor.required_entitlement)
        except Exception as exc:
            raise ExtensionUnavailable("extension entitlement authority is unavailable") from exc
        if not entitled:
            raise ExtensionEntitlementDenied(f"tenant is not entitled to extension {identifier!r}")
        client = self._http_client_factory(descriptor)
        context = ExtensionExecutionContext(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            actor_id=getattr(request, "actor_id", None),
            http_client=client,
        )
        operation = getattr(extension, self._METHODS[kind])
        try:
            return operation(context, request)
        except CircuitOpenError as exc:
            raise ExtensionCircuitOpen("extension dependency circuit is open") from exc
        except DependencyTimeoutError as exc:
            raise ExtensionTimedOut("extension dependency timed out") from exc
        except ResilientHttpError as exc:
            raise ExtensionAdapterFailure("extension dependency failed") from exc
        except ExtensionContractError:
            raise
        except Exception as exc:
            raise ExtensionAdapterFailure("extension adapter failed") from exc

    def collect_evidence(self, identifier: str, request: EvidenceCollectionRequest) -> EvidenceCollectionResult:
        result = self._invoke(identifier, ExtensionKind.EVIDENCE_COLLECTOR, request)
        if not isinstance(result, EvidenceCollectionResult):
            raise ExtensionAdapterFailure("evidence collector returned an invalid result")
        return result

    def provide_framework(self, identifier: str, request: FrameworkPackRequest) -> FrameworkPackResult:
        result = self._invoke(identifier, ExtensionKind.FRAMEWORK_PACK, request)
        if not isinstance(result, FrameworkPackResult):
            raise ExtensionAdapterFailure("framework provider returned an invalid result")
        return result

    def evaluate_applicability(self, identifier: str, request: ApplicabilityRequest) -> ApplicabilityDecision:
        result = self._invoke(identifier, ExtensionKind.APPLICABILITY_RULE, request)
        if not isinstance(result, ApplicabilityDecision):
            raise ExtensionAdapterFailure("applicability rule returned an invalid result")
        return result

    def score(self, identifier: str, request: ScoringRequest) -> ScoringResult:
        result = self._invoke(identifier, ExtensionKind.SCORING_RULE, request)
        if not isinstance(result, ScoringResult):
            raise ExtensionAdapterFailure("scoring rule returned an invalid result")
        return result

    def render(self, identifier: str, request: ReportRenderRequest) -> RenderedComplianceReport:
        result = self._invoke(identifier, ExtensionKind.REPORT_RENDERER, request)
        if not isinstance(result, RenderedComplianceReport):
            raise ExtensionAdapterFailure("report renderer returned an invalid result")
        return result

    def identifiers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._extensions))


extension_registry = ComplianceExtensionRegistry()

__all__ = [
    "ApplicabilityDecision",
    "ApplicabilityRequest",
    "ApplicabilityRule",
    "CollectedEvidence",
    "ComplianceExtensionRegistry",
    "ComplianceReportRenderer",
    "EvidenceCollectionRequest",
    "EvidenceCollectionResult",
    "EvidenceCollector",
    "ExtensionAdapterFailure",
    "ExtensionCircuitOpen",
    "ExtensionDescriptor",
    "ExtensionEntitlementDenied",
    "ExtensionKind",
    "ExtensionRegistrationCollision",
    "ExtensionTimedOut",
    "ExtensionUnavailable",
    "FrameworkPackProvider",
    "FrameworkPackRequest",
    "FrameworkPackResult",
    "RenderedComplianceReport",
    "ReportRenderRequest",
    "ScoringRequest",
    "ScoringResult",
    "ScoringRule",
    "extension_registry",
]
