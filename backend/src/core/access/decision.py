"""Unified, fail-closed access decision pipeline.

SPDX-License-Identifier: Apache-2.0

The pipeline is intentionally the only component that orders identity, tenant,
policy, entitlement, and quota checks.  A failed stage terminates evaluation;
later stages never weaken or reinterpret the denial.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger("saraise.access")


class AccessReasonCode(str, Enum):
    """Stable access decision reason codes."""

    ALLOW = "ALLOW"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    DENY_SUBJECT_INVALID = "DENY_SUBJECT_INVALID"
    DENY_TENANT_MISMATCH = "DENY_TENANT_MISMATCH"
    DENY_DEFAULT = "DENY_DEFAULT"
    POLICY_CONFIG_MISSING = "POLICY_CONFIG_MISSING"
    POLICY_DENIED = "POLICY_DENIED"
    ENGINE_TIMEOUT = "ENGINE_TIMEOUT"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


ReasonCode = AccessReasonCode


@dataclass(frozen=True)
class AccessDecision:
    """Typed, auditable result of evaluating one access request."""

    allowed: bool
    reason_code: AccessReasonCode
    reason: str
    reason_codes: tuple[AccessReasonCode, ...] = ()
    tenant_id: uuid.UUID | None = None
    remaining_quota: int | None = None
    applied_policies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason_codes:
            object.__setattr__(self, "reason_codes", (self.reason_code,))

    @classmethod
    def deny(
        cls,
        reason_code: AccessReasonCode,
        reason: str,
        *,
        tenant_id: uuid.UUID | None = None,
    ) -> AccessDecision:
        """Build a denial containing a stable reason code."""

        return cls(
            allowed=False,
            reason_code=reason_code,
            reason=reason,
            tenant_id=tenant_id,
        )


@dataclass(frozen=True)
class PolicyEvaluation:
    """Normalized response from the authoritative Policy Engine."""

    allowed: bool
    reason_codes: tuple[str, ...] = ()
    applied_policies: tuple[str, ...] = ()


class PolicyEvaluator(Protocol):
    """Interface consumed by ``AccessDecisionPipeline``."""

    def evaluate(
        self,
        tenant_id: uuid.UUID,
        identity: object,
        required_permission: str,
        *,
        request: object | None = None,
    ) -> PolicyEvaluation | bool:
        """Evaluate one permission without falling back to local RBAC."""


class EntitlementCheck(Protocol):
    """Structural type returned by an entitlement service."""

    entitled: bool


class EntitlementChecker(Protocol):
    """Interface consumed for explicit capability grants."""

    def check(self, tenant_id: uuid.UUID, capability: str) -> EntitlementCheck:
        """Return an explicit tenant entitlement result."""


class QuotaConsumption(Protocol):
    """Structural type returned by a quota service."""

    allowed: bool
    remaining: int


class QuotaConsumer(Protocol):
    """Interface consumed for atomic quota reservation."""

    def consume(
        self,
        tenant_id: uuid.UUID,
        resource: str,
        *,
        cost: int = 1,
    ) -> QuotaConsumption:
        """Atomically reserve quota for an allowed operation."""


class PolicyConfigurationError(RuntimeError):
    """The authoritative policy dependency is not configured."""


class PolicyDependencyError(RuntimeError):
    """The authoritative policy dependency did not return a valid result."""


class PolicyTimeoutError(PolicyDependencyError):
    """The authoritative policy dependency exceeded its hard timeout."""


class CircuitOpenError(PolicyDependencyError):
    """A dependency call was rejected because its circuit is open."""


class CircuitBreaker:
    """Thread-safe circuit breaker for synchronous policy evaluation calls."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def call(self, operation: Callable[[], object]) -> object:
        """Execute ``operation`` when closed and track dependency failures."""

        with self._lock:
            now = self._clock()
            if self._opened_at is not None:
                if now - self._opened_at < self.recovery_timeout:
                    raise CircuitOpenError("Policy Engine circuit is open")
                self._opened_at = None
                self._failures = 0

        try:
            result = operation()
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = self._clock()
            raise

        with self._lock:
            self._failures = 0
            self._opened_at = None
        return result


