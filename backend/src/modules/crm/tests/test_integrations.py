"""Resilient provider and paid-module ABI tests."""

from decimal import Decimal

import pytest
from django.test import override_settings

from src.modules.crm import integrations


class _Response:
    status_code = 200

    def __init__(self, body: object) -> None:
        self.body = body

    def json(self) -> object:
        return self.body


class _Breaker:
    class State:
        value = "closed"

    state = State()


class _Client:
    def __init__(self, body: object) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, endpoint: str, **kwargs: object) -> _Response:
        self.calls.append((endpoint, kwargs))
        return _Response(self.body)

    def get_breaker(self, dependency: str) -> _Breaker:
        assert dependency == "crm_ai"
        return _Breaker()


SCORING = {
    "dependency": "crm_ai",
    "endpoint": "/v1/score",
    "provider": "evidence-provider",
    "model": "score-2026-07",
}
PREDICTION = {
    "dependency": "crm_ai",
    "endpoint": "/v1/predict",
    "provider": "evidence-provider",
    "model": "forecast-2026-07",
}


@override_settings(CRM_LEAD_SCORING_PROVIDER=SCORING)
def test_scoring_client_returns_verified_typed_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client({"score": 83, "grade": "A", "factors": {"company_present": True}})
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda: client)
    result = integrations.get_scoring_client().score_lead(
        {"lead_id": "7c05a191-4dd8-44fd-a231-6154a29a6ccc"}, correlation_id="req_score_1"
    )
    assert result.score == 83
    assert result.grade == "A"
    assert result.provider == "evidence-provider"
    assert result.factors == {"company_present": True}
    assert client.calls[0][0] == "/v1/score"
    assert client.calls[0][1]["dependency"] == "crm_ai"


@override_settings(CRM_REVENUE_PREDICTION_PROVIDER=PREDICTION)
def test_prediction_preserves_provider_confidence_without_inventing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(
        {
            "amount": "125000.42",
            "currency": "USD",
            "confidence": "0.81",
            "as_of": "2026-07-22T00:00:00Z",
            "factors": {"open_opportunities": 8},
        }
    )
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda: client)
    result = integrations.get_revenue_prediction_client().predict_revenue(
        {"period_days": 90}, correlation_id="req_forecast_1"
    )
    assert result.amount == Decimal("125000.42")
    assert result.confidence == Decimal("0.81")
    assert result.as_dict()["amount"] == "125000.42"


def test_missing_provider_configuration_is_explicitly_unavailable() -> None:
    with override_settings(CRM_LEAD_SCORING_PROVIDER=None):
        with pytest.raises(integrations.IntegrationUnavailable):
            integrations.get_scoring_client()


@override_settings(CRM_LEAD_SCORING_PROVIDER=SCORING)
@pytest.mark.parametrize(
    "body",
    [
        {"score": 101, "factors": {}},
        {"score": 70, "grade": "A", "factors": {}},
        {"score": 70, "factors": {"nested": {"unsafe": True}}},
    ],
)
def test_malformed_provider_output_never_becomes_success(monkeypatch: pytest.MonkeyPatch, body: object) -> None:
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda: _Client(body))
    with pytest.raises(integrations.InvalidIntegrationResponse):
        integrations.get_scoring_client().score_lead({}, correlation_id="req_score_invalid")


class _QualificationProvider:
    schema_version = "1.0"

    def signals(self, context: object, lead_id: object) -> tuple[object, ...]:
        del context, lead_id
        return ()


def test_extension_registration_is_ordered_and_collision_safe() -> None:
    registry = integrations.CRMExtensionRegistry()
    later = _QualificationProvider()
    first = _QualificationProvider()
    registry.register("qualification", "industry.later", later, priority=200)
    registry.register("qualification", "industry.first", first, priority=10)
    assert registry.resolve("qualification") == (first, later)
    with pytest.raises(integrations.ExtensionConflictError):
        registry.register("qualification", "industry.first", _QualificationProvider())
    assert registry.unregister("qualification", "industry.first") is first


def test_sales_order_acknowledgement_requires_verified_same_tenant_delivery() -> None:
    from uuid import uuid4

    tenant = uuid4()
    event = {
        "event_type": "sales_management.order.created.v1",
        "event_id": str(uuid4()),
        "tenant_id": str(tenant),
        "opportunity_id": str(uuid4()),
        "order_id": str(uuid4()),
        "correlation_id": "req_order_ack_1",
    }
    acknowledgement = integrations.parse_sales_order_acknowledgement(
        event, expected_tenant_id=tenant, verified_delivery=True
    )
    assert acknowledgement.tenant_id == tenant
    with pytest.raises(integrations.InvalidIntegrationResponse):
        integrations.parse_sales_order_acknowledgement(event, expected_tenant_id=tenant, verified_delivery=False)
    with pytest.raises(integrations.InvalidIntegrationResponse):
        integrations.parse_sales_order_acknowledgement(event, expected_tenant_id=uuid4(), verified_delivery=True)
    with pytest.raises(integrations.InvalidIntegrationResponse):
        integrations.verify_fulfillment_acknowledgement(event)
    verified = integrations.verify_fulfillment_acknowledgement({**event, "delivery_verified": True})
    assert verified.accepted is True
    assert verified.tenant_id == tenant
    assert verified.external_order_id is not None
