"""Typed outcomes for service operations and their HTTP boundary mapping.

Services return :class:`OperationResult` when callers must distinguish a
durable success from a failed or unavailable capability.  A success is only
constructible with non-empty evidence; this prevents controllers from turning
placeholder values into fabricated successful responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, Literal, Mapping, TypeVar, cast

from rest_framework import status as http_status_codes
from rest_framework.exceptions import APIException
from rest_framework.response import Response

T = TypeVar("T")
ResultStatus = Literal["succeeded", "failed", "unavailable"]


class OperationFailed(APIException):
    """Raised when an operation completed with an explicit failure."""

    status_code: int = http_status_codes.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "operation_failed"
    default_detail = "The operation could not be completed."

    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        detail: object | None = None,
        evidence: Mapping[str, object] | None = None,
        http_status: int = http_status_codes.HTTP_422_UNPROCESSABLE_ENTITY,
    ) -> None:
        if not http_status_codes.is_client_error(http_status) and not http_status_codes.is_server_error(http_status):
            raise ValueError("Operation failures must map to an HTTP 4xx or 5xx status")
        self.status_code = http_status
        self.error_code = error_code
        self.public_message = message
        self.error_detail = detail
        self.evidence = MappingProxyType(dict(evidence or {}))
        super().__init__(detail=message, code=self.default_code)


class CapabilityUnavailable(OperationFailed):
    """Raised when an authoritative capability cannot currently execute."""

    status_code: int = http_status_codes.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "capability_unavailable"
    default_detail = "The requested capability is currently unavailable."

    def __init__(
        self,
        *,
        capability: str,
        message: str | None = None,
        detail: object | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> None:
        self.capability = capability
        super().__init__(
            error_code="CAPABILITY_UNAVAILABLE",
            message=message or self.default_detail,
            detail=detail if detail is not None else {"capability": capability},
            evidence=evidence,
            http_status=http_status_codes.HTTP_503_SERVICE_UNAVAILABLE,
        )


@dataclass(frozen=True, slots=True)
class OperationResult(Generic[T]):
    """Immutable outcome returned by service-layer operations.

    ``evidence`` is server-side provenance such as an affected-row count,
    durable record identifier, provider acknowledgement, or checksum.  It is
    intentionally not emitted by the HTTP adapter because evidence can contain
    operational data that is unsafe for clients.
    """

    status: ResultStatus
    value: T | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)
    provider: str | None = None
    error_code: str | None = None
    message: str | None = None
    detail: object | None = None
    http_status: int | None = None

    def __post_init__(self) -> None:
        evidence = dict(self.evidence)
        object.__setattr__(self, "evidence", MappingProxyType(evidence))

        if self.status not in ("succeeded", "failed", "unavailable"):
            raise ValueError(f"Unsupported operation status: {self.status}")
        if self.provider is not None and not self.provider.strip():
            raise ValueError("provider must be non-empty when supplied")

        if self.status == "succeeded":
            if not evidence:
                raise ValueError("Successful operations require evidence")
            if self.error_code is not None or self.message is not None or self.http_status is not None:
                raise ValueError("Successful operations cannot carry an error")
            return

        if self.value is not None:
            raise ValueError("Failed or unavailable operations cannot carry a value")
        if not self.error_code or not self.message:
            raise ValueError("Failed or unavailable operations require an error code and message")
        if self.http_status is None or (
            not http_status_codes.is_client_error(self.http_status)
            and not http_status_codes.is_server_error(self.http_status)
        ):
            raise ValueError("Failed or unavailable operations require an HTTP 4xx or 5xx status")
        if self.status == "unavailable" and self.error_code != "CAPABILITY_UNAVAILABLE":
            raise ValueError("Unavailable operations must use CAPABILITY_UNAVAILABLE")
        if self.status == "unavailable" and self.http_status != http_status_codes.HTTP_503_SERVICE_UNAVAILABLE:
            raise ValueError("Unavailable operations must map to HTTP 503")

    @classmethod
    def succeeded(
        cls,
        value: T,
        *,
        evidence: Mapping[str, object],
        provider: str | None = None,
    ) -> "OperationResult[T]":
        """Create a proven successful result."""

        return cls(status="succeeded", value=value, evidence=evidence, provider=provider)

    @classmethod
    def failed(
        cls,
        *,
        code: str,
        message: str,
        detail: object | None = None,
        evidence: Mapping[str, object] | None = None,
        provider: str | None = None,
        http_status: int = http_status_codes.HTTP_422_UNPROCESSABLE_ENTITY,
    ) -> "OperationResult[T]":
        """Create an explicit non-success outcome."""

        return cls(
            status="failed",
            evidence=evidence or {},
            provider=provider,
            error_code=code,
            message=message,
            detail=detail,
            http_status=http_status,
        )

    @classmethod
    def unavailable(
        cls,
        *,
        capability: str,
        message: str = "The requested capability is currently unavailable.",
        detail: object | None = None,
        evidence: Mapping[str, object] | None = None,
        provider: str | None = None,
    ) -> "OperationResult[T]":
        """Create a capability-unavailable outcome that maps to HTTP 503."""

        if not capability.strip():
            raise ValueError("capability must be non-empty")
        unavailable_detail = detail if detail is not None else {"capability": capability}
        return cls(
            status="unavailable",
            evidence=evidence or {},
            provider=provider,
            error_code="CAPABILITY_UNAVAILABLE",
            message=message,
            detail=unavailable_detail,
            http_status=http_status_codes.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def unwrap(self) -> T:
        """Return the value or raise the typed exception for this outcome."""

        if self.status == "succeeded":
            return cast(T, self.value)
        raise self.to_exception()

    def to_exception(self) -> OperationFailed:
        """Convert a non-success result to its DRF boundary exception."""

        if self.status == "succeeded":
            raise ValueError("A successful result has no exception")
        if self.status == "unavailable":
            capability = "unknown"
            if isinstance(self.detail, Mapping):
                candidate = self.detail.get("capability")
                if isinstance(candidate, str) and candidate:
                    capability = candidate
            return CapabilityUnavailable(
                capability=capability,
                message=self.message,
                detail=self.detail,
                evidence=self.evidence,
            )
        return OperationFailed(
            error_code=cast(str, self.error_code),
            message=cast(str, self.message),
            detail=self.detail,
            evidence=self.evidence,
            http_status=cast(int, self.http_status),
        )

    def to_response(self, *, success_status: int = http_status_codes.HTTP_200_OK) -> Response:
        """Adapt this result to DRF, raising typed exceptions for non-success."""

        return operation_result_to_response(self, success_status=success_status)


def operation_result_to_response(
    result: OperationResult[T],
    *,
    success_status: int = http_status_codes.HTTP_200_OK,
) -> Response:
    """Map a service outcome to DRF without manufacturing a successful value."""

    if result.status != "succeeded":
        raise result.to_exception()
    return Response(result.value, status=success_status)