_POLICY_CIRCUIT_BREAKER = CircuitBreaker()


class HttpPolicyEvaluator:
    """Policy Engine client with timeout, circuit breaking, and strict parsing."""

    TIMEOUT_SECONDS = 2.0

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = TIMEOUT_SECONDS,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        configured_url = base_url if base_url is not None else getattr(settings, "SARAISE_POLICY_ENGINE_URL", None)
        self.base_url = (
            configured_url.rstrip("/") if isinstance(configured_url, str) and configured_url.strip() else None
        )
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker or _POLICY_CIRCUIT_BREAKER

    def evaluate(
        self,
        tenant_id: uuid.UUID,
        identity: object,
        required_permission: str,
        *,
        request: object | None = None,
    ) -> PolicyEvaluation:
        """Evaluate policy; configuration, transport, and response errors deny."""

        if not self.base_url:
            raise PolicyConfigurationError("Policy Engine URL is not configured")

        payload = self._build_payload(tenant_id, identity, required_permission, request=request)

        def send_request() -> PolicyEvaluation:
            response = requests.post(
                f"{self.base_url}/api/v1/evaluate",
                json=cast(Any, payload),
                timeout=self.timeout,
            )

            if not isinstance(response, requests.Response) and not hasattr(response, "status_code"):
                raise PolicyDependencyError("Policy Engine returned an invalid transport response")
            if response.status_code != 200:
                raise PolicyDependencyError("Policy Engine returned a non-success status")

            try:
                body = response.json()
            except (TypeError, ValueError) as exc:
                raise PolicyDependencyError("Policy Engine returned invalid JSON") from exc
            if not isinstance(body, Mapping):
                raise PolicyDependencyError("Policy Engine response must be an object")

            decision = body.get("decision")
            legacy_allowed = body.get("allowed")
            if decision not in ("allow", "deny") and not isinstance(legacy_allowed, bool):
                raise PolicyDependencyError("Policy Engine response omitted a valid decision")

            allowed = decision == "allow" if decision in ("allow", "deny") else legacy_allowed is True
            return PolicyEvaluation(
                allowed=allowed,
                reason_codes=self._string_tuple(body.get("reason_codes")),
                applied_policies=self._string_tuple(body.get("applied_policies")),
            )

        try:
            evaluation = self.circuit_breaker.call(send_request)
        except requests.Timeout as exc:
            raise PolicyTimeoutError("Policy Engine evaluation timed out") from exc
        except CircuitOpenError:
            raise
        except PolicyDependencyError:
            raise
        except requests.RequestException as exc:
            raise PolicyDependencyError("Policy Engine is unavailable") from exc

        if not isinstance(evaluation, PolicyEvaluation):
            raise PolicyDependencyError("Policy Engine circuit returned an invalid result")
        return evaluation

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return ()
        return tuple(item for item in value if isinstance(item, str))

    @staticmethod
    def _build_payload(
        tenant_id: uuid.UUID,
        identity: object,
        required_permission: str,
        *,
        request: object | None,
    ) -> dict[str, object]:
        roles = _string_list(getattr(identity, "roles", []))
        groups = _identity_groups(identity)
        session = getattr(request, "session", None)
        session_id = getattr(session, "session_key", "") if session is not None else ""
        request_id = getattr(request, "correlation_id", "") if request is not None else ""
        path = getattr(request, "path", "") if request is not None else ""

        return {
            "tenant_id": str(tenant_id),
            "subject": {
                "id": str(getattr(identity, "id", getattr(identity, "pk", ""))),
                "type": getattr(identity, "subject_type", "user"),
            },
            "resource": {
                "type": path or required_permission.split(":", maxsplit=1)[0],
                "tenant_id": str(tenant_id),
                "attributes": {},
            },
            "action": required_permission,
            "required_permissions": [required_permission],
            "context": {
                "request_id": str(request_id),
                "org_scope": {},
            },
            "identity_snapshot": {
                "session_id": str(session_id or ""),
                "policy_version": str(getattr(identity, "policy_version", "")),
                "roles": roles,
                "groups": groups,
                "jit_grants": list(getattr(identity, "jit_grants", [])),
            },
        }


