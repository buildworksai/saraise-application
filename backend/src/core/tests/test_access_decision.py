"""Fail-closed tests for the unified access-decision foundation.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from src.core.access.decision import (
    AccessDecisionPipeline,
    AccessReasonCode,
    CircuitBreaker,
    CircuitOpenError,
    HttpPolicyEvaluator,
    PolicyDependencyError,
    PolicyEvaluation,
)
from src.core.access.entitlements import Entitlement, EntitlementService, Quota, QuotaService
from src.core.access.permissions import RequiresAccess
from src.core.module_registry_models import ModuleRegistryEntry, TenantModuleInstallation

PERMISSION = "manufacturing.work-order:execute"
CAPABILITY = "manufacturing"
QUOTA_RESOURCE = "manufacturing.work-order"


@dataclass(frozen=True)
class StubEntitlementResult:
    entitled: bool


@dataclass(frozen=True)
class StubQuotaResult:
    allowed: bool
    remaining: int


class StubPolicyEvaluator:
    """Deterministic policy dependency used by pipeline unit tests."""

    def __init__(self, result: PolicyEvaluation | bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[uuid.UUID, object, str]] = []

    def evaluate(
        self,
        tenant_id: uuid.UUID,
        identity: object,
        required_permission: str,
        *,
        request: object | None = None,
    ) -> PolicyEvaluation | bool:
        self.calls.append((tenant_id, identity, required_permission))
        if self.error is not None:
            raise self.error
        return self.result


class StubEntitlementService:
    """Entitlement dependency that records whether the pipeline reached it."""

    def __init__(self, entitled: bool = True, error: Exception | None = None) -> None:
        self.entitled = entitled
        self.error = error
        self.calls: list[tuple[uuid.UUID, str]] = []

    def check(self, tenant_id: uuid.UUID, capability: str) -> StubEntitlementResult:
        self.calls.append((tenant_id, capability))
        if self.error is not None:
            raise self.error
        return StubEntitlementResult(entitled=self.entitled)


class StubQuotaService:
    """Quota dependency that records reservation attempts."""

    def __init__(self, allowed: bool = True, remaining: int = 4, error: Exception | None = None) -> None:
        self.allowed = allowed
        self.remaining = remaining
        self.error = error
        self.calls: list[tuple[uuid.UUID, str, int]] = []

    def consume(
        self,
        tenant_id: uuid.UUID,
        resource: str,
        *,
        cost: int = 1,
    ) -> StubQuotaResult:
        self.calls.append((tenant_id, resource, cost))
        if self.error is not None:
            raise self.error
        return StubQuotaResult(allowed=self.allowed, remaining=self.remaining)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def identity(tenant_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_authenticated=True,
        profile=SimpleNamespace(tenant_id=str(tenant_id)),
        roles=["tenant_user"],
        policy_version="v1",
        jit_grants=[],
    )


def build_pipeline(
    *,
    policy: StubPolicyEvaluator | None = None,
    entitlement: StubEntitlementService | None = None,
    quota: StubQuotaService | None = None,
) -> tuple[AccessDecisionPipeline, StubPolicyEvaluator, StubEntitlementService, StubQuotaService]:
    policy_dependency = policy or StubPolicyEvaluator()
    entitlement_dependency = entitlement or StubEntitlementService()
    quota_dependency = quota or StubQuotaService()
    return (
        AccessDecisionPipeline(
            policy_evaluator=policy_dependency,
            entitlement_service=entitlement_dependency,
            quota_service=quota_dependency,
        ),
        policy_dependency,
        entitlement_dependency,
        quota_dependency,
    )


def decide(
    pipeline: AccessDecisionPipeline,
    tenant_id: uuid.UUID,
    identity: object,
    *,
    required_permission: str | None = PERMISSION,
):
    return pipeline.decide(
        tenant_id,
        identity,
        required_permission,
        entitlement=CAPABILITY,
        quota=QUOTA_RESOURCE,
        quota_cost=1,
    )


class TestAccessDecisionPipeline:
    def test_unauthenticated_identity_denies_before_dependencies(self, tenant_id: uuid.UUID) -> None:
        pipeline, policy, entitlement, quota = build_pipeline()
        anonymous = SimpleNamespace(id=uuid.uuid4(), is_authenticated=False, tenant_id=tenant_id)

        result = decide(pipeline, tenant_id, anonymous)

        assert result.allowed is False
        assert result.reason_code == AccessReasonCode.AUTHENTICATION_REQUIRED
        assert policy.calls == []
        assert entitlement.calls == []
        assert quota.calls == []

    def test_incomplete_authenticated_subject_denies(self, tenant_id: uuid.UUID) -> None:
        pipeline, policy, _, _ = build_pipeline()
        subject = SimpleNamespace(is_authenticated=True, tenant_id=tenant_id)

        result = decide(pipeline, tenant_id, subject)

        assert result.reason_code == AccessReasonCode.DENY_SUBJECT_INVALID
        assert policy.calls == []

    @pytest.mark.parametrize("request_tenant", [None, "", "not-a-uuid"])
    def test_missing_or_invalid_request_tenant_denies(
        self,
        request_tenant: str | None,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, policy, _, _ = build_pipeline()

        result = decide(pipeline, request_tenant, identity)

        assert result.reason_code == AccessReasonCode.DENY_TENANT_MISMATCH
        assert policy.calls == []

    def test_tenant_mismatch_denies(self, identity: SimpleNamespace) -> None:
        pipeline, policy, entitlement, quota = build_pipeline()

        result = decide(pipeline, uuid.uuid4(), identity)

        assert result.allowed is False
        assert result.reason_code == AccessReasonCode.DENY_TENANT_MISMATCH
        assert policy.calls == []
        assert entitlement.calls == []
        assert quota.calls == []

    def test_missing_permission_metadata_denies_by_default(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, policy, _, _ = build_pipeline()

        result = decide(pipeline, tenant_id, identity, required_permission=None)

        assert result.reason_code == AccessReasonCode.DENY_DEFAULT
        assert policy.calls == []

    def test_invalid_permission_metadata_denies_by_default(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, policy, _, _ = build_pipeline()

        result = decide(pipeline, tenant_id, identity, required_permission=42)

        assert result.reason_code == AccessReasonCode.DENY_DEFAULT
        assert policy.calls == []

    def test_missing_identity_profile_denies_tenant_match(self, tenant_id: uuid.UUID) -> None:
        class IdentityWithoutProfile:
            id = uuid.uuid4()
            is_authenticated = True

            @property
            def profile(self):
                raise ObjectDoesNotExist("profile missing")

        pipeline, policy, _, _ = build_pipeline()

        result = decide(pipeline, tenant_id, IdentityWithoutProfile())

        assert result.reason_code == AccessReasonCode.DENY_TENANT_MISMATCH
        assert policy.calls == []

    def test_policy_dependency_error_denies_without_rbac_fallback(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        identity.has_perm = Mock(return_value=True)
        pipeline, _, entitlement, quota = build_pipeline(
            policy=StubPolicyEvaluator(error=PolicyDependencyError("offline"))
        )

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE
        identity.has_perm.assert_not_called()
        assert entitlement.calls == []
        assert quota.calls == []

    def test_unexpected_policy_error_denies_without_fallback(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, _, entitlement, _ = build_pipeline(policy=StubPolicyEvaluator(error=RuntimeError("broken")))

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE
        assert entitlement.calls == []

    def test_explicit_policy_deny_short_circuits_entitlement_and_quota(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        policy_result = PolicyEvaluation(
            allowed=False,
            reason_codes=("DENY_EXPLICIT",),
            applied_policies=("policy-42",),
        )
        pipeline, _, entitlement, quota = build_pipeline(policy=StubPolicyEvaluator(result=policy_result))

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.POLICY_DENIED
        assert result.applied_policies == ("policy-42",)
        assert entitlement.calls == []
        assert quota.calls == []

    def test_invalid_policy_result_denies(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        policy = StubPolicyEvaluator()
        policy.result = object()
        pipeline, _, _, _ = build_pipeline(policy=policy)

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    def test_missing_entitlement_denies_before_quota(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, _, entitlement, quota = build_pipeline(entitlement=StubEntitlementService(entitled=False))

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENTITLEMENT_REQUIRED
        assert entitlement.calls == [(tenant_id, CAPABILITY)]
        assert quota.calls == []

    def test_entitlement_dependency_failure_denies(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, _, _, quota = build_pipeline(
            entitlement=StubEntitlementService(error=RuntimeError("projection unavailable"))
        )

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.DEPENDENCY_UNAVAILABLE
        assert quota.calls == []

    def test_quota_exhaustion_denies(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        pipeline, _, _, quota = build_pipeline(quota=StubQuotaService(allowed=False, remaining=0))

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.QUOTA_EXCEEDED
        assert result.remaining_quota == 0
        assert quota.calls == [(tenant_id, QUOTA_RESOURCE, 1)]

    def test_quota_dependency_failure_denies(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        pipeline, _, _, _ = build_pipeline(quota=StubQuotaService(error=RuntimeError("counter unavailable")))

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.DEPENDENCY_UNAVAILABLE

    def test_happy_path_allows_in_fixed_order(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        policy = StubPolicyEvaluator(
            result=PolicyEvaluation(allowed=True, reason_codes=("ALLOW",), applied_policies=("policy-1",))
        )
        pipeline, _, entitlement, quota = build_pipeline(policy=policy)

        result = pipeline.evaluate(
            tenant_id,
            identity,
            PERMISSION,
            entitlement=CAPABILITY,
            quota=QUOTA_RESOURCE,
            quota_cost=2,
        )

        assert result.allowed is True
        assert result.reason_code == AccessReasonCode.ALLOW
        assert result.reason_codes == (AccessReasonCode.ALLOW,)
        assert result.remaining_quota == 4
        assert result.applied_policies == ("policy-1",)
        assert entitlement.calls == [(tenant_id, CAPABILITY)]
        assert quota.calls == [(tenant_id, QUOTA_RESOURCE, 2)]


class TestHttpPolicyEvaluator:
    def test_missing_policy_configuration_denies_without_http_or_rbac(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        identity.has_perm = Mock(return_value=True)
        pipeline = AccessDecisionPipeline(
            policy_evaluator=HttpPolicyEvaluator(base_url=""),
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post") as post:
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.POLICY_CONFIG_MISSING
        post.assert_not_called()
        identity.has_perm.assert_not_called()

    @pytest.mark.parametrize("status_code", [201, 400, 401, 403, 429, 500, 503])
    def test_every_non_200_response_denies(
        self,
        status_code: int,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        response = Mock(status_code=status_code)
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post", return_value=response):
            result = decide(pipeline, tenant_id, identity)

        assert result.allowed is False
        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    def test_timeout_has_stable_reason(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post", side_effect=requests.Timeout("late")):
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_TIMEOUT

    def test_request_exception_denies(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch(
            "src.core.access.decision.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    @pytest.mark.parametrize(
        "body",
        [None, [], {}, {"decision": "maybe"}, {"allowed": "yes"}],
    )
    def test_invalid_200_payload_denies(
        self,
        body: object,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = body
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post", return_value=response):
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    def test_invalid_json_denies(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("not json")
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post", return_value=response):
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    def test_allow_response_is_normalized_and_sends_timeout(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "decision": "allow",
            "reason_codes": ["ALLOW", 12],
            "applied_policies": ["policy-a"],
        }
        evaluator = HttpPolicyEvaluator(
            base_url="https://policy.invalid", timeout=1.25, circuit_breaker=CircuitBreaker()
        )

        with patch("src.core.access.decision.requests.post", return_value=response) as post:
            result = evaluator.evaluate(tenant_id, identity, PERMISSION)

        assert result == PolicyEvaluation(True, ("ALLOW",), ("policy-a",))
        assert post.call_args.kwargs["timeout"] == 1.25
        assert post.call_args.kwargs["json"]["tenant_id"] == str(tenant_id)

    def test_legacy_explicit_boolean_decision_is_supported(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"allowed": False}
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())

        with patch("src.core.access.decision.requests.post", return_value=response):
            result = evaluator.evaluate(tenant_id, identity, PERMISSION)

        assert result.allowed is False

    def test_invalid_transport_object_denies(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        evaluator = HttpPolicyEvaluator(base_url="https://policy.invalid", circuit_breaker=CircuitBreaker())
        pipeline = AccessDecisionPipeline(
            policy_evaluator=evaluator,
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        with patch("src.core.access.decision.requests.post", return_value=object()):
            result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENGINE_UNAVAILABLE

    def test_circuit_opens_and_recovers(self) -> None:
        clock = Mock(return_value=10.0)
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5, clock=clock)
        failing_operation = Mock(side_effect=PolicyDependencyError("down"))

        with pytest.raises(PolicyDependencyError):
            breaker.call(failing_operation)
        with pytest.raises(CircuitOpenError):
            breaker.call(Mock())

        clock.return_value = 16.0
        assert breaker.call(lambda: "recovered") == "recovered"

    def test_non_200_responses_open_policy_circuit(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        response = Mock(status_code=503)
        evaluator = HttpPolicyEvaluator(
            base_url="https://policy.invalid",
            circuit_breaker=CircuitBreaker(failure_threshold=2),
        )

        with patch("src.core.access.decision.requests.post", return_value=response) as post:
            for _ in range(3):
                with pytest.raises(PolicyDependencyError):
                    evaluator.evaluate(tenant_id, identity, PERMISSION)

        assert post.call_count == 2

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"failure_threshold": 0}, "failure_threshold"),
            ({"recovery_timeout": 0}, "recovery_timeout"),
        ],
    )
    def test_circuit_breaker_rejects_invalid_configuration(self, kwargs: dict[str, int], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            CircuitBreaker(**kwargs)

    def test_http_evaluator_rejects_invalid_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            HttpPolicyEvaluator(base_url="https://policy.invalid", timeout=0)

    def test_non_string_setting_is_treated_as_missing_configuration(
        self,
        settings,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        settings.SARAISE_POLICY_ENGINE_URL = 42
        pipeline = AccessDecisionPipeline(
            entitlement_service=StubEntitlementService(),
            quota_service=StubQuotaService(),
        )

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.POLICY_CONFIG_MISSING


@pytest.mark.django_db
class TestEntitlementAndQuotaServices:
    def test_installed_module_is_not_an_entitlement(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        registry_entry = ModuleRegistryEntry.objects.create(
            name=CAPABILITY,
            version="1.0.0",
            module_type="industry",
            lifecycle="managed",
            manifest_content="name: manufacturing",
            manifest_hash="a" * 64,
        )
        TenantModuleInstallation.objects.create(
            tenant_id=str(tenant_id),
            module_name=CAPABILITY,
            module_version="1.0.0",
            registry_entry=registry_entry,
            installed_by=str(identity.id),
            status="installed",
        )
        pipeline = AccessDecisionPipeline(
            policy_evaluator=StubPolicyEvaluator(),
            entitlement_service=EntitlementService(),
            quota_service=StubQuotaService(),
        )

        result = decide(pipeline, tenant_id, identity)

        assert result.reason_code == AccessReasonCode.ENTITLEMENT_REQUIRED

    def test_entitlement_effective_window_and_tenant_isolation(self, tenant_id: uuid.UUID) -> None:
        other_tenant = uuid.uuid4()
        Entitlement.objects.create(tenant_id=other_tenant, capability=CAPABILITY)
        service = EntitlementService()

        assert service.check(tenant_id, CAPABILITY).entitled is False
        assert service.is_entitled(other_tenant, CAPABILITY) is True

        Entitlement.objects.create(
            tenant_id=tenant_id,
            capability=CAPABILITY,
            starts_at=timezone.now() + timezone.timedelta(hours=1),
        )
        assert service.check(tenant_id, CAPABILITY).entitled is False

    def test_disabled_and_expired_entitlements_deny(self, tenant_id: uuid.UUID) -> None:
        service = EntitlementService()
        Entitlement.objects.create(tenant_id=tenant_id, capability="disabled", enabled=False)
        Entitlement.objects.create(
            tenant_id=tenant_id,
            capability="expired",
            starts_at=timezone.now() - timezone.timedelta(hours=2),
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        assert service.check(tenant_id, "disabled").entitled is False
        assert service.check(tenant_id, "expired").entitled is False
        assert service.check(tenant_id, "").entitled is False

    def test_entitlement_unique_per_tenant_capability(self, tenant_id: uuid.UUID) -> None:
        entitlement = Entitlement.objects.create(tenant_id=tenant_id, capability=CAPABILITY)

        assert str(entitlement) == f"{tenant_id}:{CAPABILITY}"

        with pytest.raises(IntegrityError):
            Entitlement.objects.create(tenant_id=tenant_id, capability=CAPABILITY)

    def test_entitlement_rejects_invalid_effective_window(self, tenant_id: uuid.UUID) -> None:
        starts_at = timezone.now()

        with pytest.raises(IntegrityError):
            Entitlement.objects.create(
                tenant_id=tenant_id,
                capability=CAPABILITY,
                starts_at=starts_at,
                expires_at=starts_at - timezone.timedelta(seconds=1),
            )

    def test_missing_quota_is_zero_not_unlimited(self, tenant_id: uuid.UUID) -> None:
        result = QuotaService().consume(tenant_id, QUOTA_RESOURCE)

        assert result.allowed is False
        assert result.limit == 0
        assert result.remaining == 0

    def test_zero_and_exhausted_quota_deny(self, tenant_id: uuid.UUID) -> None:
        service = QuotaService()
        zero = Quota.objects.create(tenant_id=tenant_id, resource="zero", limit=0, remaining=0)
        exhausted = Quota.objects.create(tenant_id=tenant_id, resource="spent", limit=3, remaining=0)

        assert service.consume(tenant_id, zero.resource).allowed is False
        result = service.consume(tenant_id, exhausted.resource)
        assert result.allowed is False
        assert result.limit == 3
        assert result.remaining == 0

    def test_quota_decrement_is_atomic_and_stops_at_zero(self, tenant_id: uuid.UUID) -> None:
        quota = Quota.objects.create(tenant_id=tenant_id, resource=QUOTA_RESOURCE, limit=3, remaining=3)
        service = QuotaService()

        assert str(quota) == f"{tenant_id}:{QUOTA_RESOURCE} (3/3)"

        first = service.consume(tenant_id, QUOTA_RESOURCE, cost=2)
        second = service.check_and_decrement(tenant_id, QUOTA_RESOURCE, amount=1)
        denied = service.consume(tenant_id, QUOTA_RESOURCE)

        quota.refresh_from_db()
        assert first.allowed is True
        assert first.remaining == 1
        assert second.allowed is True
        assert second.remaining == 0
        assert denied.allowed is False
        assert quota.remaining == 0

    def test_quota_rejects_remaining_above_limit(self, tenant_id: uuid.UUID) -> None:
        with pytest.raises(IntegrityError):
            Quota.objects.create(
                tenant_id=tenant_id,
                resource=QUOTA_RESOURCE,
                limit=1,
                remaining=2,
            )

    def test_quota_consumption_is_tenant_scoped(self, tenant_id: uuid.UUID) -> None:
        other_tenant = uuid.uuid4()
        own = Quota.objects.create(tenant_id=tenant_id, resource=QUOTA_RESOURCE, limit=2, remaining=2)
        other = Quota.objects.create(tenant_id=other_tenant, resource=QUOTA_RESOURCE, limit=5, remaining=5)

        result = QuotaService().consume(tenant_id, QUOTA_RESOURCE)

        own.refresh_from_db()
        other.refresh_from_db()
        assert result.allowed is True
        assert own.remaining == 1
        assert other.remaining == 5

    def test_expired_quota_denies_without_mutation(self, tenant_id: uuid.UUID) -> None:
        quota = Quota.objects.create(
            tenant_id=tenant_id,
            resource=QUOTA_RESOURCE,
            limit=2,
            remaining=2,
            reset_at=timezone.now() - timezone.timedelta(seconds=1),
        )

        result = QuotaService().consume(tenant_id, QUOTA_RESOURCE)

        quota.refresh_from_db()
        assert result.allowed is False
        assert result.limit == 0
        assert quota.remaining == 2

    @pytest.mark.parametrize(
        ("resource", "cost", "message"),
        [
            ("", 1, "resource"),
            (QUOTA_RESOURCE, 0, "positive"),
            (QUOTA_RESOURCE, -1, "positive"),
            (QUOTA_RESOURCE, True, "positive"),
        ],
    )
    def test_quota_rejects_invalid_reservation(
        self,
        tenant_id: uuid.UUID,
        resource: str,
        cost: int,
        message: str,
    ) -> None:
        with pytest.raises(ValueError, match=message):
            QuotaService().consume(tenant_id, resource, cost=cost)

    def test_real_services_happy_path_decrements_once(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        Entitlement.objects.create(tenant_id=tenant_id, capability=CAPABILITY)
        quota = Quota.objects.create(tenant_id=tenant_id, resource=QUOTA_RESOURCE, limit=2, remaining=2)
        pipeline = AccessDecisionPipeline(policy_evaluator=StubPolicyEvaluator())

        result = decide(pipeline, tenant_id, identity)

        quota.refresh_from_db()
        assert result.allowed is True
        assert result.remaining_quota == 1
        assert quota.remaining == 1


class TestRequiresAccess:
    def build_request(self, tenant_id: uuid.UUID, identity: SimpleNamespace):
        request = APIRequestFactory().get("/api/v1/work-orders/")
        request.user = identity
        request.tenant_id = tenant_id
        return request

    def test_missing_metadata_denies_without_pipeline(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline = Mock(spec=AccessDecisionPipeline)
        permission = RequiresAccess(pipeline=pipeline)
        request = self.build_request(tenant_id, identity)

        assert permission.has_permission(request, SimpleNamespace()) is False
        assert request.access_decision.reason_code == AccessReasonCode.DENY_DEFAULT
        pipeline.decide.assert_not_called()

    def test_configured_permission_delegates_and_is_drf_callable(
        self,
        tenant_id: uuid.UUID,
        identity: SimpleNamespace,
    ) -> None:
        pipeline, _, _, _ = build_pipeline()
        configured = RequiresAccess(PERMISSION, pipeline=pipeline)
        request = self.build_request(tenant_id, identity)
        view = SimpleNamespace(
            required_entitlement=CAPABILITY,
            quota_resource=QUOTA_RESOURCE,
            quota_cost=1,
        )

        assert configured() is configured
        assert configured.has_permission(request, view) is True
        assert request.access_decision.reason_code == AccessReasonCode.ALLOW

    def test_view_metadata_can_supply_permission(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        pipeline, _, _, _ = build_pipeline()
        permission = RequiresAccess(pipeline=pipeline)
        request = self.build_request(tenant_id, identity)

        assert permission.has_permission(request, SimpleNamespace(required_permission=PERMISSION)) is True

    def test_object_permission_requires_same_tenant(self, tenant_id: uuid.UUID, identity: SimpleNamespace) -> None:
        pipeline, _, _, _ = build_pipeline()
        permission = RequiresAccess(PERMISSION, pipeline=pipeline)
        request = self.build_request(tenant_id, identity)
        assert (
            permission.has_object_permission(request, SimpleNamespace(), SimpleNamespace(tenant_id=tenant_id)) is False
        )

        assert permission.has_permission(request, SimpleNamespace()) is True
        assert (
            permission.has_object_permission(
                request,
                SimpleNamespace(),
                SimpleNamespace(tenant_id=tenant_id),
            )
            is True
        )
        assert (
            permission.has_object_permission(
                request,
                SimpleNamespace(),
                SimpleNamespace(tenant_id=uuid.uuid4()),
            )
            is False
        )
        assert permission.has_object_permission(request, SimpleNamespace(), SimpleNamespace()) is False
