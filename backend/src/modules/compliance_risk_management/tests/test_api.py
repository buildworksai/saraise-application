"""Governed v2 HTTP contract tests using real session authentication."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode

from ..models import RiskAssessment
from .factories import RiskAssessmentFactory

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db

RISKS = "/api/v2/compliance-risk-management/risks/"


@pytest.fixture(autouse=True)
def declared_access_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            True,
            AccessReasonCode.ALLOW,
            "declared permission allowed for API contract proof",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", allow)


def test_anonymous_collection_is_401(api_client) -> None:
    response = api_client.get(RISKS)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    body = response.json()
    assert body["error"]["code"]
    assert body["error"]["correlation_id"]


def test_list_uses_governed_envelope_pagination_and_tenant_scope(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    own = RiskAssessmentFactory(tenant_id=tenant_a.id, risk_code="OWN-RISK")
    foreign = RiskAssessmentFactory(tenant_id=tenant_b.id, risk_code="FOREIGN-RISK")
    response = authenticated_tenant_a_client.get(f"{RISKS}?page=1&page_size=25")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body) >= {"data", "meta"}
    assert body["meta"]["pagination"]["page"] == 1
    identities = {item["id"] for item in body["data"]}
    assert str(own.id) in identities
    assert str(foreign.id) not in identities


def test_create_binds_authenticated_tenant_and_returns_201(authenticated_tenant_a_client, tenant_a, tenant_b) -> None:
    actor = uuid.uuid4()
    response = authenticated_tenant_a_client.post(
        RISKS,
        {
            "tenant_id": str(tenant_b.id),
            "risk_code": "API-001",
            "name": "API-created risk",
            "category": "compliance",
            "description": "Created through the governed API.",
            "likelihood": 2,
            "impact": 3,
            "owner_id": str(actor),
            "review_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "idempotency_key": "api-create-001",
        },
        format="json",
    )
    # The strict serializer rejects tenant_id rather than trusting it.
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not RiskAssessment.objects.filter(tenant_id=tenant_b.id, risk_code="API-001").exists()

    response = authenticated_tenant_a_client.post(
        RISKS,
        {
            "risk_code": "API-001",
            "name": "API-created risk",
            "category": "compliance",
            "description": "Created through the governed API.",
            "likelihood": 2,
            "impact": 3,
            "owner_id": str(actor),
            "review_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "idempotency_key": "api-create-001",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    created = RiskAssessment.objects.get(pk=body["data"]["id"])
    assert created.tenant_id == tenant_a.id
    assert body["data"]["inherent_score"] == "6.00"


@pytest.mark.parametrize(
    "query",
    ["unknown=value", "page_size=101", "ordering=description", "owner_id=not-a-uuid"],
)
def test_invalid_query_parameters_use_governed_400(authenticated_tenant_a_client, query: str) -> None:
    response = authenticated_tenant_a_client.get(f"{RISKS}?{query}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["correlation_id"]


def test_score_preview_is_non_persistent_and_explainable(authenticated_tenant_a_client, tenant_a) -> None:
    before = RiskAssessment.objects.for_tenant(tenant_a.id).count()
    response = authenticated_tenant_a_client.post(
        f"{RISKS}score-preview/", {"likelihood": 4, "impact": 5}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()["data"]
    assert body["inherent_score"] == "20.00"
    assert body["risk_level"] == "critical"
    assert body["explanation"]["formula"] == "likelihood × impact"
    assert RiskAssessment.objects.for_tenant(tenant_a.id).count() == before


def test_put_and_unsupported_media_type_are_rejected(authenticated_tenant_a_client, tenant_a) -> None:
    risk = RiskAssessmentFactory(tenant_id=tenant_a.id)
    assert (
        authenticated_tenant_a_client.put(f"{RISKS}{risk.id}/", {"name": "No PUT"}, format="json").status_code
        == status.HTTP_405_METHOD_NOT_ALLOWED
    )
    response = authenticated_tenant_a_client.post(
        RISKS, "risk_code=FORM", content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    }