class AccessDecisionPipeline:
    """Evaluate access in one fixed, fail-closed order."""

    def __init__(
        self,
        *,
        policy_evaluator: PolicyEvaluator | None = None,
        entitlement_service: EntitlementChecker | None = None,
        quota_service: QuotaConsumer | None = None,
    ) -> None:
        if entitlement_service is None or quota_service is None:
            from .entitlements import EntitlementService, QuotaService

        self.policy_evaluator = policy_evaluator or HttpPolicyEvaluator()
        self.entitlement_service = entitlement_service or EntitlementService()
        self.quota_service = quota_service or QuotaService()

    def decide(
        self,
        tenant_id: uuid.UUID | str | None,
        identity: object,
        required_permission: str | None,
        *,
        entitlement: str | None = None,
        quota: str | None = None,
        quota_cost: int = 1,
        request: object | None = None,
    ) -> AccessDecision:
        """Return an allow/deny result without any weaker fallback path.

        Evaluation order is fixed by the unit contract: authenticated identity,
        tenant match, policy, explicit entitlement, then atomic quota consume.
        """

        if not bool(getattr(identity, "is_authenticated", False)):
            return AccessDecision.deny(
                AccessReasonCode.AUTHENTICATION_REQUIRED,
                "A valid authenticated session is required.",
            )

        subject_id = getattr(identity, "id", getattr(identity, "pk", None))
        if subject_id is None:
            return AccessDecision.deny(
                AccessReasonCode.DENY_SUBJECT_INVALID,
                "The authenticated subject is incomplete.",
            )

        requested_tenant = _normalize_uuid(tenant_id)
        identity_tenant = _normalize_uuid(_identity_tenant_id(identity))
        if requested_tenant is None or identity_tenant is None or requested_tenant != identity_tenant:
            return AccessDecision.deny(
                AccessReasonCode.DENY_TENANT_MISMATCH,
                "The request tenant does not match the authenticated subject.",
                tenant_id=requested_tenant,
            )

        if not isinstance(required_permission, str) or not required_permission.strip():
            return AccessDecision.deny(
                AccessReasonCode.DENY_DEFAULT,
                "Access metadata does not declare a required permission.",
                tenant_id=requested_tenant,
            )

        policy_decision = self._evaluate_policy(
            requested_tenant,
            identity,
            required_permission,
            request=request,
        )
        if isinstance(policy_decision, AccessDecision):
            return policy_decision
        if not policy_decision.allowed:
            return AccessDecision(
                allowed=False,
                reason_code=AccessReasonCode.POLICY_DENIED,
                reason="The authoritative policy denied this operation.",
                tenant_id=requested_tenant,
                applied_policies=policy_decision.applied_policies,
            )

        capability = entitlement if entitlement is not None else required_permission
        try:
            entitlement_result = self.entitlement_service.check(requested_tenant, capability)
        except Exception:
            logger.exception(
                "Entitlement dependency failed closed",
                extra={"tenant_id": str(requested_tenant), "capability": capability},
            )
            return AccessDecision.deny(
                AccessReasonCode.DEPENDENCY_UNAVAILABLE,
                "Entitlement state is unavailable.",
                tenant_id=requested_tenant,
            )
        if not entitlement_result.entitled:
            return AccessDecision.deny(
                AccessReasonCode.ENTITLEMENT_REQUIRED,
                "An explicit entitlement is required for this capability.",
                tenant_id=requested_tenant,
            )

        quota_resource = quota if quota is not None else required_permission
        try:
            quota_result = self.quota_service.consume(
                requested_tenant,
                quota_resource,
                cost=quota_cost,
            )
        except Exception:
            logger.exception(
                "Quota dependency failed closed",
                extra={"tenant_id": str(requested_tenant), "resource": quota_resource},
            )
            return AccessDecision.deny(
                AccessReasonCode.DEPENDENCY_UNAVAILABLE,
                "Quota state is unavailable.",
                tenant_id=requested_tenant,
            )
        if not quota_result.allowed:
            return AccessDecision(
                allowed=False,
                reason_code=AccessReasonCode.QUOTA_EXCEEDED,
                reason="The quota for this operation is exhausted or missing.",
                tenant_id=requested_tenant,
                remaining_quota=quota_result.remaining,
            )

        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="All access checks passed.",
            tenant_id=requested_tenant,
            remaining_quota=quota_result.remaining,
            applied_policies=policy_decision.applied_policies,
        )

    def evaluate(
        self,
        tenant_id: uuid.UUID | str | None,
        identity: object,
        required_permission: str | None,
        *,
        entitlement: str | None = None,
        quota: str | None = None,
        quota_cost: int = 1,
        request: object | None = None,
    ) -> AccessDecision:
        """Alias for codebases that name pipeline execution ``evaluate``."""

        return self.decide(
            tenant_id,
            identity,
            required_permission,
            entitlement=entitlement,
            quota=quota,
            quota_cost=quota_cost,
            request=request,
        )

    def _evaluate_policy(
        self,
        tenant_id: uuid.UUID,
        identity: object,
        required_permission: str,
        *,
        request: object | None,
    ) -> PolicyEvaluation | AccessDecision:
        try:
            result = self.policy_evaluator.evaluate(
                tenant_id,
                identity,
                required_permission,
                request=request,
            )
        except PolicyConfigurationError:
            return AccessDecision.deny(
                AccessReasonCode.POLICY_CONFIG_MISSING,
                "The authoritative policy dependency is not configured.",
                tenant_id=tenant_id,
            )
        except PolicyTimeoutError:
            return AccessDecision.deny(
                AccessReasonCode.ENGINE_TIMEOUT,
                "The authoritative policy evaluation timed out.",
                tenant_id=tenant_id,
            )
        except (CircuitOpenError, PolicyDependencyError):
            return AccessDecision.deny(
                AccessReasonCode.ENGINE_UNAVAILABLE,
                "The authoritative policy dependency is unavailable.",
                tenant_id=tenant_id,
            )
        except Exception:
            logger.exception(
                "Unexpected policy evaluator failure denied access",
                extra={"tenant_id": str(tenant_id), "permission": required_permission},
            )
            return AccessDecision.deny(
                AccessReasonCode.ENGINE_UNAVAILABLE,
                "The authoritative policy dependency is unavailable.",
                tenant_id=tenant_id,
            )

        if isinstance(result, bool):
            return PolicyEvaluation(allowed=result)
        if not isinstance(result, PolicyEvaluation):
            return AccessDecision.deny(
                AccessReasonCode.ENGINE_UNAVAILABLE,
                "The authoritative policy dependency returned an invalid result.",
                tenant_id=tenant_id,
            )
        return result


def _identity_tenant_id(identity: object) -> object | None:
    try:
        direct_tenant = cast(object | None, getattr(identity, "tenant_id", None))
        if direct_tenant is not None:
            return direct_tenant
        profile = cast(object | None, getattr(identity, "profile", None))
        return cast(object | None, getattr(profile, "tenant_id", None))
    except (AttributeError, ObjectDoesNotExist):
        return None


def _normalize_uuid(value: object | None) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def _identity_groups(identity: object) -> list[str]:
    groups = getattr(identity, "groups", None)
    if groups is None:
        return []
    values_list = getattr(groups, "values_list", None)
    if callable(values_list):
        return list(values_list("name", flat=True))
    return _string_list(groups)


AccessDecisionReason = AccessReasonCode

__all__ = [
    "AccessDecision",
    "AccessDecisionPipeline",
    "AccessDecisionReason",
    "AccessReasonCode",
    "CircuitBreaker",
    "CircuitOpenError",
    "HttpPolicyEvaluator",
    "PolicyConfigurationError",
    "PolicyDependencyError",
    "PolicyEvaluation",
    "PolicyTimeoutError",
    "ReasonCode",
]
